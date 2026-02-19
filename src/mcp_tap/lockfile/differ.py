"""Compare lockfile state against actual installed servers and health results."""

from __future__ import annotations

from mcp_tap.lockfile.hasher import compute_tools_hash
from mcp_tap.models import (
    DriftEntry,
    DriftSeverity,
    DriftType,
    InstalledServer,
    LockedServer,
    Lockfile,
    ServerHealth,
)


def diff_lockfile(
    lockfile: Lockfile,
    installed: list[InstalledServer],
    healths: list[ServerHealth] | None = None,
) -> list[DriftEntry]:
    """Compare locked state against actual installed servers and health results.

    Checks performed:
    - Server in lockfile but not installed -> MISSING (warning)
    - Server installed but not in lockfile -> EXTRA (info)
    - Tools hash mismatch -> TOOLS_CHANGED (error)
    - Config command/args mismatch -> CONFIG_CHANGED (warning)
    """
    drift: list[DriftEntry] = []
    installed_names = {s.name for s in installed}
    health_by_name = {h.name: h for h in (healths or [])}

    # Check each locked server against installed state
    for name, locked in lockfile.servers.items():
        if name not in installed_names:
            drift.append(
                DriftEntry(
                    server=name,
                    drift_type=DriftType.MISSING,
                    detail=f"Server '{name}' is in lockfile but not in client config.",
                    severity=DriftSeverity.WARNING,
                )
            )
            continue

        # Find matching installed server
        installed_server = next(s for s in installed if s.name == name)

        # Check config drift (command and args)
        drift.extend(_check_config_drift(name, locked, installed_server))

        # Check tools drift if health data is available
        health = health_by_name.get(name)
        if health and health.status == "healthy" and locked.tools:
            drift.extend(_check_tools_drift(name, locked, health))

    # Check for extra servers (installed but not locked)
    locked_names = set(lockfile.servers)
    for server in installed:
        if server.name not in locked_names:
            drift.append(
                DriftEntry(
                    server=server.name,
                    drift_type=DriftType.EXTRA,
                    detail=(f"Server '{server.name}' is in client config but not in lockfile."),
                    severity=DriftSeverity.INFO,
                )
            )

    return drift


def _check_config_drift(
    name: str,
    locked: LockedServer,
    installed: InstalledServer,
) -> list[DriftEntry]:
    """Check if command/args have drifted from locked config."""
    drift: list[DriftEntry] = []
    locked_cmd = locked.config.command
    locked_args = list(locked.config.args)
    installed_cmd = installed.config.command
    installed_args = list(installed.config.args)

    if locked_cmd != installed_cmd or locked_args != installed_args:
        drift.append(
            DriftEntry(
                server=name,
                drift_type=DriftType.CONFIG_CHANGED,
                detail=(
                    f"Locked config: {locked_cmd} {locked_args} | "
                    f"Installed config: {installed_cmd} {installed_args}"
                ),
                severity=DriftSeverity.WARNING,
            )
        )
    return drift


def _check_tools_drift(
    name: str,
    locked: LockedServer,
    health: ServerHealth,
) -> list[DriftEntry]:
    """Check if discovered tools differ from locked tools."""
    drift: list[DriftEntry] = []
    current_tools = sorted(health.tools)
    current_hash = compute_tools_hash(current_tools)

    if current_hash != locked.tools_hash:
        locked_tools = sorted(locked.tools)
        added = sorted(set(current_tools) - set(locked_tools))
        removed = sorted(set(locked_tools) - set(current_tools))

        parts = []
        if added:
            parts.append(f"added: {added}")
        if removed:
            parts.append(f"removed: {removed}")
        detail = f"Tools changed for '{name}'. {', '.join(parts)}"

        drift.append(
            DriftEntry(
                server=name,
                drift_type=DriftType.TOOLS_CHANGED,
                detail=detail,
                severity=DriftSeverity.ERROR,
            )
        )
    return drift
