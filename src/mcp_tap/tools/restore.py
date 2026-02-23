"""restore tool -- recreate MCP server setup from lockfile."""

from __future__ import annotations

import logging
from pathlib import Path

from mcp.server.fastmcp import Context

from mcp_tap.config.detection import resolve_config_locations
from mcp_tap.config.matching import find_matching_installed_server
from mcp_tap.config.reader import parse_servers, read_config
from mcp_tap.config.writer import write_server_config
from mcp_tap.connection.base import ConnectionTesterPort
from mcp_tap.errors import McpTapError
from mcp_tap.installer.base import InstallerResolverPort
from mcp_tap.lockfile.reader import read_lockfile
from mcp_tap.models import (
    ConfigLocation,
    InstalledServer,
    LockedServer,
    Lockfile,
    RegistryType,
    ServerConfig,
)
from mcp_tap.tools._helpers import get_context

logger = logging.getLogger(__name__)

_LOCKFILE_NAME = "mcp-tap.lock"


async def restore(
    project_path: str,
    ctx: Context,
    client: str = "",
    dry_run: bool = False,
) -> dict[str, object]:
    """Recreate MCP server configurations from a lockfile.

    Reads ``mcp-tap.lock`` from the project directory and reinstalls each
    server into the target MCP client config. Environment variable values
    are NOT stored in the lockfile, so the user must set them manually.

    Args:
        project_path: Root directory of the project containing ``mcp-tap.lock``.
        client: Target MCP client(s). Comma-separated names like
            ``"claude_desktop,cursor"``, ``"all"`` for every detected client,
            or empty to auto-detect the first available.
        dry_run: When True, show what would be installed without actually
            installing or writing config.

    Returns:
        Restore result with per-server status, required env vars, and
        overall success.
    """
    try:
        app = get_context(ctx)

        path = Path(project_path)
        lockfile_path = path / _LOCKFILE_NAME

        # Read lockfile
        lockfile = read_lockfile(path)
        if lockfile is None:
            return {
                "success": False,
                "error": f"No lockfile found at {lockfile_path}.",
                "hint": (
                    "Run configure_server with project_path to create one, "
                    "or check that the path is correct."
                ),
            }

        if not lockfile.servers:
            return {
                "success": True,
                "message": "Lockfile exists but contains no servers.",
                "lockfile_path": str(lockfile_path),
                "restored": [],
            }

        # Resolve target config locations
        locations = resolve_config_locations(client, scope="user", project_path=project_path)
        if not locations:
            return {
                "success": False,
                "error": (
                    "No MCP client detected. Install Claude Desktop, Cursor, or Claude Code first."
                ),
            }

        # Dry run: just report what would happen
        if dry_run:
            return _build_dry_run_result(lockfile, locations, lockfile_path)

        installed_servers = _read_installed_servers(locations)

        # Restore each server
        results: list[dict[str, object]] = []
        all_env_keys: list[dict[str, object]] = []

        for name, locked in lockfile.servers.items():
            existing = _find_existing_server(name, locked, installed_servers)
            if existing is not None:
                results.append(
                    {
                        "server": name,
                        "success": True,
                        "status": "already_installed",
                        "installed_as": existing.name,
                        "package": locked.package_identifier,
                        "version": locked.version,
                        "message": (
                            f"Server already installed as '{existing.name}' in "
                            f"{existing.source_file}. Skipped reinstall."
                        ),
                    }
                )
                continue

            result = await _restore_server(
                name,
                locked,
                locations,
                ctx,
                app.installer_resolver,
                app.connection_tester,
            )
            results.append(result)

            # Collect env vars that need manual setup
            if locked.config.env_keys:
                all_env_keys.append(
                    {
                        "server": name,
                        "env_keys": locked.config.env_keys,
                    }
                )

        success_count = sum(1 for r in results if r.get("success"))
        overall_success = success_count > 0

        output: dict[str, object] = {
            "success": overall_success,
            "lockfile_path": str(lockfile_path),
            "total": len(results),
            "restored": success_count,
            "failed": len(results) - success_count,
            "servers": results,
            "clients": [loc.client.value for loc in locations],
        }

        if all_env_keys:
            output["env_vars_needed"] = all_env_keys
            output["env_hint"] = (
                "The lockfile does not store env var values. "
                "Set the listed environment variables in your client config "
                "or shell environment."
            )

        return output

    except McpTapError as exc:
        return {"success": False, "error": str(exc)}
    except Exception as exc:
        await ctx.error(f"Unexpected error in restore: {exc}")
        return {"success": False, "error": f"Internal error: {type(exc).__name__}"}


def _read_installed_servers(locations: list[ConfigLocation]) -> list[InstalledServer]:
    """Read currently installed servers from all target config locations."""
    installed: list[InstalledServer] = []
    for loc in locations:
        try:
            raw = read_config(Path(loc.path))
            installed.extend(parse_servers(raw, source_file=loc.path))
        except Exception:
            logger.debug("Failed to read installed servers from %s", loc.path, exc_info=True)
    return installed


def _find_existing_server(
    name: str,
    locked: LockedServer,
    installed_servers: list[InstalledServer],
) -> InstalledServer | None:
    """Find an existing installed server matching this lockfile entry."""
    return find_matching_installed_server(name, locked, installed_servers)


async def _restore_server(
    name: str,
    locked: LockedServer,
    locations: list[ConfigLocation],
    ctx: Context,
    installer_resolver: InstallerResolverPort,
    connection_tester: ConnectionTesterPort,
) -> dict[str, object]:
    """Restore a single server from its locked entry."""
    try:
        await ctx.info(f"Restoring {name}...")

        # Resolve installer
        rt = RegistryType(locked.registry_type)
        installer = await installer_resolver.resolve_installer(rt)

        # Install the package at the locked version
        install_result = await installer.install(locked.package_identifier, locked.version)

        if not install_result.success:
            return {
                "server": name,
                "success": False,
                "error": f"Install failed: {install_result.message}",
            }

        # Build server config from locked entry
        server_config = ServerConfig(
            command=locked.config.command,
            args=list(locked.config.args),
            env={},  # env values are never in lockfile
        )

        # Write config to each target client
        for loc in locations:
            write_server_config(
                Path(loc.path),
                name,
                server_config,
                overwrite_existing=True,
            )

        # Validate connection
        test_result = await connection_tester.test_server_connection(
            name, server_config, timeout_seconds=15
        )

        return {
            "server": name,
            "success": True,
            "package": locked.package_identifier,
            "version": locked.version,
            "validation_passed": test_result.success,
            "tools_discovered": list(test_result.tools_discovered),
            "config_written_to": [loc.path for loc in locations],
        }

    except McpTapError as exc:
        return {"server": name, "success": False, "error": str(exc)}
    except Exception as exc:
        logger.debug("Failed to restore %s: %s", name, exc, exc_info=True)
        return {
            "server": name,
            "success": False,
            "error": f"Internal error: {type(exc).__name__}",
        }


def _build_dry_run_result(
    lockfile: Lockfile,
    locations: list[ConfigLocation],
    lockfile_path: Path,
) -> dict[str, object]:
    """Build a dry-run result showing what would be restored."""
    servers = []
    for name, locked in lockfile.servers.items():
        servers.append(
            {
                "server": name,
                "package": locked.package_identifier,
                "registry_type": locked.registry_type,
                "version": locked.version,
                "command": locked.config.command,
                "args": list(locked.config.args),
                "env_keys": locked.config.env_keys,
            }
        )
    return {
        "success": True,
        "dry_run": True,
        "lockfile_path": str(lockfile_path),
        "total": len(servers),
        "servers": servers,
        "target_clients": [loc.client.value for loc in locations],
        "message": "Dry run complete. No changes were made.",
    }
