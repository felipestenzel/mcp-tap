"""Tests for the remove_server MCP tool (tools/remove.py)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from mcp_tap.errors import McpTapError
from mcp_tap.models import ConfigLocation, MCPClient
from mcp_tap.tools.remove import remove_server

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


# --- remove_server tests --------------------------------------------------


class TestRemoveServer:
    @patch("mcp_tap.tools.remove.remove_server_config")
    @patch("mcp_tap.tools.remove.resolve_config_path")
    async def test_successful_removal_explicit_client(self, mock_resolve, mock_remove):
        mock_resolve.return_value = _fake_location()
        mock_remove.return_value = {"command": "npx", "args": ["-y", "my-server"]}

        result = await remove_server("my-server", _make_ctx(), client="claude_code")

        assert result["success"] is True
        assert result["server_name"] == "my-server"
        assert "removed" in result["message"].lower()
        mock_resolve.assert_called_once_with(MCPClient("claude_code"))
        mock_remove.assert_called_once()

    @patch("mcp_tap.tools.remove.remove_server_config")
    @patch("mcp_tap.tools.remove.detect_clients")
    async def test_successful_removal_auto_detect(self, mock_detect, mock_remove):
        mock_detect.return_value = [_fake_location()]
        mock_remove.return_value = {"command": "npx"}

        result = await remove_server("my-server", _make_ctx())

        assert result["success"] is True
        assert result["server_name"] == "my-server"

    @patch("mcp_tap.tools.remove.detect_clients")
    async def test_no_client_detected(self, mock_detect):
        mock_detect.return_value = []

        result = await remove_server("my-server", _make_ctx())

        assert result["success"] is False
        assert "No MCP client detected" in result["message"]

    @patch("mcp_tap.tools.remove.remove_server_config")
    @patch("mcp_tap.tools.remove.resolve_config_path")
    async def test_server_not_found(self, mock_resolve, mock_remove):
        mock_resolve.return_value = _fake_location()
        mock_remove.return_value = None

        result = await remove_server("nonexistent", _make_ctx(), client="claude_code")

        assert result["success"] is False
        assert "not found" in result["message"].lower()
        assert "list_installed" in result["message"]

    @patch("mcp_tap.tools.remove.resolve_config_path")
    async def test_mcp_tap_error(self, mock_resolve):
        mock_resolve.side_effect = McpTapError("Permission denied")

        result = await remove_server("s", _make_ctx(), client="claude_code")

        assert result["success"] is False
        assert "Permission denied" in result["message"]

    @patch("mcp_tap.tools.remove.resolve_config_path")
    async def test_unexpected_error(self, mock_resolve):
        mock_resolve.side_effect = RuntimeError("disk failure")
        ctx = _make_ctx()

        result = await remove_server("s", ctx, client="claude_code")

        assert result["success"] is False
        assert "RuntimeError" in result["message"]
        ctx.error.assert_awaited_once()

    @patch("mcp_tap.tools.remove.remove_server_config")
    @patch("mcp_tap.tools.remove.resolve_config_path")
    async def test_result_includes_config_file(self, mock_resolve, mock_remove):
        mock_resolve.return_value = _fake_location(path="/home/user/.config/claude.json")
        mock_remove.return_value = {"command": "npx"}

        result = await remove_server("x", _make_ctx(), client="claude_code")

        assert result["config_file"] == "/home/user/.config/claude.json"

    @patch("mcp_tap.tools.remove.remove_server_config")
    @patch("mcp_tap.tools.remove.resolve_config_path")
    async def test_message_mentions_restart(self, mock_resolve, mock_remove):
        mock_resolve.return_value = _fake_location()
        mock_remove.return_value = {"command": "npx"}

        result = await remove_server("x", _make_ctx(), client="claude_code")

        assert "restart" in result["message"].lower()
