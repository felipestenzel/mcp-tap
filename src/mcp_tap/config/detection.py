"""Detect installed MCP clients and locate their config files."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from mcp_tap.errors import ClientNotFoundError
from mcp_tap.models import ConfigLocation, MCPClient

# ─── User-scoped config paths ───────────────────────────────────


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

# ─── Project-scoped config paths ────────────────────────────────

# Maps client → relative path inside project directory.
# Claude Desktop has no project-scoped config.
_PROJECT_CONFIGS: dict[MCPClient, str] = {
    MCPClient.CLAUDE_CODE: ".mcp.json",
    MCPClient.CURSOR: ".cursor/mcp.json",
    MCPClient.WINDSURF: ".windsurf/mcp_config.json",
}


# ─── Public API ─────────────────────────────────────────────────


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


def resolve_config_path(
    client: MCPClient | str,
    *,
    scope: str = "user",
    project_path: str = "",
) -> ConfigLocation:
    """Resolve config path for a specific client and scope.

    Args:
        client: Target MCP client.
        scope: "user" for global config, "project" for project-scoped.
        project_path: Project directory (required when scope="project").

    Returns ConfigLocation even if the file doesn't exist yet (for first-time setup).
    """
    client_enum = MCPClient(client) if isinstance(client, str) else client

    if scope == "project":
        return _resolve_project_config(client_enum, project_path)

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


def resolve_config_locations(
    clients: str = "",
    *,
    scope: str = "user",
    project_path: str = "",
) -> list[ConfigLocation]:
    """Resolve config locations for one, many, or all clients.

    Args:
        clients: Comma-separated client names, "all", or empty for auto-detect.
        scope: "user" for global config, "project" for project-scoped.
        project_path: Project directory (required when scope="project").

    Returns:
        List of ConfigLocation entries. Empty list if no clients resolved.
    """
    if clients == "all":
        if scope == "project":
            return _all_project_configs(project_path)
        return _all_user_configs()

    if clients:
        names = [c.strip() for c in clients.split(",") if c.strip()]
        return [resolve_config_path(name, scope=scope, project_path=project_path) for name in names]

    # Auto-detect: single best client
    detected = detect_clients()
    if not detected:
        return []
    return [detected[0]]


# ─── Private helpers ────────────────────────────────────────────


def _resolve_project_config(client: MCPClient, project_path: str) -> ConfigLocation:
    """Resolve a project-scoped config path for a client."""
    if not project_path:
        raise ClientNotFoundError(
            "project_path is required when scope='project'. "
            "Pass the path to your project directory."
        )

    rel = _PROJECT_CONFIGS.get(client)
    if rel is None:
        raise ClientNotFoundError(
            f"{client.value} does not support project-scoped config. Use scope='user' instead."
        )

    path = Path(project_path) / rel
    return ConfigLocation(
        client=client,
        path=str(path),
        scope="project",
        exists=path.exists(),
    )


def _all_user_configs() -> list[ConfigLocation]:
    """Return user-scoped config locations for all known clients."""
    locations: list[ConfigLocation] = []
    for client, _scope, path_fn in _CLIENT_CONFIGS:
        path = path_fn()
        if path is not None:
            locations.append(
                ConfigLocation(
                    client=client,
                    path=str(path),
                    scope="user",
                    exists=path.exists(),
                )
            )
    return locations


def _all_project_configs(project_path: str) -> list[ConfigLocation]:
    """Return project-scoped config locations for all supported clients."""
    if not project_path:
        raise ClientNotFoundError(
            "project_path is required when scope='project' and clients='all'."
        )

    locations: list[ConfigLocation] = []
    for client, rel in _PROJECT_CONFIGS.items():
        path = Path(project_path) / rel
        locations.append(
            ConfigLocation(
                client=client,
                path=str(path),
                scope="project",
                exists=path.exists(),
            )
        )
    return locations
