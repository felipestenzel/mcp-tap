"""Tests for domain models."""

from __future__ import annotations

import pytest

from mcp_tap.models import HttpServerConfig, ServerConfig


class TestServerConfig:
    def test_to_dict_minimal(self):
        config = ServerConfig(command="npx", args=["-y", "test"])
        d = config.to_dict()
        assert d == {"command": "npx", "args": ["-y", "test"]}
        assert "env" not in d

    def test_to_dict_with_env(self):
        config = ServerConfig(command="uvx", args=["pkg"], env={"KEY": "val"})
        d = config.to_dict()
        assert d["env"] == {"KEY": "val"}

    def test_frozen(self):
        config = ServerConfig(command="x", args=[])
        with pytest.raises(AttributeError):
            config.command = "y"  # type: ignore[misc]


class TestHttpServerConfig:
    """Tests for HttpServerConfig model (HTTP native config)."""

    def test_to_dict_http_without_env(self):
        """Should return {"type":"http","url":"..."} without env key."""
        config = HttpServerConfig(url="https://mcp.vercel.com", transport_type="http")
        d = config.to_dict()
        assert d == {"type": "http", "url": "https://mcp.vercel.com"}
        assert "env" not in d

    def test_to_dict_http_with_env(self):
        """Should include env key when env vars are present."""
        config = HttpServerConfig(
            url="https://mcp.vercel.com",
            transport_type="http",
            env={"API_KEY": "sk-123"},
        )
        d = config.to_dict()
        assert d["type"] == "http"
        assert d["url"] == "https://mcp.vercel.com"
        assert d["env"] == {"API_KEY": "sk-123"}

    def test_to_dict_sse_transport(self):
        """Should use type='sse' for SSE transport."""
        config = HttpServerConfig(
            url="https://sse.example.com/v1/sse",
            transport_type="sse",
        )
        d = config.to_dict()
        assert d == {"type": "sse", "url": "https://sse.example.com/v1/sse"}

    def test_to_dict_with_multiple_env_vars(self):
        """Should include all env vars in the dict."""
        config = HttpServerConfig(
            url="https://api.example.com/mcp",
            transport_type="http",
            env={"KEY1": "val1", "KEY2": "val2"},
        )
        d = config.to_dict()
        assert d["env"] == {"KEY1": "val1", "KEY2": "val2"}

    def test_frozen(self):
        """HttpServerConfig should be immutable."""
        config = HttpServerConfig(url="https://x.com", transport_type="http")
        with pytest.raises(AttributeError):
            config.url = "https://y.com"  # type: ignore[misc]

    def test_empty_env_not_included(self):
        """Empty env dict should not produce an env key."""
        config = HttpServerConfig(url="https://x.com", transport_type="http", env={})
        d = config.to_dict()
        assert "env" not in d
