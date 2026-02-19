"""remove_server tool -- remove an MCP server from config."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from mcp.server.fastmcp import Context

from mcp_tap.config.detection import detect_clients, resolve_config_path
from mcp_tap.config.writer import remove_server_config
from mcp_tap.errors import McpTapError
from mcp_tap.models import MCPClient, RemoveResult


async def remove_server(
    server_name: str,
    ctx: Context,
    client: str = "",
) -> dict[str, object]:
    """Remove an MCP server from your AI client's configuration.

    Args:
        server_name: Name of the server to remove (as shown by list_installed).
        client: Which MCP client's config to modify. Auto-detects if empty.

    Returns:
        Removal result showing what was removed.
    """
    try:
        if client:
            location = resolve_config_path(MCPClient(client))
        else:
            clients = detect_clients()
            if not clients:
                return asdict(
                    RemoveResult(
                        success=False,
                        server_name=server_name,
                        message="No MCP client detected.",
                    )
                )
            location = clients[0]

        removed = remove_server_config(Path(location.path), server_name)

        if removed is None:
            return asdict(
                RemoveResult(
                    success=False,
                    server_name=server_name,
                    config_file=location.path,
                    message=(
                        f"Server '{server_name}' not found in {location.path}. "
                        "Use list_installed to see configured servers."
                    ),
                )
            )

        return asdict(
            RemoveResult(
                success=True,
                server_name=server_name,
                config_file=location.path,
                message=(
                    f"Server '{server_name}' removed from {location.path}. "
                    "Restart your MCP client to apply."
                ),
            )
        )
    except McpTapError as exc:
        return asdict(
            RemoveResult(
                success=False,
                server_name=server_name,
                message=str(exc),
            )
        )
    except Exception as exc:
        await ctx.error(f"Unexpected error in remove_server: {exc}")
        return asdict(
            RemoveResult(
                success=False,
                server_name=server_name,
                message=f"Internal error: {type(exc).__name__}",
            )
        )
