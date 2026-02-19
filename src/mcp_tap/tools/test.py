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
    """Test that a configured MCP server starts and responds.

    Spawns the server, connects via MCP protocol, calls list_tools(),
    then shuts it down.

    Args:
        server_name: Name of the server as it appears in the config file.
        client: Which MCP client's config to read from. Auto-detects if empty.
        timeout_seconds: How long to wait for the server to respond (5-60).

    Returns:
        Test result showing whether the server connected and what tools
        it exposes, or the error message if it failed.
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
