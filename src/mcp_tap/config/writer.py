"""Atomic config file writes with merge semantics.

Invariants:
  1. Existing server entries are NEVER modified or removed by configure.
  2. Writes are atomic: write to .tmp, then os.replace().
  3. The full config dict is round-tripped -- unknown keys are preserved.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from mcp_tap.config.reader import read_config
from mcp_tap.errors import ConfigWriteError
from mcp_tap.models import ServerConfig


def write_server_config(
    config_path: Path | str,
    server_name: str,
    server_config: ServerConfig,
    *,
    overwrite_existing: bool = False,
) -> None:
    """Add a server entry to the config file atomically."""
    path = Path(config_path)

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


def remove_server_config(
    config_path: Path | str,
    server_name: str,
) -> dict[str, object] | None:
    """Remove a server from the config file. Returns the removed entry or None."""
    path = Path(config_path)
    raw = read_config(path)
    servers = raw.get("mcpServers", {})

    removed = servers.pop(server_name, None)
    if removed is not None:
        raw["mcpServers"] = servers
        _atomic_write(path, raw)

    return removed


def _atomic_write(path: Path, data: dict[str, object]) -> None:
    """Write JSON atomically: write to .tmp then rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(".tmp")

    try:
        content = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
        tmp_path.write_text(content, encoding="utf-8")
        os.replace(str(tmp_path), str(path))
    except PermissionError as exc:
        raise ConfigWriteError(f"Permission denied writing to {path}: {exc}") from exc
    except OSError as exc:
        raise ConfigWriteError(f"Failed to write {path}: {exc}") from exc
    finally:
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
