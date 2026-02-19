"""Tests for the check_health MCP tool (tools/health.py)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from mcp_tap.errors import McpTapError
from mcp_tap.models import (
    ConfigLocation,
    ConnectionTestResult,
    InstalledServer,
    MCPClient,
    ServerConfig,
    ServerHealth,
)
from mcp_tap.tools.health import _check_all_servers, _check_single_server, check_health

# --- Helpers ---------------------------------------------------------------


def _make_ctx() -> MagicMock:
    """Build a mock Context with async info/error methods."""
    ctx = MagicMock()
    ctx.info = AsyncMock()
    ctx.error = AsyncMock()
    return ctx


def _fake_location(
    client: MCPClient = MCPClient.CLAUDE_CODE,
    path: str = "/tmp/fake_config.json",
    exists: bool = True,
) -> ConfigLocation:
    return ConfigLocation(client=client, path=path, scope="user", exists=exists)


def _installed_server(name: str = "test-server") -> InstalledServer:
    return InstalledServer(
        name=name,
        config=ServerConfig(command="npx", args=["-y", name]),
        source_file="/tmp/fake_config.json",
    )


def _ok_connection(
    server_name: str = "test-server",
    tools: list[str] | None = None,
) -> ConnectionTestResult:
    return ConnectionTestResult(
        success=True,
        server_name=server_name,
        tools_discovered=tools or ["tool_a", "tool_b"],
    )


def _failed_connection(
    server_name: str = "test-server",
    error: str = "Connection refused",
) -> ConnectionTestResult:
    return ConnectionTestResult(
        success=False,
        server_name=server_name,
        error=error,
    )


def _timeout_connection(server_name: str = "test-server") -> ConnectionTestResult:
    return ConnectionTestResult(
        success=False,
        server_name=server_name,
        error="Server did not respond within 15s. Check that the command exists.",
    )


# === check_health Tool Tests ================================================


class TestHealthAllHealthy:
    """Tests for check_health when all servers are healthy."""

    @patch("mcp_tap.tools.health.test_server_connection")
    @patch("mcp_tap.tools.health.parse_servers")
    @patch("mcp_tap.tools.health.read_config", return_value={"mcpServers": {}})
    @patch("mcp_tap.tools.health.detect_clients")
    async def test_three_healthy_servers(
        self,
        mock_detect: MagicMock,
        _mock_read: MagicMock,
        mock_parse: MagicMock,
        mock_test_conn: AsyncMock,
    ):
        """Should report healthy=3, unhealthy=0 when all servers connect."""
        mock_detect.return_value = [_fake_location()]
        servers = [
            _installed_server("server-a"),
            _installed_server("server-b"),
            _installed_server("server-c"),
        ]
        mock_parse.return_value = servers
        mock_test_conn.side_effect = [
            _ok_connection("server-a"),
            _ok_connection("server-b"),
            _ok_connection("server-c"),
        ]

        ctx = _make_ctx()
        result = await check_health(ctx)

        assert result["total"] == 3
        assert result["healthy"] == 3
        assert result["unhealthy"] == 0


class TestHealthMixed:
    """Tests for check_health with a mix of healthy and unhealthy servers."""

    @patch("mcp_tap.tools.health.test_server_connection")
    @patch("mcp_tap.tools.health.parse_servers")
    @patch("mcp_tap.tools.health.read_config", return_value={"mcpServers": {}})
    @patch("mcp_tap.tools.health.detect_clients")
    async def test_two_healthy_one_unhealthy(
        self,
        mock_detect: MagicMock,
        _mock_read: MagicMock,
        mock_parse: MagicMock,
        mock_test_conn: AsyncMock,
    ):
        """Should report healthy=2, unhealthy=1 when one server fails."""
        mock_detect.return_value = [_fake_location()]
        servers = [
            _installed_server("server-a"),
            _installed_server("server-b"),
            _installed_server("server-c"),
        ]
        mock_parse.return_value = servers
        mock_test_conn.side_effect = [
            _ok_connection("server-a"),
            _ok_connection("server-b"),
            _failed_connection("server-c"),
        ]

        ctx = _make_ctx()
        result = await check_health(ctx)

        assert result["total"] == 3
        assert result["healthy"] == 2
        assert result["unhealthy"] == 1


class TestHealthAllUnhealthy:
    """Tests for check_health when all servers fail."""

    @patch("mcp_tap.tools.health.test_server_connection")
    @patch("mcp_tap.tools.health.parse_servers")
    @patch("mcp_tap.tools.health.read_config", return_value={"mcpServers": {}})
    @patch("mcp_tap.tools.health.detect_clients")
    async def test_two_servers_both_fail(
        self,
        mock_detect: MagicMock,
        _mock_read: MagicMock,
        mock_parse: MagicMock,
        mock_test_conn: AsyncMock,
    ):
        """Should report healthy=0, unhealthy=2 when all servers fail."""
        mock_detect.return_value = [_fake_location()]
        servers = [
            _installed_server("server-a"),
            _installed_server("server-b"),
        ]
        mock_parse.return_value = servers
        mock_test_conn.side_effect = [
            _failed_connection("server-a"),
            _failed_connection("server-b"),
        ]

        ctx = _make_ctx()
        result = await check_health(ctx)

        assert result["total"] == 2
        assert result["healthy"] == 0
        assert result["unhealthy"] == 2


class TestHealthNoServers:
    """Tests for check_health with empty config."""

    @patch("mcp_tap.tools.health.parse_servers", return_value=[])
    @patch("mcp_tap.tools.health.read_config", return_value={"mcpServers": {}})
    @patch("mcp_tap.tools.health.detect_clients")
    async def test_empty_config(
        self,
        mock_detect: MagicMock,
        _mock_read: MagicMock,
        _mock_parse: MagicMock,
    ):
        """Should report total=0 when no servers are configured."""
        mock_detect.return_value = [_fake_location()]

        ctx = _make_ctx()
        result = await check_health(ctx)

        assert result["total"] == 0
        assert result["healthy"] == 0
        assert result["unhealthy"] == 0
        assert "No MCP servers configured" in result["message"]


class TestHealthNoClient:
    """Tests for check_health when no MCP client is detected."""

    @patch("mcp_tap.tools.health.detect_clients", return_value=[])
    async def test_no_client_detected(self, _mock_detect: MagicMock):
        """Should return a report with 'No MCP client detected' message."""
        ctx = _make_ctx()
        result = await check_health(ctx)

        assert result["total"] == 0
        assert "No MCP client detected" in result["message"]
        assert result["client"] == "none"


class TestHealthServerDetails:
    """Tests for per-server detail fields in the health report."""

    @patch("mcp_tap.tools.health.test_server_connection")
    @patch("mcp_tap.tools.health.parse_servers")
    @patch("mcp_tap.tools.health.read_config", return_value={"mcpServers": {}})
    @patch("mcp_tap.tools.health.detect_clients")
    async def test_healthy_server_details(
        self,
        mock_detect: MagicMock,
        _mock_read: MagicMock,
        mock_parse: MagicMock,
        mock_test_conn: AsyncMock,
    ):
        """Should include name, status, tools_count for healthy server."""
        mock_detect.return_value = [_fake_location()]
        mock_parse.return_value = [_installed_server("pg-mcp")]
        mock_test_conn.return_value = _ok_connection(
            "pg-mcp",
            tools=["read_query", "write_query"],
        )

        ctx = _make_ctx()
        result = await check_health(ctx)

        server = result["servers"][0]
        assert server["name"] == "pg-mcp"
        assert server["status"] == "healthy"
        assert server["tools_count"] == 2
        assert server["error"] == ""

    @patch("mcp_tap.tools.health.test_server_connection")
    @patch("mcp_tap.tools.health.parse_servers")
    @patch("mcp_tap.tools.health.read_config", return_value={"mcpServers": {}})
    @patch("mcp_tap.tools.health.detect_clients")
    async def test_unhealthy_server_details(
        self,
        mock_detect: MagicMock,
        _mock_read: MagicMock,
        mock_parse: MagicMock,
        mock_test_conn: AsyncMock,
    ):
        """Should include name, status='unhealthy', and error for failed server."""
        mock_detect.return_value = [_fake_location()]
        mock_parse.return_value = [_installed_server("broken-mcp")]
        mock_test_conn.return_value = _failed_connection(
            "broken-mcp",
            error="Connection refused",
        )

        ctx = _make_ctx()
        result = await check_health(ctx)

        server = result["servers"][0]
        assert server["name"] == "broken-mcp"
        assert server["status"] == "unhealthy"
        assert server["tools_count"] == 0
        assert "Connection refused" in server["error"]


class TestHealthToolsListed:
    """Tests that healthy servers have their tools list populated."""

    @patch("mcp_tap.tools.health.test_server_connection")
    @patch("mcp_tap.tools.health.parse_servers")
    @patch("mcp_tap.tools.health.read_config", return_value={"mcpServers": {}})
    @patch("mcp_tap.tools.health.detect_clients")
    async def test_tools_list_populated(
        self,
        mock_detect: MagicMock,
        _mock_read: MagicMock,
        mock_parse: MagicMock,
        mock_test_conn: AsyncMock,
    ):
        """Should populate tools list for a healthy server."""
        mock_detect.return_value = [_fake_location()]
        mock_parse.return_value = [_installed_server("pg-mcp")]
        expected_tools = ["read_query", "write_query", "create_table"]
        mock_test_conn.return_value = _ok_connection("pg-mcp", tools=expected_tools)

        ctx = _make_ctx()
        result = await check_health(ctx)

        server = result["servers"][0]
        assert server["tools"] == expected_tools
        assert server["tools_count"] == 3


class TestHealthTimeoutReported:
    """Tests that server timeouts are reported with status='timeout'."""

    @patch("mcp_tap.tools.health.test_server_connection")
    @patch("mcp_tap.tools.health.parse_servers")
    @patch("mcp_tap.tools.health.read_config", return_value={"mcpServers": {}})
    @patch("mcp_tap.tools.health.detect_clients")
    async def test_timeout_status(
        self,
        mock_detect: MagicMock,
        _mock_read: MagicMock,
        mock_parse: MagicMock,
        mock_test_conn: AsyncMock,
    ):
        """Should set status='timeout' for server that times out."""
        mock_detect.return_value = [_fake_location()]
        mock_parse.return_value = [_installed_server("slow-mcp")]
        mock_test_conn.return_value = _timeout_connection("slow-mcp")

        ctx = _make_ctx()
        result = await check_health(ctx)

        server = result["servers"][0]
        assert server["status"] == "timeout"
        assert "did not respond within" in server["error"]


class TestHealthConcurrent:
    """Tests that check_health runs server checks concurrently."""

    @patch("mcp_tap.tools.health.test_server_connection")
    async def test_asyncio_gather_is_used(self, mock_test_conn: AsyncMock):
        """Should use asyncio.gather to run checks concurrently."""
        # Create multiple servers and verify they are all checked
        servers = [
            _installed_server("server-a"),
            _installed_server("server-b"),
            _installed_server("server-c"),
        ]
        mock_test_conn.side_effect = [
            _ok_connection("server-a"),
            _ok_connection("server-b"),
            _ok_connection("server-c"),
        ]

        # Call the internal _check_all_servers which uses asyncio.gather
        results = await _check_all_servers(servers, timeout_seconds=15)

        assert len(results) == 3
        assert mock_test_conn.call_count == 3
        # All should be healthy
        assert all(r.status == "healthy" for r in results)


class TestHealthExplicitClient:
    """Tests for passing client parameter explicitly."""

    @patch("mcp_tap.tools.health.test_server_connection")
    @patch("mcp_tap.tools.health.parse_servers")
    @patch("mcp_tap.tools.health.read_config", return_value={"mcpServers": {}})
    @patch("mcp_tap.tools.health.resolve_config_path")
    async def test_explicit_client_parameter(
        self,
        mock_resolve: MagicMock,
        _mock_read: MagicMock,
        mock_parse: MagicMock,
        mock_test_conn: AsyncMock,
    ):
        """Should use resolve_config_path when client is provided explicitly."""
        mock_resolve.return_value = _fake_location(client=MCPClient.CURSOR)
        mock_parse.return_value = [_installed_server("my-server")]
        mock_test_conn.return_value = _ok_connection("my-server")

        ctx = _make_ctx()
        result = await check_health(ctx, client="cursor")

        mock_resolve.assert_called_once_with(MCPClient.CURSOR)
        assert result["client"] == "cursor"
        assert result["total"] == 1


# === _check_all_servers Unit Tests ==========================================


class TestCheckAllServersExceptionHandling:
    """Tests for _check_all_servers exception handling via asyncio.gather."""

    @patch("mcp_tap.tools.health.test_server_connection")
    async def test_exception_in_one_server_does_not_block_others(
        self,
        mock_test_conn: AsyncMock,
    ):
        """Should handle exception from one server and still check the rest."""
        servers = [
            _installed_server("good-server"),
            _installed_server("bad-server"),
        ]
        mock_test_conn.side_effect = [
            _ok_connection("good-server"),
            RuntimeError("Unexpected boom"),
        ]

        results = await _check_all_servers(servers, timeout_seconds=15)

        assert len(results) == 2
        assert results[0].status == "healthy"
        assert results[1].status == "unhealthy"
        assert "RuntimeError" in results[1].error


# === _check_single_server Unit Tests ========================================


class TestCheckSingleServer:
    """Tests for the _check_single_server helper."""

    @patch("mcp_tap.tools.health.test_server_connection")
    async def test_healthy_server(self, mock_test_conn: AsyncMock):
        """Should return ServerHealth with status='healthy' on success."""
        server = _installed_server("pg-mcp")
        mock_test_conn.return_value = _ok_connection(
            "pg-mcp",
            tools=["read_query"],
        )

        result = await _check_single_server(server, timeout_seconds=15)

        assert isinstance(result, ServerHealth)
        assert result.status == "healthy"
        assert result.tools_count == 1
        assert result.tools == ["read_query"]

    @patch("mcp_tap.tools.health.test_server_connection")
    async def test_unhealthy_server(self, mock_test_conn: AsyncMock):
        """Should return ServerHealth with status='unhealthy' on failure."""
        server = _installed_server("broken-mcp")
        mock_test_conn.return_value = _failed_connection(
            "broken-mcp",
            error="Command not found: npx",
        )

        result = await _check_single_server(server, timeout_seconds=15)

        assert result.status == "unhealthy"
        assert "Command not found" in result.error

    @patch("mcp_tap.tools.health.test_server_connection")
    async def test_timeout_server(self, mock_test_conn: AsyncMock):
        """Should return ServerHealth with status='timeout' for timeout error."""
        server = _installed_server("slow-mcp")
        mock_test_conn.return_value = _timeout_connection("slow-mcp")

        result = await _check_single_server(server, timeout_seconds=15)

        assert result.status == "timeout"


# === Unexpected Error Handling Tests =========================================


class TestHealthUnexpectedErrors:
    """Tests for unexpected exception handling in check_health."""

    @patch(
        "mcp_tap.tools.health.detect_clients",
        side_effect=RuntimeError("filesystem exploded"),
    )
    async def test_unexpected_error_returns_error_dict(
        self,
        _mock_detect: MagicMock,
    ):
        """Should return error dict for unexpected exceptions."""
        ctx = _make_ctx()
        result = await check_health(ctx)

        assert result["success"] is False
        assert "Internal error" in result["error"]
        ctx.error.assert_awaited_once()

    @patch(
        "mcp_tap.tools.health.detect_clients",
        side_effect=McpTapError("config broken"),
    )
    async def test_mcp_tap_error_returns_error_dict(
        self,
        _mock_detect: MagicMock,
    ):
        """Should return error dict for McpTapError."""
        ctx = _make_ctx()
        result = await check_health(ctx)

        assert result["success"] is False
        assert "config broken" in result["error"]


# === Timeout Clamping Tests ==================================================


class TestHealthTimeoutClamping:
    """Tests for the timeout clamping logic (5-60 seconds)."""

    @patch("mcp_tap.tools.health.test_server_connection")
    @patch("mcp_tap.tools.health.parse_servers")
    @patch("mcp_tap.tools.health.read_config", return_value={"mcpServers": {}})
    @patch("mcp_tap.tools.health.detect_clients")
    async def test_timeout_below_minimum_clamped_to_5(
        self,
        mock_detect: MagicMock,
        _mock_read: MagicMock,
        mock_parse: MagicMock,
        mock_test_conn: AsyncMock,
    ):
        """Should clamp timeout_seconds to 5 when below minimum."""
        mock_detect.return_value = [_fake_location()]
        mock_parse.return_value = [_installed_server("s")]
        mock_test_conn.return_value = _ok_connection("s")

        ctx = _make_ctx()
        await check_health(ctx, timeout_seconds=1)

        # Verify test_server_connection was called with clamped timeout (5)
        call_kwargs = mock_test_conn.call_args
        assert call_kwargs[1]["timeout_seconds"] == 5

    @patch("mcp_tap.tools.health.test_server_connection")
    @patch("mcp_tap.tools.health.parse_servers")
    @patch("mcp_tap.tools.health.read_config", return_value={"mcpServers": {}})
    @patch("mcp_tap.tools.health.detect_clients")
    async def test_timeout_above_maximum_clamped_to_60(
        self,
        mock_detect: MagicMock,
        _mock_read: MagicMock,
        mock_parse: MagicMock,
        mock_test_conn: AsyncMock,
    ):
        """Should clamp timeout_seconds to 60 when above maximum."""
        mock_detect.return_value = [_fake_location()]
        mock_parse.return_value = [_installed_server("s")]
        mock_test_conn.return_value = _ok_connection("s")

        ctx = _make_ctx()
        await check_health(ctx, timeout_seconds=999)

        call_kwargs = mock_test_conn.call_args
        assert call_kwargs[1]["timeout_seconds"] == 60


# === Semaphore Concurrency Limiting (Fix C4) ==================================


class TestHealthSemaphoreConcurrency:
    """Tests for _MAX_CONCURRENT_CHECKS semaphore limiting in _check_all_servers."""

    def test_max_concurrent_checks_constant_is_five(self):
        """Should have _MAX_CONCURRENT_CHECKS set to 5."""
        from mcp_tap.tools.health import _MAX_CONCURRENT_CHECKS

        assert _MAX_CONCURRENT_CHECKS == 5

    @patch("mcp_tap.tools.health.test_server_connection")
    async def test_semaphore_limits_concurrency_to_five(
        self,
        mock_test_conn: AsyncMock,
    ):
        """Should run at most 5 checks concurrently when given 10 servers."""
        max_concurrent = 0
        current_concurrent = 0
        lock = asyncio.Lock()

        async def _track_concurrency(*args, **kwargs):
            nonlocal max_concurrent, current_concurrent
            async with lock:
                current_concurrent += 1
                if current_concurrent > max_concurrent:
                    max_concurrent = current_concurrent

            # Simulate some work so tasks overlap
            await asyncio.sleep(0.01)

            async with lock:
                current_concurrent -= 1

            server_name = args[0] if args else kwargs.get("server_name", "unknown")
            return _ok_connection(server_name)

        mock_test_conn.side_effect = _track_concurrency

        servers = [_installed_server(f"server-{i}") for i in range(10)]
        results = await _check_all_servers(servers, timeout_seconds=15)

        assert len(results) == 10
        assert max_concurrent <= 5
        assert mock_test_conn.call_count == 10

    @patch("mcp_tap.tools.health.test_server_connection")
    async def test_all_servers_checked_with_semaphore(
        self,
        mock_test_conn: AsyncMock,
    ):
        """Should check all servers even with semaphore limiting."""
        servers = [_installed_server(f"server-{i}") for i in range(8)]
        mock_test_conn.side_effect = [_ok_connection(f"server-{i}") for i in range(8)]

        results = await _check_all_servers(servers, timeout_seconds=15)

        assert len(results) == 8
        assert all(r.status == "healthy" for r in results)

    @patch("mcp_tap.tools.health.test_server_connection")
    async def test_semaphore_with_failures_still_checks_all(
        self,
        mock_test_conn: AsyncMock,
    ):
        """Should check all servers when some fail under semaphore."""
        servers = [_installed_server(f"server-{i}") for i in range(7)]
        mock_test_conn.side_effect = [
            _ok_connection("server-0"),
            _failed_connection("server-1"),
            _ok_connection("server-2"),
            RuntimeError("boom"),
            _ok_connection("server-4"),
            _failed_connection("server-5"),
            _ok_connection("server-6"),
        ]

        results = await _check_all_servers(servers, timeout_seconds=15)

        assert len(results) == 7
        assert mock_test_conn.call_count == 7
