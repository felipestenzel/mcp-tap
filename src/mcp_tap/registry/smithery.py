"""HTTP client for the Smithery MCP server registry.

API docs: https://smithery.ai
Base URL: https://api.smithery.ai

Authentication is optional -- the API works without an API key.
If ``SMITHERY_API_KEY`` is set in the environment, it is sent as
a Bearer token for higher rate limits.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from urllib.parse import quote as urlquote

import httpx

from mcp_tap.errors import RegistryError
from mcp_tap.models import PackageInfo, RegistryServer, RegistryType, Transport

_BASE_URL = "https://api.smithery.ai"

# Maximum retries on HTTP 429 (Too Many Requests).
_MAX_429_RETRIES = 1
_RETRY_DELAY_SECONDS = 2.0


@dataclass
class SmitheryClient:
    """Async client for the Smithery MCP server registry.

    Works without authentication.  When ``api_key`` is provided, it is
    sent as a ``Bearer`` token for higher rate limits.
    """

    http: httpx.AsyncClient
    api_key: str = ""

    # ── Public API ────────────────────────────────────────────

    async def search(
        self,
        query: str,
        *,
        limit: int = 30,
    ) -> list[RegistryServer]:
        """Search Smithery for MCP servers matching *query*.

        Args:
            query: Free-text search term.
            limit: Maximum number of results (clamped to 1-100).

        Returns:
            List of ``RegistryServer`` objects from the Smithery catalogue.

        Raises:
            RegistryError: On non-retryable HTTP errors or after exhausting
                429 retries.
        """
        params = {"q": query, "pageSize": min(max(limit, 1), 100)}
        data = await self._get("/servers", params=params)
        servers_raw: list[dict] = data.get("servers", [])
        return [self._parse_server(entry) for entry in servers_raw]

    async def get_server(self, name: str) -> RegistryServer | None:
        """Fetch a single server by its Smithery ``qualifiedName``.

        Args:
            name: The ``qualifiedName`` identifier (e.g. ``"neon"``).

        Returns:
            A ``RegistryServer`` if found, or ``None`` on 404.

        Raises:
            RegistryError: On non-retryable HTTP errors or after exhausting
                429 retries.
        """
        encoded = urlquote(name, safe="")
        try:
            data = await self._get(f"/servers/{encoded}")
        except RegistryError as exc:
            # Surface 404 as None rather than an error.
            if "404" in str(exc):
                return None
            raise
        return self._parse_server(data)

    # ── HTTP helpers ──────────────────────────────────────────

    def _headers(self) -> dict[str, str]:
        """Build request headers.

        Returns an ``Authorization`` header when an API key is configured,
        otherwise an empty dict (anonymous access).
        """
        if self.api_key:
            return {"Authorization": f"Bearer {self.api_key}"}
        return {}

    async def _get(
        self,
        path: str,
        *,
        params: dict[str, object] | None = None,
    ) -> dict:
        """Execute a GET request with automatic 429 retry.

        Args:
            path: URL path appended to ``_BASE_URL``.
            params: Optional query-string parameters.

        Returns:
            Parsed JSON response body.

        Raises:
            RegistryError: After all retry attempts are exhausted or on
                non-retryable HTTP errors.
        """
        url = f"{_BASE_URL}{path}"
        last_exc: httpx.HTTPError | None = None

        for attempt in range(_MAX_429_RETRIES + 1):
            try:
                response = await self.http.get(
                    url,
                    params=params,
                    headers=self._headers(),
                )
                if response.status_code == 429:
                    if attempt < _MAX_429_RETRIES:
                        await asyncio.sleep(_RETRY_DELAY_SECONDS)
                        continue
                    raise RegistryError(
                        f"Smithery API rate limit exceeded for '{path}' "
                        f"after {_MAX_429_RETRIES + 1} attempts"
                    )
                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError as exc:
                raise RegistryError(
                    f"Smithery API error for '{path}': "
                    f"{exc.response.status_code} {exc.response.reason_phrase}"
                ) from exc
            except httpx.HTTPError as exc:
                last_exc = exc
                if attempt < _MAX_429_RETRIES:
                    await asyncio.sleep(_RETRY_DELAY_SECONDS)
                    continue

        raise RegistryError(f"Failed to reach Smithery API at '{path}': {last_exc}") from last_exc

    # ── Parsing ───────────────────────────────────────────────

    def _parse_server(self, raw: dict) -> RegistryServer:
        """Map a Smithery API server object to a ``RegistryServer``.

        Tolerant of missing fields -- uses sensible defaults rather than
        crashing on incomplete data.
        """
        qualified_name = raw.get("qualifiedName", raw.get("name", ""))

        package = PackageInfo(
            registry_type=RegistryType.SMITHERY,
            identifier=qualified_name,
            version="",
            transport=Transport.STDIO,
        )

        return RegistryServer(
            name=qualified_name,
            description=raw.get("description", ""),
            version="",
            repository_url=raw.get("homepage", ""),
            packages=[package],
            is_official=raw.get("verified", False),
            updated_at=raw.get("createdAt", ""),
            use_count=raw.get("useCount"),
            verified=raw.get("verified"),
            smithery_id=raw.get("qualifiedName"),
            source="smithery",
        )
