"""HTTP client for the official MCP Registry API.

API docs: https://registry.modelcontextprotocol.io/openapi.yaml
Base URL: https://registry.modelcontextprotocol.io/v0.1
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from mcp_tap.errors import RegistryError
from mcp_tap.models import (
    EnvVarSpec,
    PackageInfo,
    RegistryServer,
    RegistryType,
    Transport,
)

_BASE_URL = "https://registry.modelcontextprotocol.io/v0.1"


@dataclass
class RegistryClient:
    """Async client for the MCP Registry API."""

    http: httpx.AsyncClient

    async def search(
        self,
        query: str,
        *,
        limit: int = 30,
    ) -> list[RegistryServer]:
        """Search the registry for MCP servers.

        Args:
            query: Search term (substring match on server name/description).
            limit: Max results (1-100).

        Returns:
            List of RegistryServer objects.
        """
        try:
            response = await self.http.get(
                f"{_BASE_URL}/servers",
                params={
                    "search": query,
                    "limit": min(limit, 100),
                    "version": "latest",
                },
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise RegistryError(f"Failed to search MCP Registry for '{query}': {exc}") from exc

        data = response.json()
        servers_raw = data.get("servers", [])
        return [self._parse_server(s) for s in servers_raw]

    async def get_server(self, name: str) -> RegistryServer | None:
        """Fetch a specific server by its registry name."""
        try:
            response = await self.http.get(
                f"{_BASE_URL}/servers/{name}",
            )
            if response.status_code == 404:
                return None
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise RegistryError(f"Failed to fetch server '{name}': {exc}") from exc

        return self._parse_server(response.json())

    def _parse_server(self, raw: dict) -> RegistryServer:
        """Parse a raw server JSON into a RegistryServer model.

        Tolerant of missing fields -- uses defaults rather than crashing.
        """
        packages = []
        for pkg in raw.get("packages", []):
            env_vars = []
            for ev in pkg.get("environmentVariables", []):
                env_vars.append(
                    EnvVarSpec(
                        name=ev.get("name", ""),
                        description=ev.get("description", ""),
                        is_required=ev.get("isRequired", True),
                        is_secret=ev.get("isSecret", False),
                    )
                )

            registry_type_raw = pkg.get("registryType", "npm").lower()
            try:
                registry_type = RegistryType(registry_type_raw)
            except ValueError:
                registry_type = RegistryType.NPM

            transport_raw = pkg.get("transport", "stdio").lower()
            try:
                transport = Transport(transport_raw)
            except ValueError:
                transport = Transport.STDIO

            packages.append(
                PackageInfo(
                    registry_type=registry_type,
                    identifier=pkg.get("identifier", pkg.get("name", "")),
                    version=pkg.get("version", raw.get("version", "")),
                    transport=transport,
                    environment_variables=env_vars,
                )
            )

        repo = raw.get("repository", {})
        repo_url = repo.get("url", "") if isinstance(repo, dict) else ""

        return RegistryServer(
            name=raw.get("name", ""),
            description=raw.get("description", ""),
            version=raw.get("version", ""),
            repository_url=repo_url,
            packages=packages,
            is_official=raw.get("_meta", {}).get("isOfficial", False),
            updated_at=raw.get("_meta", {}).get("updatedAt", ""),
        )
