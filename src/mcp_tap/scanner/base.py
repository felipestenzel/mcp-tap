"""Port: Project technology scanning."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from mcp_tap.models import MCPClient, ProjectProfile

if TYPE_CHECKING:
    from mcp_tap.registry.base import RegistryClientPort


class ProjectScannerPort(Protocol):
    """Port for detecting technologies from project files."""

    async def scan_project(
        self,
        path: str,
        *,
        client: MCPClient | None = None,
        registry: RegistryClientPort | None = None,
    ) -> ProjectProfile:
        """Scan a project directory and return a ProjectProfile."""
        ...
