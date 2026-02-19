"""Detect tool name conflicts across configured MCP servers."""

from __future__ import annotations

from mcp_tap.models import ServerHealth, ToolConflict


def detect_tool_conflicts(server_healths: list[ServerHealth]) -> list[ToolConflict]:
    """Find tools that appear in more than one healthy server.

    Only considers healthy servers (those with a populated tools list).
    Returns a list of ToolConflict, one per duplicated tool name,
    sorted alphabetically by tool name.

    Args:
        server_healths: Health status entries from a batch health check.

    Returns:
        Conflicts where a tool name appears in two or more servers.
    """
    tool_to_servers: dict[str, list[str]] = {}
    for health in server_healths:
        if health.status != "healthy" or not health.tools:
            continue
        for tool in health.tools:
            tool_to_servers.setdefault(tool, []).append(health.name)

    return [
        ToolConflict(tool_name=tool, servers=servers)
        for tool, servers in sorted(tool_to_servers.items())
        if len(servers) > 1
    ]
