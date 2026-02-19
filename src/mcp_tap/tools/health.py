"""check_health tool -- batch health check for all configured MCP servers."""

from __future__ import annotations

import asyncio
from dataclasses import asdict
from pathlib import Path

from mcp.server.fastmcp import Context

from mcp_tap.config.detection import detect_clients, resolve_config_path
from mcp_tap.config.reader import parse_servers, read_config
from mcp_tap.connection.tester import test_server_connection
from mcp_tap.errors import McpTapError
from mcp_tap.models import (
    HealthReport,
    InstalledServer,
    MCPClient,
    ServerHealth,
)


async def check_health(
    ctx: Context,
    client: str | None = None,
    timeout_seconds: int = 15,
) -> dict[str, object]:
    """Check the health of all installed MCP servers.

    Reads all configured servers from your MCP client config, tests each one
    concurrently by spawning it and calling list_tools(), and returns a health
    report showing which servers are healthy, unhealthy, or timed out.

    Args:
        client: Which MCP client's config to check. One of "claude_desktop",
            "claude_code", "cursor", "windsurf". Auto-detects if not specified.
        timeout_seconds: How long to wait for each server to respond (5-60).

    Returns:
        Health report with total/healthy/unhealthy counts and per-server details.
    """
    try:
        if client:
            location = resolve_config_path(MCPClient(client))
        else:
            clients = detect_clients()
            if not clients:
                return asdict(
                    HealthReport(
                        client="none",
                        config_file="",
                        total=0,
                        healthy=0,
                        unhealthy=0,
                    )
                ) | {"message": "No MCP client detected on this machine."}

            location = clients[0]

        raw = read_config(Path(location.path))
        servers = parse_servers(raw, source_file=location.path)

        if not servers:
            return asdict(
                HealthReport(
                    client=location.client.value,
                    config_file=location.path,
                    total=0,
                    healthy=0,
                    unhealthy=0,
                )
            ) | {"message": "No MCP servers configured."}

        timeout = max(5, min(timeout_seconds, 60))

        server_healths = await _check_all_servers(servers, timeout)

        healthy_count = sum(1 for s in server_healths if s.status == "healthy")
        unhealthy_count = len(server_healths) - healthy_count

        report = HealthReport(
            client=location.client.value,
            config_file=location.path,
            total=len(server_healths),
            healthy=healthy_count,
            unhealthy=unhealthy_count,
            servers=server_healths,
        )
        return asdict(report)

    except McpTapError as exc:
        return {"success": False, "error": str(exc)}
    except Exception as exc:
        await ctx.error(f"Unexpected error in check_health: {exc}")
        return {"success": False, "error": f"Internal error: {type(exc).__name__}"}


async def _check_all_servers(
    servers: list[InstalledServer],
    timeout_seconds: int,
) -> list[ServerHealth]:
    """Run health checks on all servers concurrently.

    Uses asyncio.gather with return_exceptions=True so that one server's
    failure does not prevent checking the rest.
    """
    tasks = [_check_single_server(server, timeout_seconds) for server in servers]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    healths: list[ServerHealth] = []
    for server, result in zip(servers, results, strict=True):
        if isinstance(result, BaseException):
            healths.append(
                ServerHealth(
                    name=server.name,
                    status="unhealthy",
                    error=f"{type(result).__name__}: {result}",
                )
            )
        else:
            healths.append(result)

    return healths


async def _check_single_server(
    server: InstalledServer,
    timeout_seconds: int,
) -> ServerHealth:
    """Check one server and return its ServerHealth."""
    result = await test_server_connection(
        server.name,
        server.config,
        timeout_seconds=timeout_seconds,
    )

    if result.success:
        return ServerHealth(
            name=server.name,
            status="healthy",
            tools_count=len(result.tools_discovered),
            tools=result.tools_discovered,
        )

    # Distinguish timeout from other errors
    status = "timeout" if "did not respond within" in result.error else "unhealthy"
    return ServerHealth(
        name=server.name,
        status=status,
        error=result.error,
    )
