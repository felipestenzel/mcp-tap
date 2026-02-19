"""Tests for the test_connection MCP tool (tools/test.py)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from mcp_tap.errors import McpTapError
from mcp_tap.models import (
    ConfigLocation,
    ConnectionTestResult,
    InstalledServer,
    MCPClient,
    ServerConfig,
)
from mcp_tap.tools.test import test_connection as _tool_test_connection

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


def _installed_server(name: str = "test-server") -> InstalledServer:
    return InstalledServer(
        name=name,
        config=ServerConfig(command="npx", args=["-y", name]),
        source_file="/tmp/fake_config.json",
    )


def _ok_result(name: str = "test-server") -> ConnectionTestResult:
    return ConnectionTestResult(
        success=True,
        server_name=name,
        tools_discovered=["tool_a", "tool_b"],
    )


def _failed_result(name: str = "test-server") -> ConnectionTestResult:
    return ConnectionTestResult(
        success=False,
        server_name=name,
        error="Connection refused",
    )


# --- test_connection tests --------------------------------------------------


class TestTestConnection:
    @patch("mcp_tap.tools.test.test_server_connection", new_callable=AsyncMock)
    @patch("mcp_tap.tools.test.parse_servers")
    @patch("mcp_tap.tools.test.read_config")
    @patch("mcp_tap.tools.test.resolve_config_path")
    async def test_happy_path_explicit_client(
        self, mock_resolve, mock_read, mock_parse, mock_tester
    ):
        mock_resolve.return_value = _fake_location()
        mock_read.return_value = {"mcpServers": {}}
        mock_parse.return_value = [_installed_server("my-server")]
        mock_tester.return_value = _ok_result("my-server")

        result = await _tool_test_connection("my-server", _make_ctx(), client="claude_code")

        assert result["success"] is True
        assert result["server_name"] == "my-server"
        assert result["tools_discovered"] == ["tool_a", "tool_b"]
        mock_resolve.assert_called_once_with(MCPClient("claude_code"))

    @patch("mcp_tap.tools.test.test_server_connection", new_callable=AsyncMock)
    @patch("mcp_tap.tools.test.parse_servers")
    @patch("mcp_tap.tools.test.read_config")
    @patch("mcp_tap.tools.test.detect_clients")
    async def test_happy_path_auto_detect(self, mock_detect, mock_read, mock_parse, mock_tester):
        mock_detect.return_value = [_fake_location()]
        mock_read.return_value = {"mcpServers": {}}
        mock_parse.return_value = [_installed_server()]
        mock_tester.return_value = _ok_result()

        result = await _tool_test_connection("test-server", _make_ctx())

        assert result["success"] is True

    @patch("mcp_tap.tools.test.detect_clients")
    async def test_no_client_detected(self, mock_detect):
        mock_detect.return_value = []

        result = await _tool_test_connection("test-server", _make_ctx())

        assert result["success"] is False
        assert "No MCP client detected" in result["error"]

    @patch("mcp_tap.tools.test.parse_servers")
    @patch("mcp_tap.tools.test.read_config")
    @patch("mcp_tap.tools.test.resolve_config_path")
    async def test_server_not_found_in_config(self, mock_resolve, mock_read, mock_parse):
        mock_resolve.return_value = _fake_location()
        mock_read.return_value = {"mcpServers": {}}
        mock_parse.return_value = [_installed_server("other-server")]

        result = await _tool_test_connection("nonexistent", _make_ctx(), client="claude_code")

        assert result["success"] is False
        assert "not found" in result["error"].lower()

    @patch("mcp_tap.tools.test.test_server_connection", new_callable=AsyncMock)
    @patch("mcp_tap.tools.test.parse_servers")
    @patch("mcp_tap.tools.test.read_config")
    @patch("mcp_tap.tools.test.resolve_config_path")
    async def test_connection_failure(self, mock_resolve, mock_read, mock_parse, mock_tester):
        mock_resolve.return_value = _fake_location()
        mock_read.return_value = {"mcpServers": {}}
        mock_parse.return_value = [_installed_server()]
        mock_tester.return_value = _failed_result()

        result = await _tool_test_connection("test-server", _make_ctx(), client="claude_code")

        assert result["success"] is False
        assert result["error"] == "Connection refused"

    @patch("mcp_tap.tools.test.test_server_connection", new_callable=AsyncMock)
    @patch("mcp_tap.tools.test.parse_servers")
    @patch("mcp_tap.tools.test.read_config")
    @patch("mcp_tap.tools.test.resolve_config_path")
    async def test_timeout_clamped_to_range(self, mock_resolve, mock_read, mock_parse, mock_tester):
        mock_resolve.return_value = _fake_location()
        mock_read.return_value = {"mcpServers": {}}
        mock_parse.return_value = [_installed_server()]
        mock_tester.return_value = _ok_result()

        # timeout_seconds=1 should be clamped to min 5
        await _tool_test_connection(
            "test-server", _make_ctx(), client="claude_code", timeout_seconds=1
        )
        _, kwargs = mock_tester.call_args
        assert kwargs["timeout_seconds"] == 5

        # timeout_seconds=100 should be clamped to max 60
        await _tool_test_connection(
            "test-server", _make_ctx(), client="claude_code", timeout_seconds=100
        )
        _, kwargs = mock_tester.call_args
        assert kwargs["timeout_seconds"] == 60

    @patch("mcp_tap.tools.test.resolve_config_path")
    async def test_mcp_tap_error(self, mock_resolve):
        mock_resolve.side_effect = McpTapError("Config unreadable")

        result = await _tool_test_connection("s", _make_ctx(), client="claude_code")

        assert result["success"] is False
        assert "Config unreadable" in result["error"]

    @patch("mcp_tap.tools.test.resolve_config_path")
    async def test_unexpected_error(self, mock_resolve):
        mock_resolve.side_effect = RuntimeError("segfault")
        ctx = _make_ctx()

        result = await _tool_test_connection("s", ctx, client="claude_code")

        assert result["success"] is False
        assert "RuntimeError" in result["error"]
        ctx.error.assert_awaited_once()
