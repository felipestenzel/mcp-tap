"""Atomic config file writes with merge semantics.

Invariants:
  1. Existing server entries are NEVER modified or removed by configure.
  2. Writes are atomic: write to unique temp file, then os.replace().
  3. The full config dict is round-tripped -- unknown keys are preserved.
  4. Concurrent writes are safe via threading.Lock (in-process) + fcntl.flock (cross-process).
"""

from __future__ import annotations

import contextlib
import fcntl
import json
import os
import tempfile
import threading
from pathlib import Path

from mcp_tap.config.reader import read_config
from mcp_tap.errors import ConfigWriteError
from mcp_tap.models import HttpServerConfig, ServerConfig

_path_locks: dict[str, threading.Lock] = {}
_path_locks_guard = threading.Lock()


def _get_path_lock(path: Path) -> threading.Lock:
    """Get or create an in-process threading.Lock for *path*."""
    key = str(path.resolve())
    with _path_locks_guard:
        if key not in _path_locks:
            _path_locks[key] = threading.Lock()
        return _path_locks[key]


def write_server_config(
    config_path: Path | str,
    server_name: str,
    server_config: ServerConfig | HttpServerConfig,
    *,
    overwrite_existing: bool = False,
) -> None:
    """Add a server entry to the config file atomically."""
    path = Path(config_path)
    lock = _get_path_lock(path)

    with lock:
        _locked_write(path, server_name, server_config, overwrite_existing=overwrite_existing)


def _locked_write(
    path: Path,
    server_name: str,
    server_config: ServerConfig | HttpServerConfig,
    *,
    overwrite_existing: bool = False,
) -> None:
    """Read-modify-write under an inter-process file lock."""
    lock_path = path.with_suffix(".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    with open(lock_path, "w") as lock_fd:
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        try:
            raw = read_config(path)
            servers = raw.get("mcpServers", {})

            if server_name in servers and not overwrite_existing:
                raise ConfigWriteError(
                    f"Server '{server_name}' already exists in {path}. "
                    "Use remove_server first, then configure again."
                )

            servers[server_name] = server_config.to_dict()
            raw["mcpServers"] = servers
            _atomic_write(path, raw)
        finally:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)


def remove_server_config(
    config_path: Path | str,
    server_name: str,
) -> dict[str, object] | None:
    """Remove a server from the config file. Returns the removed entry or None."""
    path = Path(config_path)
    lock = _get_path_lock(path)

    with lock:
        return _locked_remove(path, server_name)


def _locked_remove(path: Path, server_name: str) -> dict[str, object] | None:
    """Remove under an inter-process file lock."""
    lock_path = path.with_suffix(".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    with open(lock_path, "w") as lock_fd:
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        try:
            raw = read_config(path)
            servers = raw.get("mcpServers", {})

            removed = servers.pop(server_name, None)
            if removed is not None:
                raw["mcpServers"] = servers
                _atomic_write(path, raw)

            return removed
        finally:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)


def _atomic_write(path: Path, data: dict[str, object]) -> None:
    """Write JSON atomically: write to unique temp file then rename."""
    path.parent.mkdir(parents=True, exist_ok=True)

    fd = None
    tmp_path: str | None = None
    try:
        fd, tmp_path = tempfile.mkstemp(
            dir=str(path.parent),
            suffix=".tmp",
            prefix=f".{path.stem}_",
        )
        content = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
        os.write(fd, content.encode("utf-8"))
        os.close(fd)
        fd = None
        os.replace(tmp_path, str(path))
        tmp_path = None
    except PermissionError as exc:
        raise ConfigWriteError(f"Permission denied writing to {path}: {exc}") from exc
    except OSError as exc:
        raise ConfigWriteError(f"Failed to write {path}: {exc}") from exc
    finally:
        if fd is not None:
            os.close(fd)
        if tmp_path is not None:
            with contextlib.suppress(OSError):
                os.unlink(tmp_path)
