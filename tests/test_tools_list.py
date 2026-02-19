"""Tests for the list_installed MCP tool (tools/list.py)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from mcp_tap.errors import McpTapError
from mcp_tap.models import (
    ConfigLocation,
    InstalledServer,
    MCPClient,
    ServerConfig,
)
from mcp_tap.tools.list import _mask_env, list_installed

# --- Helpers ---------------------------------------------------------------


def _make_ctx() -> MagicMock:
    ctx = MagicMock()
    ctx.info = AsyncMock()
    ctx.error = AsyncMock()
    return ctx


def _fake_location(
    client: MCPClient = MCPClient.CLAUDE_CODE,
    path: str = "/tmp/fake_config.json",
) -> ConfigLocation:
    return ConfigLocation(client=client, path=path, scope="user", exists=True)


def _installed_server(
    name: str = "test-server",
    env: dict[str, str] | None = None,
) -> InstalledServer:
    return InstalledServer(
        name=name,
        config=ServerConfig(command="npx", args=["-y", name], env=env or {}),
        source_file="/tmp/fake_config.json",
    )


# --- _mask_env tests -------------------------------------------------------


class TestMaskEnv:
    def test_short_values_not_masked(self):
        env = {"PORT": "3000", "HOST": "localhost"}
        assert _mask_env(env) == {"PORT": "3000", "HOST": "localhost"}

    def test_long_alphanumeric_values_masked(self):
        env = {"API_KEY": "sk_abcdefghijklmnopqrstuvwxyz1234"}
        result = _mask_env(env)
        assert result["API_KEY"] == "***"

    def test_base64_token_masked(self):
        env = {"TOKEN": "eyJhbGciOiJIUzI1NiIs"}
        result = _mask_env(env)
        assert result["TOKEN"] == "***"

    def test_mixed_env(self):
        env = {
            "DEBUG": "true",
            "SECRET": "AAAAAAAAAAAAAAAAAAAAAA",
            "NAME": "my-app",
        }
        result = _mask_env(env)
        assert result["DEBUG"] == "true"
        assert result["SECRET"] == "***"
        assert result["NAME"] == "my-app"

    def test_empty_dict(self):
        assert _mask_env({}) == {}


# --- list_installed tests --------------------------------------------------


class TestListInstalled:
    @patch("mcp_tap.tools.list.parse_servers")
    @patch("mcp_tap.tools.list.read_config")
    @patch("mcp_tap.tools.list.resolve_config_path")
    async def test_explicit_client(self, mock_resolve, mock_read, mock_parse):
        mock_resolve.return_value = _fake_location()
        mock_read.return_value = {"mcpServers": {}}
        server = _installed_server("my-server", env={"PORT": "8080"})
        mock_parse.return_value = [server]

        result = await list_installed(_make_ctx(), client="claude_code")

        assert len(result) == 1
        assert result[0]["name"] == "my-server"
        assert result[0]["command"] == "npx"
        assert result[0]["args"] == ["-y", "my-server"]
        assert result[0]["env"] == {"PORT": "8080"}
        mock_resolve.assert_called_once_with(MCPClient("claude_code"))

    @patch("mcp_tap.tools.list.parse_servers")
    @patch("mcp_tap.tools.list.read_config")
    @patch("mcp_tap.tools.list.detect_clients")
    async def test_auto_detect_client(self, mock_detect, mock_read, mock_parse):
        mock_detect.return_value = [_fake_location()]
        mock_read.return_value = {"mcpServers": {}}
        mock_parse.return_value = [_installed_server()]

        result = await list_installed(_make_ctx())

        assert len(result) == 1
        assert result[0]["name"] == "test-server"
        mock_detect.assert_called_once()

    @patch("mcp_tap.tools.list.detect_clients")
    async def test_no_client_detected(self, mock_detect):
        mock_detect.return_value = []

        result = await list_installed(_make_ctx())

        assert len(result) == 1
        assert result[0]["message"] == "No MCP client detected on this machine."

    @patch("mcp_tap.tools.list.parse_servers")
    @patch("mcp_tap.tools.list.read_config")
    @patch("mcp_tap.tools.list.detect_clients")
    async def test_empty_config(self, mock_detect, mock_read, mock_parse):
        mock_detect.return_value = [_fake_location()]
        mock_read.return_value = {"mcpServers": {}}
        mock_parse.return_value = []

        result = await list_installed(_make_ctx())

        assert result == []

    @patch("mcp_tap.tools.list.parse_servers")
    @patch("mcp_tap.tools.list.read_config")
    @patch("mcp_tap.tools.list.detect_clients")
    async def test_secrets_masked_in_output(self, mock_detect, mock_read, mock_parse):
        mock_detect.return_value = [_fake_location()]
        mock_read.return_value = {"mcpServers": {}}
        mock_parse.return_value = [
            _installed_server("s", env={"API_KEY": "sk_abcdefghijklmnopqrstuvwxyz"})
        ]

        result = await list_installed(_make_ctx())

        assert result[0]["env"]["API_KEY"] == "***"

    @patch("mcp_tap.tools.list.parse_servers")
    @patch("mcp_tap.tools.list.read_config")
    @patch("mcp_tap.tools.list.detect_clients")
    async def test_multiple_servers(self, mock_detect, mock_read, mock_parse):
        mock_detect.return_value = [_fake_location()]
        mock_read.return_value = {"mcpServers": {}}
        mock_parse.return_value = [
            _installed_server("server-a"),
            _installed_server("server-b"),
        ]

        result = await list_installed(_make_ctx())

        assert len(result) == 2
        names = {r["name"] for r in result}
        assert names == {"server-a", "server-b"}

    @patch("mcp_tap.tools.list.resolve_config_path")
    async def test_mcp_tap_error_returns_error_dict(self, mock_resolve):
        mock_resolve.side_effect = McpTapError("Config broken")

        result = await list_installed(_make_ctx(), client="claude_code")

        assert len(result) == 1
        assert result[0]["success"] is False
        assert "Config broken" in result[0]["error"]

    @patch("mcp_tap.tools.list.resolve_config_path")
    async def test_unexpected_error_returns_error_dict(self, mock_resolve):
        mock_resolve.side_effect = RuntimeError("boom")
        ctx = _make_ctx()

        result = await list_installed(ctx, client="claude_code")

        assert len(result) == 1
        assert result[0]["success"] is False
        assert "RuntimeError" in result[0]["error"]
        ctx.error.assert_awaited_once()
