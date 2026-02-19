"""remove_server tool -- remove an MCP server from config."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from mcp.server.fastmcp import Context

from mcp_tap.config.detection import resolve_config_locations
from mcp_tap.config.writer import remove_server_config
from mcp_tap.errors import McpTapError
from mcp_tap.models import RemoveResult

_NO_CLIENT_MSG = "No MCP client detected."


async def remove_server(
    server_name: str,
    ctx: Context,
    clients: str = "",
    scope: str = "user",
    project_path: str = "",
) -> dict[str, object]:
    """Remove an MCP server from your AI client's configuration.

    Removes the server entry from the config file. The user must restart
    their MCP client for the change to take effect.

    Use list_installed to see server names. Use clients="all" to remove
    from every configured client at once.

    Args:
        server_name: Exact name of the server to remove, as shown by
            list_installed.
        clients: Target MCP client(s). Comma-separated names like
            "claude_desktop,cursor", "all" for every detected client,
            or empty to auto-detect.
        scope: "user" for global config (default), "project" for
            project-scoped config.
        project_path: Project directory path. Required when scope="project".

    Returns:
        Result with success status and message. Multi-client calls also
        include per_client_results with per-client removal status.
    """
    try:
        locations = resolve_config_locations(clients, scope=scope, project_path=project_path)
        if not locations:
            return asdict(
                RemoveResult(
                    success=False,
                    server_name=server_name,
                    message=_NO_CLIENT_MSG,
                )
            )

        if len(locations) == 1:
            return _remove_single(server_name, locations[0])

        return _remove_multi(server_name, locations)

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


def _remove_single(server_name: str, location: object) -> dict[str, object]:
    """Remove a server from a single client config."""
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
                f"Server '{server_name}' removed from "
                f"{location.client.value} ({location.scope}) at {location.path}. "
                "Restart your MCP client to apply."
            ),
        )
    )


def _remove_multi(server_name: str, locations: list[object]) -> dict[str, object]:
    """Remove a server from multiple client configs."""
    per_client: list[dict[str, object]] = []
    removed_count = 0

    for loc in locations:
        try:
            removed = remove_server_config(Path(loc.path), server_name)
            if removed is not None:
                per_client.append(
                    {
                        "client": loc.client.value,
                        "scope": loc.scope,
                        "config_file": loc.path,
                        "success": True,
                        "removed": True,
                    }
                )
                removed_count += 1
            else:
                per_client.append(
                    {
                        "client": loc.client.value,
                        "scope": loc.scope,
                        "config_file": loc.path,
                        "success": True,
                        "removed": False,
                        "message": f"Server '{server_name}' not found in this config.",
                    }
                )
        except McpTapError as exc:
            per_client.append(
                {
                    "client": loc.client.value,
                    "scope": loc.scope,
                    "config_file": loc.path,
                    "success": False,
                    "error": str(exc),
                }
            )

    clients_removed = [r["client"] for r in per_client if r.get("removed")]

    result = asdict(
        RemoveResult(
            success=removed_count > 0,
            server_name=server_name,
            config_file=", ".join(r["config_file"] for r in per_client if r.get("removed")),
            message=(
                f"Server '{server_name}' removed from {removed_count}/{len(locations)} "
                f"clients ({', '.join(clients_removed) or 'none'}). "
                "Restart your MCP clients to apply."
                if removed_count > 0
                else f"Server '{server_name}' was not found in any of the "
                f"{len(locations)} client configs checked."
            ),
        )
    )
    result["per_client_results"] = per_client
    return result
