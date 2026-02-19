"""list_installed tool -- show configured MCP servers."""

from __future__ import annotations

import re
from pathlib import Path

from mcp.server.fastmcp import Context

from mcp_tap.config.detection import detect_clients, resolve_config_path
from mcp_tap.config.reader import parse_servers, read_config
from mcp_tap.errors import McpTapError
from mcp_tap.models import MCPClient

_SECRET_PATTERN = re.compile(r"^[A-Za-z0-9+/=_\-]{20,}$")


def _mask_env(env: dict[str, str]) -> dict[str, str]:
    """Mask environment variable values that look like secrets."""
    masked: dict[str, str] = {}
    for key, value in env.items():
        if _SECRET_PATTERN.match(value):
            masked[key] = "***"
        else:
            masked[key] = value
    return masked


async def list_installed(
    ctx: Context,
    client: str = "",
) -> list[dict[str, object]]:
    """List all MCP servers currently configured in your AI client.

    Use this to see what servers are already set up before adding new ones
    with configure_server, or to find the exact server name needed for
    test_connection or remove_server.

    Secret-looking environment variable values (API keys, tokens) are
    automatically masked as "***" in the output.

    Args:
        client: Which MCP client's config to read. One of "claude_desktop",
            "claude_code", "cursor", "windsurf". Auto-detects if empty.

    Returns:
        List of configured servers, each with: name, command, args,
        env (masked), and config_file path.
    """
    try:
        if client:
            location = resolve_config_path(MCPClient(client))
        else:
            clients = detect_clients()
            if not clients:
                return [{"message": "No MCP client detected on this machine."}]
            location = clients[0]

        raw = read_config(Path(location.path))
        servers = parse_servers(raw, source_file=location.path)

        return [
            {
                "name": s.name,
                "command": s.config.command,
                "args": s.config.args,
                "env": _mask_env(s.config.env),
                "config_file": s.source_file,
            }
            for s in servers
        ]
    except McpTapError as exc:
        return [{"success": False, "error": str(exc)}]
    except Exception as exc:
        await ctx.error(f"Unexpected error in list_installed: {exc}")
        return [{"success": False, "error": f"Internal error: {type(exc).__name__}"}]
