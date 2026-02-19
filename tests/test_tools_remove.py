"""Tests for the remove_server MCP tool (tools/remove.py)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from mcp_tap.errors import ConfigWriteError, McpTapError
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
    scope: str = "user",
) -> ConfigLocation:
    return ConfigLocation(client=client, path=path, scope=scope, exists=True)


# --- Single client tests --------------------------------------------------


class TestRemoveServerSingle:
    @patch("mcp_tap.tools.remove.remove_server_config")
    @patch("mcp_tap.tools.remove.resolve_config_locations")
    async def test_successful_removal_explicit_client(self, mock_locations, mock_remove):
        mock_locations.return_value = [_fake_location()]
        mock_remove.return_value = {"command": "npx", "args": ["-y", "my-server"]}

        result = await remove_server("my-server", _make_ctx(), clients="claude_code")

        assert result["success"] is True
        assert result["server_name"] == "my-server"
        assert "removed" in result["message"].lower()

    @patch("mcp_tap.tools.remove.remove_server_config")
    @patch("mcp_tap.tools.remove.resolve_config_locations")
    async def test_successful_removal_auto_detect(self, mock_locations, mock_remove):
        mock_locations.return_value = [_fake_location()]
        mock_remove.return_value = {"command": "npx"}

        result = await remove_server("my-server", _make_ctx())

        assert result["success"] is True
        assert result["server_name"] == "my-server"

    @patch("mcp_tap.tools.remove.resolve_config_locations")
    async def test_no_client_detected(self, mock_locations):
        mock_locations.return_value = []

        result = await remove_server("my-server", _make_ctx())

        assert result["success"] is False
        assert "No MCP client detected" in result["message"]

    @patch("mcp_tap.tools.remove.remove_server_config")
    @patch("mcp_tap.tools.remove.resolve_config_locations")
    async def test_server_not_found(self, mock_locations, mock_remove):
        mock_locations.return_value = [_fake_location()]
        mock_remove.return_value = None

        result = await remove_server("nonexistent", _make_ctx(), clients="claude_code")

        assert result["success"] is False
        assert "not found" in result["message"].lower()
        assert "list_installed" in result["message"]

    @patch("mcp_tap.tools.remove.resolve_config_locations")
    async def test_mcp_tap_error(self, mock_locations):
        mock_locations.side_effect = McpTapError("Permission denied")

        result = await remove_server("s", _make_ctx(), clients="claude_code")

        assert result["success"] is False
        assert "Permission denied" in result["message"]

    @patch("mcp_tap.tools.remove.resolve_config_locations")
    async def test_unexpected_error(self, mock_locations):
        mock_locations.side_effect = RuntimeError("disk failure")
        ctx = _make_ctx()

        result = await remove_server("s", ctx, clients="claude_code")

        assert result["success"] is False
        assert "RuntimeError" in result["message"]
        ctx.error.assert_awaited_once()

    @patch("mcp_tap.tools.remove.remove_server_config")
    @patch("mcp_tap.tools.remove.resolve_config_locations")
    async def test_result_includes_config_file(self, mock_locations, mock_remove):
        mock_locations.return_value = [_fake_location(path="/home/user/.config/claude.json")]
        mock_remove.return_value = {"command": "npx"}

        result = await remove_server("x", _make_ctx(), clients="claude_code")

        assert result["config_file"] == "/home/user/.config/claude.json"

    @patch("mcp_tap.tools.remove.remove_server_config")
    @patch("mcp_tap.tools.remove.resolve_config_locations")
    async def test_message_mentions_restart(self, mock_locations, mock_remove):
        mock_locations.return_value = [_fake_location()]
        mock_remove.return_value = {"command": "npx"}

        result = await remove_server("x", _make_ctx(), clients="claude_code")

        assert "restart" in result["message"].lower()

    @patch("mcp_tap.tools.remove.remove_server_config")
    @patch("mcp_tap.tools.remove.resolve_config_locations")
    async def test_scope_and_project_path_passed(self, mock_locations, mock_remove):
        mock_locations.return_value = [
            _fake_location(MCPClient.CURSOR, "/project/.cursor/mcp.json", scope="project")
        ]
        mock_remove.return_value = {"command": "npx"}

        await remove_server(
            "s", _make_ctx(), clients="cursor", scope="project", project_path="/project"
        )

        mock_locations.assert_called_once_with("cursor", scope="project", project_path="/project")


# --- Multi-client tests ---------------------------------------------------


class TestRemoveServerMulti:
    @patch("mcp_tap.tools.remove.remove_server_config")
    @patch("mcp_tap.tools.remove.resolve_config_locations")
    async def test_multi_client_all_removed(self, mock_locations, mock_remove):
        mock_locations.return_value = [
            _fake_location(MCPClient.CLAUDE_DESKTOP, "/a"),
            _fake_location(MCPClient.CURSOR, "/b"),
        ]
        mock_remove.return_value = {"command": "npx"}

        result = await remove_server("s", _make_ctx(), clients="claude_desktop,cursor")

        assert result["success"] is True
        assert "per_client_results" in result
        assert len(result["per_client_results"]) == 2
        assert result["per_client_results"][0]["removed"] is True
        assert result["per_client_results"][1]["removed"] is True
        assert "2/2" in result["message"]

    @patch("mcp_tap.tools.remove.remove_server_config")
    @patch("mcp_tap.tools.remove.resolve_config_locations")
    async def test_multi_client_not_found_in_one(self, mock_locations, mock_remove):
        mock_locations.return_value = [
            _fake_location(MCPClient.CLAUDE_DESKTOP, "/a"),
            _fake_location(MCPClient.CURSOR, "/b"),
        ]
        # Found in first, not in second
        mock_remove.side_effect = [{"command": "npx"}, None]

        result = await remove_server("s", _make_ctx(), clients="claude_desktop,cursor")

        assert result["success"] is True
        assert "1/2" in result["message"]
        per_client = result["per_client_results"]
        assert per_client[0]["removed"] is True
        assert per_client[1]["removed"] is False

    @patch("mcp_tap.tools.remove.remove_server_config")
    @patch("mcp_tap.tools.remove.resolve_config_locations")
    async def test_multi_client_none_found(self, mock_locations, mock_remove):
        mock_locations.return_value = [
            _fake_location(MCPClient.CLAUDE_DESKTOP, "/a"),
            _fake_location(MCPClient.CURSOR, "/b"),
        ]
        mock_remove.return_value = None

        result = await remove_server("s", _make_ctx(), clients="claude_desktop,cursor")

        assert result["success"] is False
        assert "not found in any" in result["message"].lower()

    @patch("mcp_tap.tools.remove.remove_server_config")
    @patch("mcp_tap.tools.remove.resolve_config_locations")
    async def test_multi_client_write_error_in_one(self, mock_locations, mock_remove):
        mock_locations.return_value = [
            _fake_location(MCPClient.CLAUDE_DESKTOP, "/a"),
            _fake_location(MCPClient.CURSOR, "/b"),
        ]
        mock_remove.side_effect = [{"command": "npx"}, ConfigWriteError("Permission denied")]

        result = await remove_server("s", _make_ctx(), clients="all")

        assert result["success"] is True
        per_client = result["per_client_results"]
        assert per_client[0]["removed"] is True
        assert per_client[1]["success"] is False
