"""Read and parse mcp-tap.lock files."""

from __future__ import annotations

import json
from pathlib import Path

from mcp_tap.errors import LockfileReadError
from mcp_tap.models import LockedConfig, LockedServer, Lockfile

_LOCKFILE_NAME = "mcp-tap.lock"


def read_lockfile(project_path: Path | str) -> Lockfile | None:
    """Read the lockfile from a project directory.

    Returns None if the file does not exist or is empty.

    Raises:
        LockfileReadError: If the file contains invalid JSON or an
            unsupported lockfile version.
    """
    path = Path(project_path) / _LOCKFILE_NAME
    if not path.exists():
        return None
    try:
        text = path.read_text(encoding="utf-8")
        if not text.strip():
            return None
        data = json.loads(text)
        return parse_lockfile(data)
    except json.JSONDecodeError as exc:
        raise LockfileReadError(f"Invalid JSON in {path}: {exc}") from exc


def parse_lockfile(data: dict) -> Lockfile:
    """Parse raw JSON dict into a Lockfile domain model.

    Raises:
        LockfileReadError: If the lockfile version is unsupported.
    """
    version = data.get("lockfile_version", 0)
    if version != 1:
        raise LockfileReadError(
            f"Unsupported lockfile version {version}. Update mcp-tap to read this lockfile."
        )

    servers: dict[str, LockedServer] = {}
    for name, entry in data.get("servers", {}).items():
        config_raw = entry.get("config", {})
        config = LockedConfig(
            command=config_raw.get("command", ""),
            args=config_raw.get("args", []),
            env_keys=config_raw.get("env_keys", []),
        )
        servers[name] = LockedServer(
            package_identifier=entry.get("package_identifier", ""),
            registry_type=entry.get("registry_type", "npm"),
            version=entry.get("version", ""),
            integrity=entry.get("integrity"),
            repository_url=entry.get("repository_url", ""),
            config=config,
            tools=entry.get("tools", []),
            tools_hash=entry.get("tools_hash"),
            installed_at=entry.get("installed_at", ""),
            verified_at=entry.get("verified_at"),
            verified_healthy=entry.get("verified_healthy", False),
        )

    return Lockfile(
        lockfile_version=version,
        generated_by=data.get("generated_by", ""),
        generated_at=data.get("generated_at", ""),
        servers=servers,
    )
