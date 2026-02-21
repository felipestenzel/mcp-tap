"""Tests for server.py — composition root and lifespan (Fix H1)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx

from mcp_tap.server import app_lifespan


class TestAppLifespan:
    """Tests for the app_lifespan context manager."""

    async def test_creates_http_client_with_retries_transport(self):
        """Should create httpx.AsyncClient with retries=3 transport."""
        mock_server = MagicMock()

        async with app_lifespan(mock_server) as ctx:
            client = ctx.http_client
            assert isinstance(client, httpx.AsyncClient)

            # Verify the transport has retries configured
            transport = client._transport
            assert isinstance(transport, httpx.AsyncHTTPTransport)
            assert transport._pool._retries == 3

    async def test_creates_http_client_with_timeout(self):
        """Should create httpx.AsyncClient with 30s read / 10s connect timeout."""
        mock_server = MagicMock()

        async with app_lifespan(mock_server) as ctx:
            client = ctx.http_client
            assert client.timeout.read == 30.0
            assert client.timeout.connect == 10.0

    async def test_creates_http_client_with_follow_redirects(self):
        """Should create httpx.AsyncClient with follow_redirects=True."""
        mock_server = MagicMock()

        async with app_lifespan(mock_server) as ctx:
            client = ctx.http_client
            assert client.follow_redirects is True

    async def test_creates_registry_client(self):
        """Should create an AggregatedRegistry (wrapping RegistryClient + SmitheryClient)."""
        from mcp_tap.registry.aggregator import AggregatedRegistry
        from mcp_tap.registry.client import RegistryClient
        from mcp_tap.registry.smithery import SmitheryClient

        mock_server = MagicMock()

        async with app_lifespan(mock_server) as ctx:
            assert isinstance(ctx.registry, AggregatedRegistry)
            assert isinstance(ctx.registry.official, RegistryClient)
            assert isinstance(ctx.registry.smithery, SmitheryClient)

    async def test_client_closed_after_lifespan(self):
        """Should close httpx.AsyncClient when lifespan exits."""
        mock_server = MagicMock()

        async with app_lifespan(mock_server) as ctx:
            client = ctx.http_client
            assert not client.is_closed

        assert client.is_closed

    # === Bug M1 — Pool Limits =============================================

    async def test_creates_http_client_with_pool_limits(self):
        """Should pass max_connections=10 limits to httpx.AsyncClient (Bug M1).

        Note: When an explicit transport= is provided, httpx applies pool
        limits from the transport, not from the limits= parameter. We verify
        that the limits= parameter is declared in the code by patching the
        AsyncClient constructor to capture the kwargs.
        """
        import httpx as httpx_mod

        original_init = httpx_mod.AsyncClient.__init__
        captured_kwargs: dict[str, object] = {}

        def capture_init(self, **kwargs):
            captured_kwargs.update(kwargs)
            return original_init(self, **kwargs)

        with patch.object(httpx_mod.AsyncClient, "__init__", capture_init):
            mock_server = MagicMock()
            async with app_lifespan(mock_server) as ctx:
                assert ctx.http_client is not None

        assert "limits" in captured_kwargs
        limits = captured_kwargs["limits"]
        assert isinstance(limits, httpx.Limits)
        assert limits.max_connections == 10
        assert limits.max_keepalive_connections == 5
