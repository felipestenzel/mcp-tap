"""Tests for tool conflict detection (tools/conflicts.py)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from mcp_tap.models import (
    ConfigLocation,
    InstalledServer,
    MCPClient,
    ServerConfig,
    ServerHealth,
    ToolConflict,
)
from mcp_tap.tools.conflicts import detect_tool_conflicts

# --- Helpers ---------------------------------------------------------------


def _healthy(name: str, tools: list[str]) -> ServerHealth:
    return ServerHealth(
        name=name,
        status="healthy",
        tools_count=len(tools),
        tools=tools,
    )


def _unhealthy(name: str, tools: list[str] | None = None) -> ServerHealth:
    return ServerHealth(
        name=name,
        status="unhealthy",
        tools=tools or [],
        error="Connection refused",
    )


def _make_ctx(*, connection_tester: AsyncMock | None = None) -> MagicMock:
    from mcp_tap.server import AppContext

    app = MagicMock(spec=AppContext)
    app.connection_tester = connection_tester or AsyncMock()
    app.healing = AsyncMock()

    ctx = MagicMock()
    ctx.request_context.lifespan_context = app
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


# === Unit Tests: detect_tool_conflicts ======================================


class TestNoConflicts:
    """Tests when all tool names are unique across servers."""

    def test_unique_tools_returns_empty(self):
        """Should return no conflicts when each server has unique tools."""
        healths = [
            _healthy("server-a", ["tool_x", "tool_y"]),
            _healthy("server-b", ["tool_z", "tool_w"]),
        ]
        assert detect_tool_conflicts(healths) == []

    def test_single_server_no_conflict(self):
        """Should return no conflicts with only one server."""
        healths = [_healthy("server-a", ["tool_x", "tool_y"])]
        assert detect_tool_conflicts(healths) == []


class TestSingleConflict:
    """Tests detecting a single tool name conflict."""

    def test_two_servers_share_one_tool(self):
        """Should detect conflict when two servers expose the same tool."""
        healths = [
            _healthy("server-a", ["shared_tool", "unique_a"]),
            _healthy("server-b", ["shared_tool", "unique_b"]),
        ]
        conflicts = detect_tool_conflicts(healths)

        assert len(conflicts) == 1
        assert conflicts[0].tool_name == "shared_tool"
        assert sorted(conflicts[0].servers) == ["server-a", "server-b"]

    def test_three_servers_share_one_tool(self):
        """Should list all three servers in the conflict."""
        healths = [
            _healthy("alpha", ["read_query"]),
            _healthy("beta", ["read_query"]),
            _healthy("gamma", ["read_query"]),
        ]
        conflicts = detect_tool_conflicts(healths)

        assert len(conflicts) == 1
        assert conflicts[0].tool_name == "read_query"
        assert len(conflicts[0].servers) == 3


class TestMultipleConflicts:
    """Tests detecting more than one conflicting tool name."""

    def test_two_conflicts_detected(self):
        """Should return one ToolConflict per duplicated tool name."""
        healths = [
            _healthy("server-a", ["read", "write"]),
            _healthy("server-b", ["read", "write", "delete"]),
        ]
        conflicts = detect_tool_conflicts(healths)

        assert len(conflicts) == 2
        tool_names = [c.tool_name for c in conflicts]
        assert "read" in tool_names
        assert "write" in tool_names

    def test_conflicts_sorted_alphabetically(self):
        """Should return conflicts sorted by tool name."""
        healths = [
            _healthy("a", ["zebra", "apple"]),
            _healthy("b", ["zebra", "apple"]),
        ]
        conflicts = detect_tool_conflicts(healths)

        assert conflicts[0].tool_name == "apple"
        assert conflicts[1].tool_name == "zebra"


class TestSkipUnhealthy:
    """Tests that unhealthy servers are excluded from conflict detection."""

    def test_unhealthy_server_excluded(self):
        """Should ignore tools from unhealthy servers."""
        healths = [
            _healthy("server-a", ["shared_tool"]),
            _unhealthy("server-b", ["shared_tool"]),
        ]
        assert detect_tool_conflicts(healths) == []

    def test_timeout_server_excluded(self):
        """Should ignore tools from servers with timeout status."""
        healths = [
            _healthy("server-a", ["shared_tool"]),
            ServerHealth(
                name="server-b",
                status="timeout",
                tools=["shared_tool"],
                error="did not respond within 15s",
            ),
        ]
        assert detect_tool_conflicts(healths) == []

    def test_mixed_healthy_unhealthy_only_healthy_conflict(self):
        """Should only report conflicts among healthy servers."""
        healths = [
            _healthy("server-a", ["shared_tool", "unique_a"]),
            _unhealthy("server-b", ["shared_tool"]),
            _healthy("server-c", ["shared_tool", "unique_c"]),
        ]
        conflicts = detect_tool_conflicts(healths)

        assert len(conflicts) == 1
        assert sorted(conflicts[0].servers) == ["server-a", "server-c"]


class TestEmptyInput:
    """Tests with empty or degenerate inputs."""

    def test_empty_list_returns_empty(self):
        """Should return no conflicts for empty server list."""
        assert detect_tool_conflicts([]) == []

    def test_healthy_server_with_no_tools(self):
        """Should skip healthy servers that have no tools."""
        healths = [
            _healthy("server-a", []),
            _healthy("server-b", []),
        ]
        assert detect_tool_conflicts(healths) == []


class TestToolConflictModel:
    """Tests for the ToolConflict dataclass itself."""

    def test_frozen(self):
        """ToolConflict should be immutable."""
        conflict = ToolConflict(tool_name="read", servers=["a", "b"])
        try:
            conflict.tool_name = "write"  # type: ignore[misc]
            raise AssertionError("Should have raised FrozenInstanceError")
        except AttributeError:
            pass

    def test_slots(self):
        """ToolConflict should use __slots__."""
        assert hasattr(ToolConflict, "__slots__")


# === Integration: check_health includes tool_conflicts ======================


class TestHealthReportIncludesConflicts:
    """Tests that check_health adds tool_conflicts to the result dict."""

    @patch("mcp_tap.tools.health.parse_servers")
    @patch("mcp_tap.tools.health.read_config", return_value={"mcpServers": {}})
    @patch("mcp_tap.tools.health.detect_clients")
    async def test_conflicts_in_health_report(
        self,
        mock_detect: MagicMock,
        _mock_read: MagicMock,
        mock_parse: MagicMock,
    ):
        """Should include tool_conflicts when two servers share a tool."""
        from mcp_tap.models import ConnectionTestResult
        from mcp_tap.tools.health import check_health

        mock_detect.return_value = [_fake_location()]
        mock_parse.return_value = [
            _installed_server("postgres"),
            _installed_server("sqlite"),
        ]

        connection_tester = AsyncMock()
        connection_tester.test_server_connection = AsyncMock(
            side_effect=[
                ConnectionTestResult(
                    success=True,
                    server_name="postgres",
                    tools_discovered=["read_query", "write_query"],
                ),
                ConnectionTestResult(
                    success=True,
                    server_name="sqlite",
                    tools_discovered=["read_query", "list_tables"],
                ),
            ]
        )

        ctx = _make_ctx(connection_tester=connection_tester)
        result = await check_health(ctx)

        assert "tool_conflicts" in result
        assert len(result["tool_conflicts"]) == 1
        assert result["tool_conflicts"][0]["tool_name"] == "read_query"
        assert sorted(result["tool_conflicts"][0]["servers"]) == [
            "postgres",
            "sqlite",
        ]

    @patch("mcp_tap.tools.health.parse_servers")
    @patch("mcp_tap.tools.health.read_config", return_value={"mcpServers": {}})
    @patch("mcp_tap.tools.health.detect_clients")
    async def test_no_conflicts_key_absent(
        self,
        mock_detect: MagicMock,
        _mock_read: MagicMock,
        mock_parse: MagicMock,
    ):
        """Should NOT include tool_conflicts key when there are no conflicts."""
        from mcp_tap.models import ConnectionTestResult
        from mcp_tap.tools.health import check_health

        mock_detect.return_value = [_fake_location()]
        mock_parse.return_value = [
            _installed_server("postgres"),
            _installed_server("github"),
        ]

        connection_tester = AsyncMock()
        connection_tester.test_server_connection = AsyncMock(
            side_effect=[
                ConnectionTestResult(
                    success=True,
                    server_name="postgres",
                    tools_discovered=["read_query"],
                ),
                ConnectionTestResult(
                    success=True,
                    server_name="github",
                    tools_discovered=["create_issue"],
                ),
            ]
        )

        ctx = _make_ctx(connection_tester=connection_tester)
        result = await check_health(ctx)

        assert "tool_conflicts" not in result
