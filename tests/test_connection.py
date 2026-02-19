"""Tests for the connection tester (connection/tester.py)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from mcp_tap.connection.tester import test_server_connection as _test_server_conn
from mcp_tap.models import ServerConfig

# --- Helpers ---------------------------------------------------------------


def _server_config(
    command: str = "npx",
    args: list[str] | None = None,
    env: dict[str, str] | None = None,
) -> ServerConfig:
    return ServerConfig(command=command, args=args or ["-y", "test-server"], env=env or {})


# --- test_server_connection tests ------------------------------------------


class TestServerConnection:
    @patch("mcp_tap.connection.tester.stdio_client")
    async def test_happy_path(self, mock_stdio):
        # Build mock tool objects
        tool_a = MagicMock()
        tool_a.name = "tool_a"
        tool_b = MagicMock()
        tool_b.name = "tool_b"

        tools_result = MagicMock()
        tools_result.tools = [tool_a, tool_b]

        # Mock session
        mock_session = AsyncMock()
        mock_session.initialize = AsyncMock()
        mock_session.list_tools = AsyncMock(return_value=tools_result)

        # Set up nested async context managers
        mock_session_cm = AsyncMock()
        mock_session_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_cm.__aexit__ = AsyncMock(return_value=False)

        mock_streams = (MagicMock(), MagicMock())
        mock_stdio_cm = AsyncMock()
        mock_stdio_cm.__aenter__ = AsyncMock(return_value=mock_streams)
        mock_stdio_cm.__aexit__ = AsyncMock(return_value=False)
        mock_stdio.return_value = mock_stdio_cm

        with patch("mcp_tap.connection.tester.ClientSession") as mock_cs_cls:
            mock_cs_cls.return_value = mock_session_cm

            result = await _test_server_conn("my-server", _server_config())

        assert result.success is True
        assert result.server_name == "my-server"
        assert result.tools_discovered == ["tool_a", "tool_b"]

    async def test_timeout_error(self):
        """When the server doesn't respond in time, we get a timeout result."""
        with patch(
            "mcp_tap.connection.tester.stdio_client",
            side_effect=TimeoutError("timed out"),
        ):
            result = await _test_server_conn("slow-server", _server_config(), timeout_seconds=5)

        assert result.success is False
        assert "5s" in result.error
        assert result.server_name == "slow-server"

    async def test_command_not_found(self):
        """When the command doesn't exist, we get a FileNotFoundError result."""
        exc = FileNotFoundError("No such file")
        exc.filename = "nonexistent-cmd"
        with patch("mcp_tap.connection.tester.stdio_client", side_effect=exc):
            result = await _test_server_conn("bad-server", _server_config())

        assert result.success is False
        assert "not found" in result.error.lower()
        assert "nonexistent-cmd" in result.error

    async def test_generic_exception(self):
        """Other exceptions are caught and reported."""
        with patch(
            "mcp_tap.connection.tester.stdio_client",
            side_effect=ConnectionError("refused"),
        ):
            result = await _test_server_conn("x", _server_config())

        assert result.success is False
        assert "ConnectionError" in result.error

    async def test_empty_env_passed_as_none(self):
        """Empty env dict should become None in StdioServerParameters."""
        with patch("mcp_tap.connection.tester.stdio_client") as mock_stdio:
            mock_stdio.side_effect = TimeoutError("quick exit")

            await _test_server_conn("test", ServerConfig(command="npx", args=[], env={}))

            call_args = mock_stdio.call_args[0][0]
            assert call_args.env is None
