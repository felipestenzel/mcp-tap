"""Detect installed MCP clients and locate their config files."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from mcp_tap.errors import ClientNotFoundError
from mcp_tap.models import ConfigLocation, MCPClient


def _claude_desktop_config() -> Path | None:
    home = Path.home()
    match sys.platform:
        case "darwin":
            return (
                home / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
            )
        case "linux":
            xdg = os.environ.get("XDG_CONFIG_HOME", str(home / ".config"))
            return Path(xdg) / "Claude" / "claude_desktop_config.json"
        case "win32":
            appdata = os.environ.get("APPDATA", str(home / "AppData" / "Roaming"))
            return Path(appdata) / "Claude" / "claude_desktop_config.json"
    return None


def _claude_code_user_config() -> Path:
    return Path.home() / ".claude.json"


def _cursor_user_config() -> Path:
    return Path.home() / ".cursor" / "mcp.json"


def _windsurf_user_config() -> Path:
    return Path.home() / ".codeium" / "windsurf" / "mcp_config.json"


_CLIENT_CONFIGS: list[tuple[MCPClient, str, callable]] = [
    (MCPClient.CLAUDE_DESKTOP, "user", _claude_desktop_config),
    (MCPClient.CLAUDE_CODE, "user", _claude_code_user_config),
    (MCPClient.CURSOR, "user", _cursor_user_config),
    (MCPClient.WINDSURF, "user", _windsurf_user_config),
]


def detect_clients() -> list[ConfigLocation]:
    """Detect all installed MCP clients and their config file locations.

    Returns:
        List of ConfigLocation entries for clients whose config files exist.
    """
    found: list[ConfigLocation] = []
    for client, scope, path_fn in _CLIENT_CONFIGS:
        path = path_fn()
        if path is not None:
            exists = path.exists()
            found.append(
                ConfigLocation(
                    client=client,
                    path=str(path),
                    scope=scope,
                    exists=exists,
                )
            )
    return [loc for loc in found if loc.exists]


def resolve_config_path(client: MCPClient | str) -> ConfigLocation:
    """Resolve config path for a specific client.

    Returns ConfigLocation even if the file doesn't exist yet (for first-time setup).
    """
    client_enum = MCPClient(client) if isinstance(client, str) else client

    path_map: dict[MCPClient, callable] = {
        MCPClient.CLAUDE_DESKTOP: _claude_desktop_config,
        MCPClient.CLAUDE_CODE: _claude_code_user_config,
        MCPClient.CURSOR: _cursor_user_config,
        MCPClient.WINDSURF: _windsurf_user_config,
    }

    path_fn = path_map.get(client_enum)
    if path_fn is None:
        raise ClientNotFoundError(f"Unknown MCP client: {client}")

    path = path_fn()
    if path is None:
        raise ClientNotFoundError(f"{client_enum.value} is not supported on {sys.platform}")

    return ConfigLocation(
        client=client_enum,
        path=str(path),
        scope="user",
        exists=path.exists(),
    )
