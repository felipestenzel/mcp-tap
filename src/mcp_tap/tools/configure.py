"""configure_server tool -- install, configure, and validate an MCP server."""

from __future__ import annotations

import logging
import re
from dataclasses import asdict
from pathlib import Path

from mcp.server.fastmcp import Context

from mcp_tap.benchmark.production_feedback import emit_recommendation_decision
from mcp_tap.config.detection import client_supports_http_native, resolve_config_locations
from mcp_tap.config.writer import write_server_config
from mcp_tap.connection.base import ConnectionTesterPort
from mcp_tap.errors import McpTapError
from mcp_tap.healing.base import HealingOrchestratorPort
from mcp_tap.models import (
    ConfigLocation,
    ConfigureResult,
    ConnectionTestResult,
    HttpServerConfig,
    RegistryType,
    SecurityReport,
    ServerConfig,
)
from mcp_tap.security.base import SecurityGatePort
from mcp_tap.tools._helpers import get_context

logger = logging.getLogger(__name__)

_HTTP_REGISTRY_TYPES = frozenset({"streamable-http", "http", "sse"})


def _is_http_transport(package_identifier: str, registry_type: str) -> bool:
    """Detect whether the server uses HTTP transport (remote, no install needed).

    Returns True when the package_identifier is a URL or the registry_type
    indicates a remote transport protocol.
    """
    return (
        package_identifier.startswith(("https://", "http://"))
        or registry_type in _HTTP_REGISTRY_TYPES
    )


async def configure_server(
    server_name: str,
    package_identifier: str,
    ctx: Context,
    clients: str = "",
    registry_type: str = "npm",
    version: str = "latest",
    env_vars: str = "",
    scope: str = "user",
    project_path: str = "",
    feedback_query_id: str = "",
    dry_run: bool = False,
) -> dict[str, object]:
    """Install an MCP server package, add it to your client config, and verify it works.

    This is the main action tool. It handles the complete setup flow:
    1. Installs the package via npm/pip/docker (fails fast if install fails)
    2. Validates by spawning the server and calling list_tools()
    3. Writes the server entry to your MCP client config file(s) only if validation passes

    For HTTP transport servers (streamable-http, SSE), the install step is
    skipped and the server is configured via the ``mcp-remote`` bridge.
    Pass the server URL as ``package_identifier`` (e.g. ``https://mcp.vercel.com``)
    or set ``registry_type`` to ``"streamable-http"``, ``"http"``, or ``"sse"``.

    Get the package_identifier and registry_type from search_servers results
    or scan_project recommendations.

    If validation fails, the config is NOT written to avoid broken entries.
    The user should fix the issue and retry.

    When ``dry_run=True``, mcp-tap performs install + validation preflight but
    does NOT write any client config, lockfile, or telemetry acceptance event.

    Args:
        server_name: Name for this server in the config (e.g. "postgres").
            This is how it appears in list_installed and other tools.
        package_identifier: The package to install and run. Get this from
            search_servers results (e.g. "@modelcontextprotocol/server-postgres"
            for npm, "mcp-server-git" for pypi), or a URL for HTTP transport
            servers (e.g. "https://mcp.vercel.com").
        clients: Target MCP client(s). Comma-separated names like
            "claude_desktop,cursor", "all" for every detected client,
            or empty to auto-detect the first available.
        registry_type: Package source — "npm" (default), "pypi", "oci",
            "streamable-http", "http", or "sse".
        version: Package version. Defaults to "latest".
        env_vars: Environment variables the server needs, as comma-separated
            KEY=VALUE pairs (e.g. "POSTGRES_URL=postgresql://...,API_KEY=sk-...").
            Check search_servers results for env_vars_required.
        scope: "user" for global config (default), "project" for
            project-scoped config (e.g. .cursor/mcp.json in the project dir).
        project_path: Project directory path. Required when scope="project".
        feedback_query_id: Optional query_id from scan/search telemetry event
            so accepted recommendations can be linked to shown rankings.
        dry_run: When True, run preflight only (install/validate) and return
            what would be written without touching client config files.

    Returns:
        Result with: success, install_status, config_written, validation_passed,
        tools_discovered. Multi-client calls also include per_client_results.
    """
    try:
        app = get_context(ctx)

        # Step 1: Resolve target config locations
        locations = resolve_config_locations(clients, scope=scope, project_path=project_path)
        if not locations:
            return asdict(
                ConfigureResult(
                    success=False,
                    server_name=server_name,
                    config_file="",
                    message=(
                        "No MCP client detected. Install Claude Desktop, "
                        "Cursor, or Claude Code first."
                    ),
                    install_status="skipped",
                )
            )

        # Step 2: For HTTP transport servers, use native config or mcp-remote fallback
        if _is_http_transport(package_identifier, registry_type):
            logger.info("HTTP transport detected for %s", package_identifier)
            await ctx.info("HTTP server detected — checking reachability...")

            env = _parse_env_vars(env_vars)

            # Security gate: URL checked via package_identifier; command is not user-supplied
            security_report = await _run_security_check(
                package_identifier=package_identifier,
                repository_url="",
                command="",
                args=[],
                ctx=ctx,
                security_gate=app.security_gate,
            )
            if security_report and not security_report.passed:
                return asdict(
                    ConfigureResult(
                        success=False,
                        server_name=server_name,
                        config_file="",
                        message=(
                            f"Security gate BLOCKED installation of "
                            f"'{server_name}': "
                            + "; ".join(s.message for s in security_report.blockers)
                        ),
                        install_status="blocked_by_security",
                    )
                )

            # HTTP reachability check (non-blocking — 401/403 = OAuth = reachable)
            http_result = await app.http_reachability.check_reachability(
                server_name, package_identifier, timeout_seconds=10
            )

            if dry_run:
                result = _build_http_dry_run_result(
                    server_name=server_name,
                    url=package_identifier,
                    env=env,
                    locations=locations,
                    registry_type=registry_type,
                    http_result=http_result,
                )
            else:
                # Write per-client config: native HTTP for capable clients, mcp-remote for others
                if len(locations) == 1:
                    result = await _configure_http_single(
                        server_name,
                        package_identifier,
                        env,
                        locations[0],
                        registry_type,
                        ctx,
                        http_result,
                    )
                else:
                    result = await _configure_http_multi(
                        server_name,
                        package_identifier,
                        env,
                        locations,
                        registry_type,
                        ctx,
                        http_result,
                    )

            # Lockfile update: store canonical HTTP form regardless of per-client format
            if project_path and result.get("success") and not dry_run:
                _update_lockfile(
                    project_path=project_path,
                    server_name=server_name,
                    package_identifier=package_identifier,
                    registry_type=registry_type,
                    version=version,
                    server_config=ServerConfig(command="", args=(), env=env),
                    tools=[],
                )

            if result.get("success") and not dry_run:
                _emit_feedback_accepted(
                    server_name=server_name,
                    feedback_query_id=feedback_query_id,
                    project_path=project_path,
                    clients=clients,
                )

            return result

        # Step 2b: Resolve installer and install the package (once)
        rt = RegistryType(registry_type)
        installer = await app.installer_resolver.resolve_installer(rt)

        await ctx.info(f"Installing {package_identifier} via {rt.value}...")
        install_result = await installer.install(package_identifier, version)

        if not install_result.success:
            return asdict(
                ConfigureResult(
                    success=False,
                    server_name=server_name,
                    config_file="",
                    message=(
                        f"Package installation failed: {install_result.message}. "
                        "Config was NOT written to avoid a broken entry."
                    ),
                    install_status="failed",
                )
            )

        logger.info("Package %s installed successfully", package_identifier)

        # Step 3: Build server config
        command, args = installer.build_server_command(package_identifier)
        env = _parse_env_vars(env_vars)
        server_config = ServerConfig(command=command, args=args, env=env)

        # Step 3.5: Run security gate
        security_report = await _run_security_check(
            package_identifier=package_identifier,
            repository_url="",
            command=command,
            args=args,
            ctx=ctx,
            security_gate=app.security_gate,
        )
        if security_report and not security_report.passed:
            return asdict(
                ConfigureResult(
                    success=False,
                    server_name=server_name,
                    config_file="",
                    message=(
                        f"Security gate BLOCKED installation of '{server_name}': "
                        + "; ".join(s.message for s in security_report.blockers)
                        + " Review the package and choose a trusted alternative."
                    ),
                    install_status="blocked_by_security",
                )
            )

        if dry_run:
            if len(locations) == 1:
                result = await _preflight_single(
                    server_name,
                    server_config,
                    locations[0],
                    ctx,
                    app.connection_tester,
                    app.healing,
                )
            else:
                result = await _preflight_multi(
                    server_name,
                    server_config,
                    locations,
                    ctx,
                    app.connection_tester,
                    app.healing,
                )
        else:
            # Step 4: Write config to each target client
            if len(locations) == 1:
                result = await _configure_single(
                    server_name,
                    server_config,
                    locations[0],
                    ctx,
                    app.connection_tester,
                    app.healing,
                )
            else:
                result = await _configure_multi(
                    server_name,
                    server_config,
                    locations,
                    ctx,
                    app.connection_tester,
                    app.healing,
                )

        # Step 5: Update lockfile if project_path is available
        if project_path and result.get("success") and not dry_run:
            _update_lockfile(
                project_path=project_path,
                server_name=server_name,
                package_identifier=package_identifier,
                registry_type=registry_type,
                version=version,
                server_config=server_config,
                tools=result.get("tools_discovered", []),
            )

        if result.get("success") and not dry_run:
            _emit_feedback_accepted(
                server_name=server_name,
                feedback_query_id=feedback_query_id,
                project_path=project_path,
                clients=clients,
            )

        return result

    except McpTapError as exc:
        return asdict(
            ConfigureResult(
                success=False,
                server_name=server_name,
                config_file="",
                message=str(exc),
                install_status="failed",
            )
        )
    except Exception as exc:
        await ctx.error(f"Unexpected error in configure_server: {exc}")
        return asdict(
            ConfigureResult(
                success=False,
                server_name=server_name,
                config_file="",
                message=f"Internal error: {type(exc).__name__}",
                install_status="failed",
            )
        )


async def _configure_single(
    server_name: str,
    server_config: ServerConfig,
    location: ConfigLocation,
    ctx: Context,
    connection_tester: ConnectionTesterPort,
    healing: HealingOrchestratorPort,
) -> dict[str, object]:
    """Configure a server for a single client. Returns a ConfigureResult dict."""
    # Validate the connection BEFORE writing config
    tools_discovered, validation_passed, tool_summary, test_result = await _validate(
        server_name, server_config, ctx, connection_tester
    )

    # Attempt healing if validation failed
    healing_info: dict[str, object] = {}
    effective_config = server_config
    if not validation_passed:
        healed, effective_config, healing_info = await _try_heal(
            server_name, server_config, test_result, ctx, healing
        )
        if healed:
            validation_passed = True
            # Use tools from the last successful heal_and_retry attempt
            # instead of spawning another process
            last_attempt = healing_info.get("attempts_count", 0)
            tool_summary = (
                f" Healed after {last_attempt} attempt(s)."
                " Server is working. See healing details for more info."
            )

    if not validation_passed:
        # Do NOT write config to avoid leaving a broken entry
        result = asdict(
            ConfigureResult(
                success=False,
                server_name=server_name,
                config_file=location.path,
                message=(
                    f"Server '{server_name}' validation failed."
                    f"{tool_summary} "
                    "Config was NOT written to avoid a broken entry."
                ),
                install_status="installed",
                tools_discovered=tools_discovered,
                validation_passed=False,
            )
        )
        if healing_info:
            result["healing"] = healing_info
        return result

    # Validation passed (directly or after healing) — write config
    write_server_config(
        Path(location.path),
        server_name,
        effective_config,
        overwrite_existing=True,
    )

    result = asdict(
        ConfigureResult(
            success=True,
            server_name=server_name,
            config_file=location.path,
            message=(
                f"Server '{server_name}' installed and added to "
                f"{location.client.value} ({location.scope}) at {location.path}."
                f"{tool_summary} "
                "Restart your MCP client to load it."
            ),
            config_written=effective_config.to_dict(),
            install_status="installed",
            tools_discovered=tools_discovered,
            validation_passed=True,
        )
    )
    if healing_info:
        result["healing"] = healing_info
    return result


async def _configure_multi(
    server_name: str,
    server_config: ServerConfig,
    locations: list[ConfigLocation],
    ctx: Context,
    connection_tester: ConnectionTesterPort,
    healing: HealingOrchestratorPort,
) -> dict[str, object]:
    """Configure a server for multiple clients. Returns aggregated result."""
    # Validate once (same binary, same config)
    tools_discovered, validation_passed, tool_summary, test_result = await _validate(
        server_name, server_config, ctx, connection_tester
    )

    # Attempt healing if validation failed
    healing_info: dict[str, object] = {}
    effective_config = server_config
    if not validation_passed:
        healed, effective_config, healing_info = await _try_heal(
            server_name, server_config, test_result, ctx, healing
        )
        if healed:
            validation_passed = True
            last_attempt = healing_info.get("attempts_count", 0)
            tool_summary = (
                f" Healed after {last_attempt} attempt(s)."
                " Server is working. See healing details for more info."
            )

    if not validation_passed:
        # Do NOT write config to avoid leaving broken entries
        result = asdict(
            ConfigureResult(
                success=False,
                server_name=server_name,
                config_file="",
                message=(
                    f"Server '{server_name}' validation failed."
                    f"{tool_summary} "
                    "Config was NOT written to avoid a broken entry."
                ),
                install_status="installed",
                tools_discovered=tools_discovered,
                validation_passed=False,
            )
        )
        if healing_info:
            result["healing"] = healing_info
        return result

    # Validation passed — write config to all target clients
    per_client: list[dict[str, object]] = []
    success_count = 0

    for loc in locations:
        try:
            write_server_config(
                Path(loc.path),
                server_name,
                effective_config,
                overwrite_existing=True,
            )
            per_client.append(
                {
                    "client": loc.client.value,
                    "scope": loc.scope,
                    "config_file": loc.path,
                    "success": True,
                }
            )
            success_count += 1
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

    overall_success = success_count > 0
    clients_ok = [r["client"] for r in per_client if r["success"]]

    result = asdict(
        ConfigureResult(
            success=overall_success,
            server_name=server_name,
            config_file=", ".join(r["config_file"] for r in per_client if r["success"]),
            message=(
                f"Server '{server_name}' configured in {success_count}/{len(locations)} "
                f"clients ({', '.join(clients_ok)}).{tool_summary} "
                "Restart your MCP clients to load it."
            ),
            config_written=effective_config.to_dict(),
            install_status="installed",
            tools_discovered=tools_discovered,
            validation_passed=True,
        )
    )
    result["per_client_results"] = per_client
    if healing_info:
        result["healing"] = healing_info
    return result


def _build_http_server_config_for_location(
    url: str,
    env: dict[str, str],
    location: ConfigLocation,
    registry_type: str,
) -> ServerConfig | HttpServerConfig:
    """Build the best HTTP config for a single client location.

    Clients that support native HTTP config (e.g. Claude Code) get ``HttpServerConfig``.
    All others get a ``ServerConfig`` using the ``mcp-remote`` bridge.
    """
    transport_type = "sse" if registry_type == "sse" else "http"
    if client_supports_http_native(location.client):
        return HttpServerConfig(url=url, transport_type=transport_type, env=env)
    return ServerConfig(command="npx", args=("-y", "mcp-remote", url), env=env)


async def _configure_http_single(
    server_name: str,
    url: str,
    env: dict[str, str],
    location: ConfigLocation,
    registry_type: str,
    ctx: Context,
    http_result: ConnectionTestResult,
) -> dict[str, object]:
    """Configure an HTTP server for a single client. Always writes config."""
    server_config = _build_http_server_config_for_location(url, env, location, registry_type)
    write_server_config(Path(location.path), server_name, server_config, overwrite_existing=True)

    restart_note = "Restart your MCP client to activate."
    oauth_note = " On first use you may need to authenticate via browser (OAuth)."

    if http_result.success:
        msg = (
            f"Server '{server_name}' configured in {location.client.value} "
            f"at {location.path}. {restart_note}{oauth_note}"
        )
    else:
        msg = (
            f"Server '{server_name}' configured in {location.client.value} "
            f"at {location.path}. {restart_note}{oauth_note} "
            f"Note: {http_result.error}"
        )

    return asdict(
        ConfigureResult(
            success=True,
            server_name=server_name,
            config_file=location.path,
            message=msg,
            config_written=server_config.to_dict(),
            install_status="configured",
            tools_discovered=[],
            validation_passed=http_result.success,
        )
    )


async def _configure_http_multi(
    server_name: str,
    url: str,
    env: dict[str, str],
    locations: list[ConfigLocation],
    registry_type: str,
    ctx: Context,
    http_result: ConnectionTestResult,
) -> dict[str, object]:
    """Configure an HTTP server for multiple clients with per-client best config.

    Clients that support native HTTP config receive ``HttpServerConfig``.
    All others receive a ``ServerConfig`` using the ``mcp-remote`` bridge.
    Both config types are written in the same call.
    """
    per_client: list[dict[str, object]] = []
    success_count = 0
    for loc in locations:
        server_config = _build_http_server_config_for_location(url, env, loc, registry_type)
        try:
            write_server_config(Path(loc.path), server_name, server_config, overwrite_existing=True)
            per_client.append(
                {
                    "client": loc.client.value,
                    "scope": loc.scope,
                    "config_file": loc.path,
                    "success": True,
                    "config_written": server_config.to_dict(),
                }
            )
            success_count += 1
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

    overall = success_count > 0
    clients_ok = [r["client"] for r in per_client if r["success"]]
    restart_note = (
        "Restart your MCP clients to activate. "
        "On first use you may need to authenticate via browser (OAuth)."
    )
    msg = (
        f"Server '{server_name}' configured in {success_count}/{len(locations)} "
        f"clients ({', '.join(str(c) for c in clients_ok)}). {restart_note}"
    )
    if not http_result.success:
        msg += f" Note: {http_result.error}"

    # Top-level config_written: first successful client's config as representative
    first_written = next((r["config_written"] for r in per_client if r.get("success")), {})

    result = asdict(
        ConfigureResult(
            success=overall,
            server_name=server_name,
            config_file=", ".join(str(r["config_file"]) for r in per_client if r["success"]),
            message=msg,
            config_written=first_written,
            install_status="configured",
            tools_discovered=[],
            validation_passed=http_result.success,
        )
    )
    result["per_client_results"] = per_client
    return result


def _build_http_dry_run_result(
    *,
    server_name: str,
    url: str,
    env: dict[str, str],
    locations: list[ConfigLocation],
    registry_type: str,
    http_result: ConnectionTestResult,
) -> dict[str, object]:
    """Build dry-run preview for HTTP servers without writing any config files."""
    per_client: list[dict[str, object]] = []
    for loc in locations:
        preview = _build_http_server_config_for_location(url, env, loc, registry_type).to_dict()
        per_client.append(
            {
                "client": loc.client.value,
                "scope": loc.scope,
                "config_file": loc.path,
                "success": http_result.success,
                "config_preview": preview,
            }
        )

    preview_config = per_client[0]["config_preview"] if per_client else {}
    message = (
        f"Dry-run preflight for '{server_name}' completed. "
        "No config file was written."
    )
    if http_result.error:
        message += f" Reachability result: {http_result.error}"

    result = asdict(
        ConfigureResult(
            success=http_result.success,
            server_name=server_name,
            config_file=", ".join(loc.path for loc in locations),
            message=message,
            config_written=preview_config,
            install_status="dry_run",
            tools_discovered=[],
            validation_passed=http_result.success,
        )
    )
    if len(per_client) > 1:
        result["per_client_results"] = per_client
    result["dry_run"] = True
    return result


async def _preflight_single(
    server_name: str,
    server_config: ServerConfig,
    location: ConfigLocation,
    ctx: Context,
    connection_tester: ConnectionTesterPort,
    healing: HealingOrchestratorPort,
) -> dict[str, object]:
    """Run install/validation preflight for one client without writing config."""
    tools_discovered, validation_passed, tool_summary, test_result = await _validate(
        server_name, server_config, ctx, connection_tester
    )

    healing_info: dict[str, object] = {}
    effective_config = server_config
    if not validation_passed:
        healed, effective_config, healing_info = await _try_heal(
            server_name, server_config, test_result, ctx, healing
        )
        if healed:
            validation_passed = True
            last_attempt = healing_info.get("attempts_count", 0)
            tool_summary = (
                f" Healed after {last_attempt} attempt(s)."
                " Server is working. See healing details for more info."
            )

    result = asdict(
        ConfigureResult(
            success=validation_passed,
            server_name=server_name,
            config_file=location.path,
            message=(
                f"Dry-run preflight for '{server_name}' finished."
                f"{tool_summary} Config was NOT written."
            ),
            config_written=effective_config.to_dict(),
            install_status="dry_run",
            tools_discovered=tools_discovered,
            validation_passed=validation_passed,
        )
    )
    if healing_info:
        result["healing"] = healing_info
    result["dry_run"] = True
    return result


async def _preflight_multi(
    server_name: str,
    server_config: ServerConfig,
    locations: list[ConfigLocation],
    ctx: Context,
    connection_tester: ConnectionTesterPort,
    healing: HealingOrchestratorPort,
) -> dict[str, object]:
    """Run install/validation preflight for multiple clients without writing config."""
    tools_discovered, validation_passed, tool_summary, test_result = await _validate(
        server_name, server_config, ctx, connection_tester
    )

    healing_info: dict[str, object] = {}
    effective_config = server_config
    if not validation_passed:
        healed, effective_config, healing_info = await _try_heal(
            server_name, server_config, test_result, ctx, healing
        )
        if healed:
            validation_passed = True
            last_attempt = healing_info.get("attempts_count", 0)
            tool_summary = (
                f" Healed after {last_attempt} attempt(s)."
                " Server is working. See healing details for more info."
            )

    preview = effective_config.to_dict()
    per_client = [
        {
            "client": loc.client.value,
            "scope": loc.scope,
            "config_file": loc.path,
            "success": validation_passed,
            "config_preview": preview,
        }
        for loc in locations
    ]

    result = asdict(
        ConfigureResult(
            success=validation_passed,
            server_name=server_name,
            config_file=", ".join(loc.path for loc in locations),
            message=(
                f"Dry-run preflight for '{server_name}' on {len(locations)} clients finished."
                f"{tool_summary} Config was NOT written."
            ),
            config_written=preview,
            install_status="dry_run",
            tools_discovered=tools_discovered,
            validation_passed=validation_passed,
        )
    )
    result["per_client_results"] = per_client
    if healing_info:
        result["healing"] = healing_info
    result["dry_run"] = True
    return result


async def _validate(
    server_name: str,
    server_config: ServerConfig,
    ctx: Context,
    connection_tester: ConnectionTesterPort,
) -> tuple[list[str], bool, str, ConnectionTestResult]:
    """Validate a server connection.

    Returns:
        Tuple of (tools, passed, summary_text, raw_test_result).
        The raw ConnectionTestResult is returned so callers can pass it
        directly to the healing loop without spawning a redundant process.
    """
    await ctx.info(f"Validating {server_name} connection...")
    test_result = await connection_tester.test_server_connection(
        server_name, server_config, timeout_seconds=15
    )

    if test_result.success:
        tools = list(test_result.tools_discovered)
        summary = (
            f" Discovered {len(tools)} tools: "
            f"{', '.join(tools[:10])}"
            f"{'...' if len(tools) > 10 else ''}."
        )
        return tools, True, summary, test_result

    logger.warning("Validation failed for %s: %s", server_name, test_result.error)
    summary = (
        f" Validation warning: {test_result.error}. "
        "You may need to set environment variables or restart your MCP client."
    )
    return [], False, summary, test_result


async def _try_heal(
    server_name: str,
    server_config: ServerConfig,
    original_error: ConnectionTestResult,
    ctx: Context,
    healing: HealingOrchestratorPort,
) -> tuple[bool, ServerConfig, dict[str, object]]:
    """Attempt self-healing after a validation failure.

    Args:
        server_name: Name of the server to heal.
        server_config: The current server configuration.
        original_error: The ConnectionTestResult from the failed validation.
            Reused directly to avoid spawning a redundant server process.
        ctx: MCP context for progress messages.
        healing: Healing orchestrator adapter for diagnose-fix-retry loop.

    Returns:
        Tuple of (healed, effective_config, healing_info_dict).
        If healed is True, effective_config is the fixed config.
        healing_info_dict is always populated for inclusion in the response.
    """
    await ctx.info(f"Attempting self-healing for {server_name}...")

    healing_result = await healing.heal_and_retry(
        server_name,
        server_config,
        original_error,
    )

    info: dict[str, object] = {
        "healed": healing_result.fixed,
        "attempts_count": len(healing_result.attempts),
        "user_action_needed": healing_result.user_action_needed,
    }

    if healing_result.fixed and healing_result.fixed_config is not None:
        await ctx.info(f"Self-healing succeeded for {server_name}.")
        return True, healing_result.fixed_config, info

    if healing_result.user_action_needed:
        await ctx.info(
            f"Self-healing for {server_name} requires user action: "
            f"{healing_result.user_action_needed}"
        )

    return False, server_config, info


async def _run_security_check(
    package_identifier: str,
    repository_url: str,
    command: str,
    args: list[str],
    ctx: Context,
    security_gate: SecurityGatePort,
) -> SecurityReport | None:
    """Run security gate. Returns None if check fails (non-blocking)."""
    try:
        report = await security_gate.run_security_gate(
            package_identifier=package_identifier,
            repository_url=repository_url,
            command=command,
            args=args,
        )

        if report.warnings:
            for w in report.warnings:
                await ctx.info(f"Security warning: {w.message}")

        return report
    except Exception:
        logger.debug("Security gate check failed (non-blocking)", exc_info=True)
        return None


def _update_lockfile(
    project_path: str,
    server_name: str,
    package_identifier: str,
    registry_type: str,
    version: str,
    server_config: ServerConfig,
    tools: list[str],
) -> None:
    """Best-effort lockfile update after successful configure."""
    try:
        from mcp_tap.lockfile.writer import add_server_to_lockfile

        add_server_to_lockfile(
            project_path=project_path,
            name=server_name,
            package_identifier=package_identifier,
            registry_type=registry_type,
            version=version,
            server_config=server_config,
            tools=tools or None,
        )
    except Exception:
        logger.debug("Failed to update lockfile", exc_info=True)


def _emit_feedback_accepted(
    *,
    server_name: str,
    feedback_query_id: str,
    project_path: str,
    clients: str,
) -> None:
    """Best-effort telemetry event for accepted/configured recommendations."""
    try:
        emit_recommendation_decision(
            decision_type="recommendation_accepted",
            server_name=server_name,
            query_id=feedback_query_id,
            project_path=project_path or "unknown",
            client=clients or "auto",
            metadata={"source": "configure_server"},
        )
    except Exception:
        logger.debug("Failed to emit recommendation_accepted telemetry", exc_info=True)


def _parse_env_vars(env_vars: str) -> dict[str, str]:
    """Parse comma-separated KEY=VALUE pairs into a dict.

    Splits only on commas followed by a KEY= pattern, so values containing
    commas (e.g. ``CONN=host=localhost,port=5432``) are preserved intact.
    """
    env: dict[str, str] = {}
    if not env_vars:
        return env

    # Split on commas that are followed by WORD= (a new key-value pair).
    # This preserves commas inside values.
    parts = re.split(r",(?=\s*[A-Za-z_][A-Za-z0-9_]*\s*=)", env_vars)
    for pair in parts:
        pair = pair.strip()
        if "=" in pair:
            key, value = pair.split("=", 1)
            env[key.strip()] = value.strip()
    return env
