"""Read MCP client config files with schema tolerance.

All config files follow: { "mcpServers": { "<name>": { ... } } }
We read only "mcpServers", preserve everything else on write.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from mcp_tap.errors import ConfigReadError
from mcp_tap.models import HttpServerConfig, InstalledServer, ServerConfig


def read_config(config_path: Path | str) -> dict[str, object]:
    """Read a full MCP client config file.

    Returns the raw dict so the writer can round-trip unknown keys.
    Creates an empty {"mcpServers": {}} if the file doesn't exist.
    """
    path = Path(config_path)
    if not path.exists():
        return {"mcpServers": {}}

    try:
        text = path.read_text(encoding="utf-8")
        if not text.strip():
            return {"mcpServers": {}}
        data = json.loads(text)
        if "mcpServers" not in data:
            data["mcpServers"] = {}
        return data
    except json.JSONDecodeError as exc:
        raise ConfigReadError(
            f"Invalid JSON in {path}: {exc}. Fix the JSON syntax or delete the file to start fresh."
        ) from exc
    except PermissionError as exc:
        raise ConfigReadError(f"Permission denied reading {path}: {exc}") from exc


async def aread_config(config_path: Path | str) -> dict[str, object]:
    """Async version of read_config. Use from async code to avoid blocking the event loop."""
    return await asyncio.to_thread(read_config, config_path)


def parse_servers(
    raw_config: dict[str, object],
    source_file: str = "",
) -> list[InstalledServer]:
    """Extract server entries from a raw config dict."""
    servers_dict = raw_config.get("mcpServers", {})
    if not isinstance(servers_dict, dict):
        return []

    result: list[InstalledServer] = []
    for name, entry in servers_dict.items():
        if not isinstance(entry, dict):
            continue

        entry_type = str(entry.get("type", "stdio"))
        if "url" in entry and entry_type in ("http", "sse", "streamable-http"):
            config: ServerConfig | HttpServerConfig = HttpServerConfig(
                url=str(entry["url"]),
                transport_type="sse" if entry_type == "sse" else "http",
                env=dict(entry.get("env", {})),
            )
        else:
            config = ServerConfig(
                command=str(entry.get("command", "")),
                args=list(entry.get("args", [])),
                env=dict(entry.get("env", {})),
            )
        result.append(InstalledServer(name=name, config=config, source_file=source_file))

    return result
