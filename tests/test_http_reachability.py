"""Tests for HttpReachabilityChecker (connection/tester.py)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from mcp_tap.connection.tester import HttpReachabilityChecker


@pytest.fixture()
def mock_http_client() -> MagicMock:
    """Build a mock httpx.AsyncClient."""
    return MagicMock(spec=httpx.AsyncClient)


class TestHttpReachabilityCheckerSuccess:
    """Tests for successful reachability checks."""

    async def test_200_is_reachable(self, mock_http_client: MagicMock):
        """HTTP 200 should be treated as reachable."""
        mock_http_client.head = AsyncMock(return_value=httpx.Response(status_code=200))
        checker = HttpReachabilityChecker(mock_http_client)

        result = await checker.check_reachability("srv", "https://mcp.example.com")

        assert result.success is True
        assert result.server_name == "srv"

    async def test_401_is_reachable_oauth(self, mock_http_client: MagicMock):
        """HTTP 401 should be treated as reachable (OAuth-gated server)."""
        mock_http_client.head = AsyncMock(return_value=httpx.Response(status_code=401))
        checker = HttpReachabilityChecker(mock_http_client)

        result = await checker.check_reachability("srv", "https://oauth.example.com")

        assert result.success is True

    async def test_403_is_reachable(self, mock_http_client: MagicMock):
        """HTTP 403 should be treated as reachable (auth-gated but server is up)."""
        mock_http_client.head = AsyncMock(return_value=httpx.Response(status_code=403))
        checker = HttpReachabilityChecker(mock_http_client)

        result = await checker.check_reachability("srv", "https://auth.example.com")

        assert result.success is True

    async def test_301_redirect_is_reachable(self, mock_http_client: MagicMock):
        """HTTP 301 should be treated as reachable (redirect, not server error)."""
        mock_http_client.head = AsyncMock(return_value=httpx.Response(status_code=301))
        checker = HttpReachabilityChecker(mock_http_client)

        result = await checker.check_reachability("srv", "https://redirect.example.com")

        assert result.success is True

    async def test_404_is_reachable(self, mock_http_client: MagicMock):
        """HTTP 404 is < 500 so should be treated as reachable."""
        mock_http_client.head = AsyncMock(return_value=httpx.Response(status_code=404))
        checker = HttpReachabilityChecker(mock_http_client)

        result = await checker.check_reachability("srv", "https://example.com/mcp")

        assert result.success is True


class TestHttpReachabilityCheckerFailure:
    """Tests for failed reachability checks."""

    async def test_500_is_not_reachable(self, mock_http_client: MagicMock):
        """HTTP 500 should be treated as unreachable."""
        mock_http_client.head = AsyncMock(return_value=httpx.Response(status_code=500))
        checker = HttpReachabilityChecker(mock_http_client)

        result = await checker.check_reachability("srv", "https://broken.example.com")

        assert result.success is False
        assert "500" in result.error
        assert "temporarily unavailable" in result.error

    async def test_503_is_not_reachable(self, mock_http_client: MagicMock):
        """HTTP 503 should be treated as unreachable."""
        mock_http_client.head = AsyncMock(return_value=httpx.Response(status_code=503))
        checker = HttpReachabilityChecker(mock_http_client)

        result = await checker.check_reachability("srv", "https://down.example.com")

        assert result.success is False

    async def test_connect_error_mentions_vpn(self, mock_http_client: MagicMock):
        """ConnectError should mention 'down or require VPN' in error message."""
        mock_http_client.head = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))
        checker = HttpReachabilityChecker(mock_http_client)

        result = await checker.check_reachability("srv", "https://unreachable.example.com")

        assert result.success is False
        assert "down or require VPN" in result.error
        assert result.server_name == "srv"

    async def test_timeout_mentions_oauth_and_restart(self, mock_http_client: MagicMock):
        """TimeoutException should mention OAuth and restart in error message."""
        mock_http_client.head = AsyncMock(side_effect=httpx.TimeoutException("Request timed out"))
        checker = HttpReachabilityChecker(mock_http_client)

        result = await checker.check_reachability("srv", "https://slow.example.com")

        assert result.success is False
        assert "OAuth" in result.error
        assert "restart" in result.error.lower()

    async def test_generic_exception_returns_failure(self, mock_http_client: MagicMock):
        """Unexpected exceptions should return failure with type name."""
        mock_http_client.head = AsyncMock(side_effect=ValueError("bad url"))
        checker = HttpReachabilityChecker(mock_http_client)

        result = await checker.check_reachability("srv", "https://bad.example.com")

        assert result.success is False
        assert "ValueError" in result.error


class TestHttpReachabilityCheckerTimeout:
    """Tests for timeout parameter handling."""

    async def test_timeout_passed_to_head(self, mock_http_client: MagicMock):
        """Should pass timeout_seconds to httpx.head as float timeout."""
        mock_http_client.head = AsyncMock(return_value=httpx.Response(status_code=200))
        checker = HttpReachabilityChecker(mock_http_client)

        await checker.check_reachability("srv", "https://example.com", timeout_seconds=30)

        call_kwargs = mock_http_client.head.call_args
        assert call_kwargs[1]["timeout"] == 30.0

    async def test_uses_head_method(self, mock_http_client: MagicMock):
        """Should use HEAD request for efficiency."""
        mock_http_client.head = AsyncMock(return_value=httpx.Response(status_code=200))
        checker = HttpReachabilityChecker(mock_http_client)

        await checker.check_reachability("srv", "https://example.com")

        mock_http_client.head.assert_awaited_once_with("https://example.com", timeout=10.0)
