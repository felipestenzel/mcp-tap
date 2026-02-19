"""Tests for domain models."""

from __future__ import annotations

from mcp_tap.models import ServerConfig


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
        with __import__("pytest").raises(AttributeError):
            config.command = "y"  # type: ignore[misc]
