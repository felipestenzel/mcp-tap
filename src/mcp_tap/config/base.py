"""Ports: Config detection, reading, and writing."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from mcp_tap.models import ConfigLocation, InstalledServer, MCPClient, ServerConfig


class ConfigLocatorPort(Protocol):
    """Port for detecting MCP clients and resolving config paths."""

    def detect_clients(self) -> list[ConfigLocation]:
        """Detect all installed MCP clients on the system."""
        ...

    def resolve_config_path(
        self,
        client: MCPClient | str,
        *,
        scope: str = "user",
        project_path: str = "",
    ) -> ConfigLocation:
        """Resolve the config file path for a specific client."""
        ...

    def resolve_config_locations(
        self,
        clients: str = "",
        *,
        scope: str = "user",
        project_path: str = "",
    ) -> list[ConfigLocation]:
        """Resolve config locations for one, many, or all clients."""
        ...


class ConfigReaderPort(Protocol):
    """Port for reading and parsing MCP client config files."""

    def read_config(self, config_path: Path | str) -> dict[str, object]:
        """Read a full MCP client config file as a dict."""
        ...

    def parse_servers(
        self,
        raw_config: dict[str, object],
        source_file: str = "",
    ) -> list[InstalledServer]:
        """Extract server entries from a raw config dict."""
        ...


class ConfigWriterPort(Protocol):
    """Port for atomic writes to MCP client config files."""

    def write_server_config(
        self,
        config_path: Path | str,
        server_name: str,
        server_config: ServerConfig,
        *,
        overwrite_existing: bool = False,
    ) -> None:
        """Add or update a server entry in the config file atomically."""
        ...

    def remove_server_config(
        self,
        config_path: Path | str,
        server_name: str,
    ) -> dict[str, object] | None:
        """Remove a server from the config file. Returns removed entry or None."""
        ...
