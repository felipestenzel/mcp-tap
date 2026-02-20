"""Port: MCP Registry API client."""

from __future__ import annotations

from typing import Protocol

from mcp_tap.models import RegistryServer


class RegistryClientPort(Protocol):
    """Port for querying the MCP server registry."""

    async def search(
        self,
        query: str,
        *,
        limit: int = 30,
    ) -> list[RegistryServer]:
        """Search the registry for MCP servers matching a query."""
        ...

    async def get_server(self, name: str) -> RegistryServer | None:
        """Fetch a specific server entry by its registry name."""
        ...
