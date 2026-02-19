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
from mcp_tap.healing.retry import heal_and_retry
from mcp_tap.models import (
    ConnectionTestResult,
    HealthReport,
    InstalledServer,
    MCPClient,
    ServerHealth,
)


async def check_health(
    ctx: Context,
    client: str | None = None,
    timeout_seconds: int = 15,
    auto_heal: bool = False,
) -> dict[str, object]:
    """Check the health of all configured MCP servers at once.

    Reads every server from your MCP client config, tests them all
    concurrently (spawns each, connects via MCP protocol, calls
    list_tools()), and returns a health report.

    Use this after configure_server to verify everything is working,
    or as a periodic health check. For unhealthy servers, try
    remove_server followed by configure_server to reinstall.

    Args:
        client: Which MCP client's config to check. One of
            "claude_desktop", "claude_code", "cursor", "windsurf".
            Auto-detects if not specified.
        timeout_seconds: Max seconds to wait per server (clamped to 5-60).
            Default 15. Increase if servers are slow to start.
        auto_heal: When True, attempt to diagnose and fix each unhealthy
            server automatically. Healing results are included in each
            server's entry in the report.

    Returns:
        Health report with: client, config_file, total/healthy/unhealthy
        counts, and per-server details (status, tools count, error).
        When auto_heal is True, unhealthy servers include a "healing" key.
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

        # Attempt healing for unhealthy servers if requested
        healing_details: dict[str, dict[str, object]] = {}
        if auto_heal:
            server_healths, healing_details = await _heal_unhealthy(
                servers,
                server_healths,
                timeout,
                ctx,
            )

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
        result = asdict(report)

        if healing_details:
            result["healing_details"] = healing_details

        return result

    except McpTapError as exc:
        return {"success": False, "error": str(exc)}
    except Exception as exc:
        await ctx.error(f"Unexpected error in check_health: {exc}")
        return {"success": False, "error": f"Internal error: {type(exc).__name__}"}


_MAX_CONCURRENT_CHECKS = 5


async def _check_all_servers(
    servers: list[InstalledServer],
    timeout_seconds: int,
) -> list[ServerHealth]:
    """Run health checks on all servers concurrently.

    Uses asyncio.gather with return_exceptions=True so that one server's
    failure does not prevent checking the rest.
    Limits concurrency to _MAX_CONCURRENT_CHECKS to avoid resource exhaustion.
    """
    sem = asyncio.Semaphore(_MAX_CONCURRENT_CHECKS)

    async def _limited_check(server: InstalledServer) -> ServerHealth:
        async with sem:
            return await _check_single_server(server, timeout_seconds)

    tasks = [_limited_check(server) for server in servers]
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


async def _heal_unhealthy(
    servers: list[InstalledServer],
    healths: list[ServerHealth],
    timeout_seconds: int,
    ctx: Context,
) -> tuple[list[ServerHealth], dict[str, dict[str, object]]]:
    """Attempt healing for each unhealthy server.

    Returns updated healths list and a dict of healing details keyed
    by server name.
    """
    updated: list[ServerHealth] = []
    details: dict[str, dict[str, object]] = {}

    for server, health in zip(servers, healths, strict=True):
        if health.status == "healthy":
            updated.append(health)
            continue

        await ctx.info(f"Attempting self-healing for {server.name}...")

        error_result = ConnectionTestResult(
            success=False,
            server_name=server.name,
            error=health.error,
        )

        healing_result = await heal_and_retry(
            server.name,
            server.config,
            error_result,
            timeout_seconds=timeout_seconds,
        )

        details[server.name] = {
            "healed": healing_result.fixed,
            "attempts_count": len(healing_result.attempts),
            "user_action_needed": healing_result.user_action_needed,
        }

        if healing_result.fixed and healing_result.fixed_config is not None:
            # Re-check with healed config
            recheck = await test_server_connection(
                server.name,
                healing_result.fixed_config,
                timeout_seconds=timeout_seconds,
            )
            if recheck.success:
                updated.append(
                    ServerHealth(
                        name=server.name,
                        status="healthy",
                        tools_count=len(recheck.tools_discovered),
                        tools=recheck.tools_discovered,
                    )
                )
                details[server.name]["fixed_config"] = healing_result.fixed_config.to_dict()
                continue

        updated.append(health)

    return updated, details
