"""test_connection tool -- verify a configured MCP server works."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from mcp.server.fastmcp import Context

from mcp_tap.config.detection import detect_clients, resolve_config_path
from mcp_tap.config.reader import parse_servers, read_config
from mcp_tap.connection.tester import test_server_connection
from mcp_tap.errors import McpTapError, ServerNotFoundError
from mcp_tap.models import ConnectionTestResult, MCPClient


async def test_connection(
    server_name: str,
    ctx: Context,
    client: str = "",
    timeout_seconds: int = 15,
) -> dict[str, object]:
    """Test that a single configured MCP server starts and responds correctly.

    Spawns the server process, connects via MCP stdio protocol, calls
    list_tools() to verify it responds, then shuts it down cleanly.

    Use this to verify a specific server after configure_server, or to
    debug a server that check_health reported as unhealthy.

    Args:
        server_name: Exact name of the server as it appears in the config.
            Use list_installed to see available names.
        client: Which MCP client's config to read from. One of
            "claude_desktop", "claude_code", "cursor", "windsurf".
            Auto-detects if empty.
        timeout_seconds: Max seconds to wait for a response (clamped to 5-60).
            Default 15. Increase for slow-starting servers.

    Returns:
        Test result with success status, discovered tool names, or error
        message explaining what went wrong.
    """
    try:
        if client:
            location = resolve_config_path(MCPClient(client))
        else:
            clients = detect_clients()
            if not clients:
                return asdict(
                    ConnectionTestResult(
                        success=False,
                        server_name=server_name,
                        error="No MCP client detected.",
                    )
                )
            location = clients[0]

        raw = read_config(Path(location.path))
        servers = parse_servers(raw, source_file=location.path)

        target = next((s for s in servers if s.name == server_name), None)
        if target is None:
            raise ServerNotFoundError(
                f"Server '{server_name}' not found in {location.path}. "
                "Use list_installed to see configured servers."
            )

        timeout = max(5, min(timeout_seconds, 60))
        result = await test_server_connection(
            server_name,
            target.config,
            timeout_seconds=timeout,
        )
        return asdict(result)

    except McpTapError as exc:
        return asdict(
            ConnectionTestResult(
                success=False,
                server_name=server_name,
                error=str(exc),
            )
        )
    except Exception as exc:
        await ctx.error(f"Unexpected error in test_connection: {exc}")
        return asdict(
            ConnectionTestResult(
                success=False,
                server_name=server_name,
                error=f"Internal error: {type(exc).__name__}",
            )
        )
