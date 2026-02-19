"""Atomic writes to mcp-tap.lock files."""

from __future__ import annotations

import contextlib
import fcntl
import json
import logging
import os
import tempfile
import threading
from datetime import UTC, datetime
from importlib.metadata import version as pkg_version
from pathlib import Path

from mcp_tap.errors import LockfileWriteError
from mcp_tap.lockfile.hasher import compute_tools_hash
from mcp_tap.lockfile.reader import read_lockfile
from mcp_tap.models import LockedConfig, LockedServer, Lockfile, ServerConfig

logger = logging.getLogger(__name__)

_LOCKFILE_NAME = "mcp-tap.lock"
_path_locks: dict[str, threading.Lock] = {}
_path_locks_guard = threading.Lock()


def _get_path_lock(path: Path) -> threading.Lock:
    """Get or create a per-path threading lock for concurrent safety."""
    key = str(path.resolve())
    with _path_locks_guard:
        if key not in _path_locks:
            _path_locks[key] = threading.Lock()
        return _path_locks[key]


def _now_iso() -> str:
    """Return current UTC time as an ISO 8601 string with Z suffix."""
    return datetime.now(tz=UTC).isoformat().replace("+00:00", "Z")


def _mcp_tap_version() -> str:
    """Return a version string like 'mcp-tap@0.2.0' or 'mcp-tap@dev'."""
    try:
        return f"mcp-tap@{pkg_version('mcp-tap')}"
    except Exception:
        return "mcp-tap@dev"


def _lockfile_to_dict(lockfile: Lockfile) -> dict:
    """Serialize Lockfile to a JSON-compatible dict with deterministic ordering."""
    servers: dict[str, dict] = {}
    for name in sorted(lockfile.servers):
        s = lockfile.servers[name]
        servers[name] = {
            "package_identifier": s.package_identifier,
            "registry_type": s.registry_type,
            "version": s.version,
            "integrity": s.integrity,
            "repository_url": s.repository_url,
            "config": {
                "command": s.config.command,
                "args": list(s.config.args),
                "env_keys": sorted(s.config.env_keys),
            },
            "tools": sorted(s.tools),
            "tools_hash": s.tools_hash,
            "installed_at": s.installed_at,
            "verified_at": s.verified_at,
            "verified_healthy": s.verified_healthy,
        }
    return {
        "lockfile_version": lockfile.lockfile_version,
        "generated_by": lockfile.generated_by,
        "generated_at": lockfile.generated_at,
        "servers": servers,
    }


def _atomic_write_lockfile(path: Path, data: dict) -> None:
    """Write lockfile data to disk atomically via tempfile + os.replace."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = None
    tmp_path: str | None = None
    try:
        fd, tmp_path = tempfile.mkstemp(
            dir=str(path.parent), suffix=".tmp", prefix=".mcp-tap-lock_"
        )
        content = json.dumps(data, indent=2, ensure_ascii=False, sort_keys=False) + "\n"
        os.write(fd, content.encode("utf-8"))
        os.close(fd)
        fd = None
        os.replace(tmp_path, str(path))
        tmp_path = None
    except OSError as exc:
        raise LockfileWriteError(f"Failed to write lockfile {path}: {exc}") from exc
    finally:
        if fd is not None:
            os.close(fd)
        if tmp_path is not None:
            with contextlib.suppress(OSError):
                os.unlink(tmp_path)


def write_lockfile(project_path: Path | str, lockfile: Lockfile) -> None:
    """Write the complete lockfile atomically with file locking.

    Uses both a per-path threading lock (for in-process concurrency)
    and fcntl.flock (for cross-process concurrency).
    """
    path = Path(project_path) / _LOCKFILE_NAME
    lock = _get_path_lock(path)
    with lock:
        lock_file_path = path.with_suffix(".lock.lck")
        lock_file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(lock_file_path, "w") as lock_fd:
            fcntl.flock(lock_fd, fcntl.LOCK_EX)
            try:
                data = _lockfile_to_dict(lockfile)
                _atomic_write_lockfile(path, data)
            finally:
                fcntl.flock(lock_fd, fcntl.LOCK_UN)


def add_server_to_lockfile(
    project_path: Path | str,
    name: str,
    package_identifier: str,
    registry_type: str,
    version: str,
    server_config: ServerConfig,
    tools: list[str] | None = None,
    repository_url: str = "",
) -> None:
    """Add or update a server in the lockfile.

    If the lockfile does not exist, it is created. If the server already
    exists, its entry is updated but ``installed_at`` is preserved.

    Args:
        project_path: Root directory of the project.
        name: Server name (key in the servers map).
        package_identifier: Package name from the registry.
        registry_type: One of "npm", "pypi", "oci".
        version: Exact installed version.
        server_config: The runtime server configuration.
        tools: Tool names discovered during validation.
        repository_url: Source repository URL (optional).
    """
    path = Path(project_path)
    existing = read_lockfile(path)

    now = _now_iso()
    tools_list = sorted(tools) if tools else []

    locked_config = LockedConfig(
        command=server_config.command,
        args=list(server_config.args),
        env_keys=sorted(server_config.env.keys()) if server_config.env else [],
    )

    entry = LockedServer(
        package_identifier=package_identifier,
        registry_type=registry_type,
        version=version,
        config=locked_config,
        tools=tools_list,
        tools_hash=compute_tools_hash(tools_list),
        installed_at=(
            existing.servers[name].installed_at
            if existing and name in existing.servers
            else now
        ),
        verified_at=now if tools else None,
        verified_healthy=bool(tools),
        repository_url=repository_url,
    )

    if existing:
        servers = dict(existing.servers)
        servers[name] = entry
        lockfile = Lockfile(
            lockfile_version=1,
            generated_by=_mcp_tap_version(),
            generated_at=now,
            servers=servers,
        )
    else:
        lockfile = Lockfile(
            lockfile_version=1,
            generated_by=_mcp_tap_version(),
            generated_at=now,
            servers={name: entry},
        )

    write_lockfile(path, lockfile)


def remove_server_from_lockfile(project_path: Path | str, name: str) -> bool:
    """Remove a server from the lockfile.

    Returns True if the server was found and removed, False otherwise.
    """
    path = Path(project_path)
    existing = read_lockfile(path)
    if not existing or name not in existing.servers:
        return False

    servers = {k: v for k, v in existing.servers.items() if k != name}
    lockfile = Lockfile(
        lockfile_version=1,
        generated_by=_mcp_tap_version(),
        generated_at=_now_iso(),
        servers=servers,
    )
    write_lockfile(path, lockfile)
    return True


def update_server_verification(
    project_path: Path | str,
    name: str,
    tools: list[str],
    healthy: bool,
) -> None:
    """Update a server's verification status in the lockfile.

    If the lockfile or the server entry does not exist, this is a no-op.
    """
    path = Path(project_path)
    existing = read_lockfile(path)
    if not existing or name not in existing.servers:
        return

    old = existing.servers[name]
    tools_sorted = sorted(tools)

    updated = LockedServer(
        package_identifier=old.package_identifier,
        registry_type=old.registry_type,
        version=old.version,
        integrity=old.integrity,
        repository_url=old.repository_url,
        config=old.config,
        tools=tools_sorted,
        tools_hash=compute_tools_hash(tools_sorted),
        installed_at=old.installed_at,
        verified_at=_now_iso(),
        verified_healthy=healthy,
    )

    servers = dict(existing.servers)
    servers[name] = updated
    lockfile = Lockfile(
        lockfile_version=1,
        generated_by=_mcp_tap_version(),
        generated_at=_now_iso(),
        servers=servers,
    )
    write_lockfile(path, lockfile)
