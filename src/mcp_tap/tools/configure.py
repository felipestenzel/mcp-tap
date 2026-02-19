"""configure_server tool -- install, configure, and validate an MCP server."""

from __future__ import annotations

import logging
from dataclasses import asdict
from pathlib import Path

from mcp.server.fastmcp import Context

from mcp_tap.config.detection import resolve_config_locations
from mcp_tap.config.writer import write_server_config
from mcp_tap.connection.tester import test_server_connection
from mcp_tap.errors import McpTapError
from mcp_tap.installer.resolver import resolve_installer
from mcp_tap.models import (
    ConfigLocation,
    ConfigureResult,
    RegistryType,
    ServerConfig,
)

logger = logging.getLogger(__name__)


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
) -> dict[str, object]:
    """Install an MCP server package, add it to your client config, and verify it works.

    This is the main action tool. It handles the complete setup flow:
    1. Installs the package via npm/pip/docker (fails fast if install fails)
    2. Writes the server entry to your MCP client config file(s)
    3. Validates by spawning the server and calling list_tools()

    Get the package_identifier and registry_type from search_servers results
    or scan_project recommendations.

    If validation fails, the config is still written — the user may need to
    set environment variables or restart their MCP client.

    Args:
        server_name: Name for this server in the config (e.g. "postgres").
            This is how it appears in list_installed and other tools.
        package_identifier: The package to install and run. Get this from
            search_servers results (e.g. "@modelcontextprotocol/server-postgres"
            for npm, "mcp-server-git" for pypi).
        clients: Target MCP client(s). Comma-separated names like
            "claude_desktop,cursor", "all" for every detected client,
            or empty to auto-detect the first available.
        registry_type: Package source — "npm" (default), "pypi", or "oci".
        version: Package version. Defaults to "latest".
        env_vars: Environment variables the server needs, as comma-separated
            KEY=VALUE pairs (e.g. "POSTGRES_URL=postgresql://...,API_KEY=sk-...").
            Check search_servers results for env_vars_required.
        scope: "user" for global config (default), "project" for
            project-scoped config (e.g. .cursor/mcp.json in the project dir).
        project_path: Project directory path. Required when scope="project".

    Returns:
        Result with: success, install_status, config_written, validation_passed,
        tools_discovered. Multi-client calls also include per_client_results.
    """
    try:
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

        # Step 2: Resolve installer and install the package (once)
        rt = RegistryType(registry_type)
        installer = await resolve_installer(rt)

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

        # Step 4: Write config to each target client
        if len(locations) == 1:
            return await _configure_single(server_name, server_config, locations[0], ctx)

        return await _configure_multi(server_name, server_config, locations, ctx)

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
) -> dict[str, object]:
    """Configure a server for a single client. Returns a ConfigureResult dict."""
    write_server_config(Path(location.path), server_name, server_config)

    # Validate the connection
    tools_discovered, validation_passed, tool_summary = await _validate(
        server_name, server_config, ctx
    )

    return asdict(
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
            config_written=server_config.to_dict(),
            install_status="installed",
            tools_discovered=tools_discovered,
            validation_passed=validation_passed,
        )
    )


async def _configure_multi(
    server_name: str,
    server_config: ServerConfig,
    locations: list[ConfigLocation],
    ctx: Context,
) -> dict[str, object]:
    """Configure a server for multiple clients. Returns aggregated result."""
    # Validate once (same binary, same config)
    tools_discovered, validation_passed, tool_summary = await _validate(
        server_name, server_config, ctx
    )

    per_client: list[dict[str, object]] = []
    success_count = 0

    for loc in locations:
        try:
            write_server_config(Path(loc.path), server_name, server_config)
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
            config_written=server_config.to_dict(),
            install_status="installed",
            tools_discovered=tools_discovered,
            validation_passed=validation_passed,
        )
    )
    result["per_client_results"] = per_client
    return result


async def _validate(
    server_name: str,
    server_config: ServerConfig,
    ctx: Context,
) -> tuple[list[str], bool, str]:
    """Validate a server connection. Returns (tools, passed, summary_text)."""
    await ctx.info(f"Validating {server_name} connection...")
    test_result = await test_server_connection(server_name, server_config, timeout_seconds=15)

    if test_result.success:
        tools = list(test_result.tools_discovered)
        summary = (
            f" Discovered {len(tools)} tools: "
            f"{', '.join(tools[:10])}"
            f"{'...' if len(tools) > 10 else ''}."
        )
        return tools, True, summary

    logger.warning("Validation failed for %s: %s", server_name, test_result.error)
    summary = (
        f" Validation warning: {test_result.error}. "
        "The server config was written. You may need to set "
        "environment variables or restart your MCP client."
    )
    return [], False, summary


def _parse_env_vars(env_vars: str) -> dict[str, str]:
    """Parse comma-separated KEY=VALUE pairs into a dict."""
    env: dict[str, str] = {}
    if not env_vars:
        return env

    for pair in env_vars.split(","):
        pair = pair.strip()
        if "=" in pair:
            key, value = pair.split("=", 1)
            env[key.strip()] = value.strip()
    return env
