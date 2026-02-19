"""configure_server tool -- install, configure, and validate an MCP server."""

from __future__ import annotations

import logging
from dataclasses import asdict
from pathlib import Path

from mcp.server.fastmcp import Context

from mcp_tap.config.detection import detect_clients, resolve_config_path
from mcp_tap.config.writer import write_server_config
from mcp_tap.connection.tester import test_server_connection
from mcp_tap.errors import McpTapError
from mcp_tap.installer.resolver import resolve_installer
from mcp_tap.models import (
    ConfigLocation,
    ConfigureResult,
    MCPClient,
    RegistryType,
    ServerConfig,
)

logger = logging.getLogger(__name__)


async def configure_server(
    server_name: str,
    package_identifier: str,
    ctx: Context,
    client: str = "",
    registry_type: str = "npm",
    version: str = "latest",
    env_vars: str = "",
) -> dict[str, object]:
    """Install an MCP server package, add it to your client config, and verify it works.

    Full end-to-end flow:
    1. Resolves the package installer for the registry type
    2. Installs/verifies the package (fails fast if install fails)
    3. Writes the server entry to your MCP client config file
    4. Validates the server by spawning it and calling list_tools()

    Args:
        server_name: Name for this server in the config (e.g. "postgres").
        package_identifier: The package to run
            (e.g. "@modelcontextprotocol/server-postgres").
        client: Target MCP client. One of "claude_desktop", "claude_code",
            "cursor", "windsurf". If empty, auto-detects.
        registry_type: Package source -- "npm", "pypi", or "oci".
        version: Package version to install. Defaults to "latest".
        env_vars: KEY=VALUE pairs separated by commas for environment
            variables the server needs
            (e.g. "POSTGRES_URL=postgresql://localhost/mydb,API_KEY=sk-...").

    Returns:
        Configuration result showing install status, what was written,
        validation results, and discovered tools.
    """
    try:
        # Step 1: Resolve client config path
        location = _resolve_client_location(client)
        if location is None:
            return asdict(ConfigureResult(
                success=False,
                server_name=server_name,
                config_file="",
                message=(
                    "No MCP client detected. Install Claude Desktop, "
                    "Cursor, or Claude Code first."
                ),
                install_status="skipped",
            ))

        # Step 2: Resolve installer and install the package
        rt = RegistryType(registry_type)
        installer = await resolve_installer(rt)

        await ctx.info(f"Installing {package_identifier} via {rt.value}...")
        install_result = await installer.install(package_identifier, version)

        if not install_result.success:
            return asdict(ConfigureResult(
                success=False,
                server_name=server_name,
                config_file=location.path,
                message=(
                    f"Package installation failed: {install_result.message}. "
                    "Config was NOT written to avoid a broken entry."
                ),
                install_status="failed",
            ))

        install_status = "installed"
        logger.info("Package %s installed successfully", package_identifier)

        # Step 3: Build server config and write atomically
        command, args = installer.build_server_command(package_identifier)
        env = _parse_env_vars(env_vars)
        server_config = ServerConfig(command=command, args=args, env=env)

        write_server_config(
            Path(location.path),
            server_name,
            server_config,
        )

        # Step 4: Validate the connection
        tools_discovered: list[str] = []
        validation_passed = False

        await ctx.info(f"Validating {server_name} connection...")
        test_result = await test_server_connection(
            server_name,
            server_config,
            timeout_seconds=15,
        )

        if test_result.success:
            validation_passed = True
            tools_discovered = list(test_result.tools_discovered)
            tool_summary = (
                f" Discovered {len(tools_discovered)} tools: "
                f"{', '.join(tools_discovered[:10])}"
                f"{'...' if len(tools_discovered) > 10 else ''}."
            )
        else:
            tool_summary = (
                f" Validation warning: {test_result.error}. "
                "The server config was written. You may need to set "
                "environment variables or restart your MCP client."
            )
            logger.warning(
                "Validation failed for %s: %s",
                server_name,
                test_result.error,
            )

        return asdict(ConfigureResult(
            success=True,
            server_name=server_name,
            config_file=location.path,
            message=(
                f"Server '{server_name}' installed and added to "
                f"{location.client.value} config at {location.path}."
                f"{tool_summary} "
                "Restart your MCP client to load it."
            ),
            config_written=server_config.to_dict(),
            install_status=install_status,
            tools_discovered=tools_discovered,
            validation_passed=validation_passed,
        ))

    except McpTapError as exc:
        return asdict(ConfigureResult(
            success=False,
            server_name=server_name,
            config_file="",
            message=str(exc),
            install_status="failed",
        ))
    except Exception as exc:
        await ctx.error(f"Unexpected error in configure_server: {exc}")
        return asdict(ConfigureResult(
            success=False,
            server_name=server_name,
            config_file="",
            message=f"Internal error: {type(exc).__name__}",
            install_status="failed",
        ))


def _resolve_client_location(client: str) -> ConfigLocation | None:
    """Resolve the config file location for the target MCP client.

    Returns None if no client is detected and no explicit client was provided.
    """
    if client:
        return resolve_config_path(MCPClient(client))

    clients = detect_clients()
    if not clients:
        return None
    return clients[0]


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
