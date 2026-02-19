"""HTTP client for the official MCP Registry API.

API docs: https://registry.modelcontextprotocol.io/openapi.yaml
Base URL: https://registry.modelcontextprotocol.io/v0.1
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import quote as urlquote

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

# Namespace key used by the registry for official-status metadata.
_OFFICIAL_META_KEY = "io.modelcontextprotocol.registry/official"


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
            raise RegistryError(
                f"Failed to search MCP Registry for '{query}': {exc}"
            ) from exc

        data = response.json()
        servers_raw = data.get("servers", [])
        return [self._parse_entry(entry) for entry in servers_raw]

    async def get_server(self, name: str) -> RegistryServer | None:
        """Fetch a specific server by its registry name.

        Uses the ``/servers/{name}/versions/latest`` endpoint.
        The server name (e.g. ``io.github.user/repo``) is URL-encoded
        automatically.
        """
        encoded = urlquote(name, safe="")
        try:
            response = await self.http.get(
                f"{_BASE_URL}/servers/{encoded}/versions/latest",
            )
            if response.status_code == 404:
                return None
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise RegistryError(
                f"Failed to fetch server '{name}': {exc}"
            ) from exc

        return self._parse_entry(response.json())

    # ── Parsing helpers ──────────────────────────────────────────

    def _parse_entry(self, entry: dict) -> RegistryServer:
        """Parse a registry response entry into a RegistryServer.

        Handles both the current wrapped format::

            {"server": {...}, "_meta": {...}}

        and the legacy flat format where server fields are at the
        top level.
        """
        if "server" in entry and isinstance(entry["server"], dict):
            server_data = entry["server"]
            meta = entry.get("_meta", {})
        else:
            server_data = entry
            meta = entry.get("_meta", {})

        return self._parse_server(server_data, meta)

    def _parse_server(self, raw: dict, meta: dict | None = None) -> RegistryServer:
        """Parse raw server JSON into a RegistryServer model.

        Tolerant of missing fields — uses defaults rather than crashing.
        Handles both ``packages`` (legacy) and ``remotes`` (current) formats.
        """
        if meta is None:
            meta = raw.get("_meta", {})

        packages = self._parse_packages(raw)

        if not packages:
            packages = self._parse_remotes(raw)

        repo = raw.get("repository", {})
        repo_url = repo.get("url", "") if isinstance(repo, dict) else ""

        return RegistryServer(
            name=raw.get("name", ""),
            description=raw.get("description", ""),
            version=raw.get("version", ""),
            repository_url=repo_url,
            packages=packages,
            is_official=self._extract_is_official(meta),
            updated_at=self._extract_updated_at(meta),
        )

    def _parse_packages(self, raw: dict) -> list[PackageInfo]:
        """Parse the ``packages`` array (legacy format)."""
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

            transport = self._parse_transport(pkg.get("transport", "stdio"))

            packages.append(
                PackageInfo(
                    registry_type=registry_type,
                    identifier=pkg.get("identifier", pkg.get("name", "")),
                    version=pkg.get("version", raw.get("version", "")),
                    transport=transport,
                    environment_variables=env_vars,
                )
            )
        return packages

    def _parse_remotes(self, raw: dict) -> list[PackageInfo]:
        """Parse the ``remotes`` array (current format).

        Remotes represent hosted MCP servers accessed via HTTP/SSE.
        We convert them to PackageInfo so downstream code works uniformly.
        """
        packages = []
        for remote in raw.get("remotes", []):
            transport_raw = remote.get("type", "streamable-http").lower()
            try:
                transport = Transport(transport_raw)
            except ValueError:
                transport = Transport.STREAMABLE_HTTP

            env_vars = []
            for header in remote.get("headers", []):
                env_vars.append(
                    EnvVarSpec(
                        name=header.get("name", ""),
                        description=header.get("description", ""),
                        is_required=header.get("isRequired", True),
                        is_secret=header.get("isSecret", False),
                    )
                )

            packages.append(
                PackageInfo(
                    registry_type=RegistryType.NPM,
                    identifier=remote.get("url", ""),
                    version=raw.get("version", ""),
                    transport=transport,
                    environment_variables=env_vars,
                )
            )
        return packages

    @staticmethod
    def _parse_transport(value: str | dict) -> Transport:
        """Parse a transport field that may be a string or a ``{"type": ...}`` dict."""
        raw = value.get("type", "stdio") if isinstance(value, dict) else value
        try:
            return Transport(str(raw).lower())
        except ValueError:
            return Transport.STDIO

    @staticmethod
    def _extract_is_official(meta: dict) -> bool:
        """Extract ``is_official`` from either legacy or current _meta format."""
        # Current format: {"io.modelcontextprotocol.registry/official": {"status": "active"}}
        official_block = meta.get(_OFFICIAL_META_KEY, {})
        if isinstance(official_block, dict) and official_block.get("status") == "active":
            return True
        # Legacy format: {"isOfficial": true}
        return bool(meta.get("isOfficial", False))

    @staticmethod
    def _extract_updated_at(meta: dict) -> str:
        """Extract ``updated_at`` from either legacy or current _meta format."""
        # Current format
        official_block = meta.get(_OFFICIAL_META_KEY, {})
        if isinstance(official_block, dict):
            updated = official_block.get("updatedAt", "")
            if updated:
                return updated
        # Legacy format
        return meta.get("updatedAt", "")
