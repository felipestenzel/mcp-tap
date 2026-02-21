"""Tests for the Smithery MCP registry client (registry/smithery.py)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from mcp_tap.errors import RegistryError
from mcp_tap.models import RegistryType, Transport
from mcp_tap.registry.smithery import _BASE_URL, SmitheryClient

# ── Fixture data ──────────────────────────────────────────────────

SMITHERY_SERVER_FIXTURE = {
    "id": "abc123",
    "qualifiedName": "neon",
    "displayName": "Neon",
    "description": "Manage PostgreSQL projects",
    "iconUrl": "https://example.com/icon.png",
    "verified": True,
    "useCount": 269,
    "remote": True,
    "isDeployed": True,
    "createdAt": "2026-01-29T06:26:32.660Z",
    "homepage": "https://smithery.ai/servers/neon",
    "owner": "user-123",
    "score": 0.013,
}

SMITHERY_SEARCH_RESPONSE = {
    "servers": [SMITHERY_SERVER_FIXTURE],
    "pagination": {"page": 0, "pageSize": 30, "totalPages": 1, "totalCount": 1},
}

SMITHERY_EMPTY_RESPONSE = {
    "servers": [],
    "pagination": {"page": 0, "pageSize": 30, "totalPages": 0, "totalCount": 0},
}


# ── Helpers ───────────────────────────────────────────────────────


def _make_client(api_key: str = "") -> SmitheryClient:
    return SmitheryClient(http=AsyncMock(spec=httpx.AsyncClient), api_key=api_key)


def _ok_response(data: dict) -> MagicMock:
    """Build a mock httpx.Response with 200 status and JSON data."""
    resp = MagicMock()
    resp.status_code = 200
    resp.raise_for_status = MagicMock()
    resp.json.return_value = data
    return resp


def _status_response(status_code: int) -> MagicMock:
    """Build a mock httpx.Response with the given status code."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.reason_phrase = f"HTTP {status_code}"
    if status_code >= 400 and status_code != 429:
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            f"HTTP {status_code}",
            request=MagicMock(),
            response=resp,
        )
    else:
        resp.raise_for_status = MagicMock()
    resp.json.return_value = {}
    return resp


# ═══════════════════════════════════════════════════════════════════
# TestSmitheryClientSearch
# ═══════════════════════════════════════════════════════════════════


class TestSmitheryClientSearch:
    """Tests for SmitheryClient.search."""

    async def test_search_returns_registry_servers(self):
        """Should parse JSON response into a list of RegistryServer objects."""
        client = _make_client()
        client.http.get = AsyncMock(return_value=_ok_response(SMITHERY_SEARCH_RESPONSE))

        results = await client.search("postgres")

        assert len(results) == 1
        server = results[0]
        assert server.name == "neon"
        assert server.description == "Manage PostgreSQL projects"
        assert server.use_count == 269
        assert server.verified is True
        assert server.smithery_id == "neon"
        assert server.source == "smithery"
        assert len(server.packages) == 1
        assert server.packages[0].registry_type == RegistryType.SMITHERY

    async def test_search_anonymous_no_auth_header(self):
        """Should NOT send Authorization header when api_key is empty."""
        client = _make_client(api_key="")
        client.http.get = AsyncMock(return_value=_ok_response(SMITHERY_EMPTY_RESPONSE))

        await client.search("test")

        _, kwargs = client.http.get.call_args
        headers = kwargs.get("headers", {})
        assert "Authorization" not in headers

    async def test_search_with_api_key_sends_auth_header(self):
        """Should send Authorization: Bearer header when api_key is set."""
        client = _make_client(api_key="sk-test")
        client.http.get = AsyncMock(return_value=_ok_response(SMITHERY_EMPTY_RESPONSE))

        await client.search("test")

        _, kwargs = client.http.get.call_args
        headers = kwargs.get("headers", {})
        assert headers["Authorization"] == "Bearer sk-test"

    @patch("mcp_tap.registry.smithery.asyncio.sleep", new_callable=AsyncMock)
    async def test_search_retries_on_429(self, mock_sleep: AsyncMock):
        """Should retry once on 429 and return results on success."""
        client = _make_client()
        rate_limited = _status_response(429)
        success = _ok_response(SMITHERY_SEARCH_RESPONSE)
        client.http.get = AsyncMock(side_effect=[rate_limited, success])

        results = await client.search("postgres")

        assert len(results) == 1
        assert results[0].name == "neon"
        mock_sleep.assert_awaited_once_with(2.0)

    @patch("mcp_tap.registry.smithery.asyncio.sleep", new_callable=AsyncMock)
    async def test_search_raises_after_max_429_retries(self, mock_sleep: AsyncMock):
        """Should raise RegistryError when all retry attempts return 429."""
        client = _make_client()
        rate_limited = _status_response(429)
        # _MAX_429_RETRIES = 1, so total attempts = 2
        client.http.get = AsyncMock(side_effect=[rate_limited, rate_limited])

        with pytest.raises(RegistryError, match="rate limit exceeded"):
            await client.search("postgres")

    async def test_search_empty_results(self):
        """Should return empty list when Smithery API returns no servers."""
        client = _make_client()
        client.http.get = AsyncMock(return_value=_ok_response(SMITHERY_EMPTY_RESPONSE))

        results = await client.search("nonexistent")

        assert results == []

    async def test_search_clamps_page_size(self):
        """Should clamp limit to max 100 in the pageSize param."""
        client = _make_client()
        client.http.get = AsyncMock(return_value=_ok_response(SMITHERY_EMPTY_RESPONSE))

        await client.search("test", limit=200)

        _, kwargs = client.http.get.call_args
        params = kwargs.get("params", {})
        assert params["pageSize"] == 100

    async def test_search_clamps_page_size_minimum(self):
        """Should clamp limit to min 1 in the pageSize param."""
        client = _make_client()
        client.http.get = AsyncMock(return_value=_ok_response(SMITHERY_EMPTY_RESPONSE))

        await client.search("test", limit=0)

        _, kwargs = client.http.get.call_args
        params = kwargs.get("params", {})
        assert params["pageSize"] == 1

    async def test_search_sends_correct_url(self):
        """Should send GET to /servers with q param."""
        client = _make_client()
        client.http.get = AsyncMock(return_value=_ok_response(SMITHERY_EMPTY_RESPONSE))

        await client.search("postgres", limit=10)

        url_called = client.http.get.call_args[0][0]
        assert url_called == f"{_BASE_URL}/servers"
        _, kwargs = client.http.get.call_args
        assert kwargs["params"]["q"] == "postgres"


# ═══════════════════════════════════════════════════════════════════
# TestSmitheryClientGetServer
# ═══════════════════════════════════════════════════════════════════


class TestSmitheryClientGetServer:
    """Tests for SmitheryClient.get_server."""

    async def test_get_server_returns_server(self):
        """Should return a RegistryServer when API responds with valid JSON."""
        client = _make_client()
        client.http.get = AsyncMock(return_value=_ok_response(SMITHERY_SERVER_FIXTURE))

        result = await client.get_server("neon")

        assert result is not None
        assert result.name == "neon"
        assert result.description == "Manage PostgreSQL projects"
        assert result.source == "smithery"

    async def test_get_server_returns_none_on_404(self):
        """Should return None when API responds with 404."""
        client = _make_client()
        resp_404 = _status_response(404)
        client.http.get = AsyncMock(side_effect=httpx.HTTPStatusError(
            "404 Not Found",
            request=MagicMock(),
            response=resp_404,
        ))
        # The _get method catches HTTPStatusError and raises RegistryError.
        # get_server catches RegistryError with "404" in message and returns None.
        # To test this properly, we need to make _get raise RegistryError with "404".
        # Let's mock at the _get level instead.
        resp_404_proper = _status_response(404)
        client.http.get = AsyncMock(return_value=resp_404_proper)

        result = await client.get_server("nonexistent")

        assert result is None

    async def test_get_server_url_encodes_name(self):
        """Should URL-encode the name parameter (e.g. slash -> %2F)."""
        client = _make_client()
        client.http.get = AsyncMock(return_value=_ok_response(SMITHERY_SERVER_FIXTURE))

        await client.get_server("foo/bar")

        url_called = client.http.get.call_args[0][0]
        assert "foo%2Fbar" in url_called
        assert "foo/bar" not in url_called.split(_BASE_URL)[-1]


# ═══════════════════════════════════════════════════════════════════
# TestSmitheryClientParsing
# ═══════════════════════════════════════════════════════════════════


class TestSmitheryClientParsing:
    """Tests for SmitheryClient._parse_server (internal parsing logic)."""

    def _make_client(self) -> SmitheryClient:
        return SmitheryClient(http=AsyncMock(spec=httpx.AsyncClient))

    def test_parse_server_maps_all_fields(self):
        """Should correctly map all fields from a complete Smithery JSON object."""
        client = self._make_client()

        server = client._parse_server(SMITHERY_SERVER_FIXTURE)

        assert server.name == "neon"
        assert server.description == "Manage PostgreSQL projects"
        assert server.is_official is True  # verified == True
        assert server.use_count == 269
        assert server.verified is True
        assert server.smithery_id == "neon"
        assert server.repository_url == "https://smithery.ai/servers/neon"
        assert server.updated_at == "2026-01-29T06:26:32.660Z"

    def test_parse_server_missing_fields_uses_defaults(self):
        """Should not crash on minimal JSON -- uses defaults for missing fields."""
        client = self._make_client()

        server = client._parse_server({})

        assert server.name == ""
        assert server.description == ""
        assert server.is_official is False
        assert server.use_count is None
        assert server.verified is None
        assert server.smithery_id is None
        assert server.repository_url == ""
        assert server.version == ""

    def test_parse_server_sets_source_smithery(self):
        """Should always set source to 'smithery'."""
        client = self._make_client()

        server = client._parse_server(SMITHERY_SERVER_FIXTURE)

        assert server.source == "smithery"

    def test_parse_server_sets_registry_type_smithery(self):
        """Should set the package's registry_type to SMITHERY."""
        client = self._make_client()

        server = client._parse_server(SMITHERY_SERVER_FIXTURE)

        assert len(server.packages) == 1
        assert server.packages[0].registry_type == RegistryType.SMITHERY

    def test_parse_server_package_identifier_is_qualified_name(self):
        """Should use qualifiedName as the package identifier."""
        client = self._make_client()

        server = client._parse_server(SMITHERY_SERVER_FIXTURE)

        assert server.packages[0].identifier == "neon"

    def test_parse_server_package_transport_is_stdio(self):
        """Should default to STDIO transport for Smithery packages."""
        client = self._make_client()

        server = client._parse_server(SMITHERY_SERVER_FIXTURE)

        assert server.packages[0].transport == Transport.STDIO

    def test_parse_server_uses_name_fallback(self):
        """Should fall back to 'name' field when 'qualifiedName' is missing."""
        client = self._make_client()
        raw = {"name": "fallback-name", "description": "test"}

        server = client._parse_server(raw)

        assert server.name == "fallback-name"
        assert server.packages[0].identifier == "fallback-name"
