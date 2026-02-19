"""Tests for server.py — composition root and lifespan (Fix H1)."""

from __future__ import annotations

from unittest.mock import MagicMock

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
        """Should create a RegistryClient instance in the context."""
        from mcp_tap.registry.client import RegistryClient

        mock_server = MagicMock()

        async with app_lifespan(mock_server) as ctx:
            assert isinstance(ctx.registry, RegistryClient)

    async def test_client_closed_after_lifespan(self):
        """Should close httpx.AsyncClient when lifespan exits."""
        mock_server = MagicMock()

        async with app_lifespan(mock_server) as ctx:
            client = ctx.http_client
            assert not client.is_closed

        assert client.is_closed
