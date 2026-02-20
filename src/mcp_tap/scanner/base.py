"""Port: Project technology scanning."""

from __future__ import annotations

from typing import Protocol

from mcp_tap.models import MCPClient, ProjectProfile


class ProjectScannerPort(Protocol):
    """Port for detecting technologies from project files."""

    async def scan_project(
        self,
        path: str,
        *,
        client: MCPClient | None = None,
    ) -> ProjectProfile:
        """Scan a project directory and return a ProjectProfile."""
        ...
