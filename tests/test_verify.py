"""Tests for the verify tool (tools/verify.py)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from mcp_tap.errors import ConfigReadError, LockfileReadError
from mcp_tap.models import (
    ConfigLocation,
    DriftEntry,
    DriftSeverity,
    DriftType,
    InstalledServer,
    LockedConfig,
    LockedServer,
    Lockfile,
    MCPClient,
    ServerConfig,
)
from mcp_tap.tools.verify import _LOCKFILE_NAME, verify

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


def _installed(name: str, command: str = "npx") -> InstalledServer:
    return InstalledServer(
        name=name,
        config=ServerConfig(command=command, args=["-y", name]),
        source_file="/tmp/fake_config.json",
    )


def _lockfile_with_servers(**servers: LockedServer) -> Lockfile:
    return Lockfile(
        lockfile_version=1,
        generated_by="mcp-tap@0.3.0",
        generated_at="2026-02-19T14:30:00Z",
        servers=servers,
    )


def _locked_server(
    command: str = "npx",
    args: list[str] | None = None,
) -> LockedServer:
    return LockedServer(
        package_identifier="test-pkg",
        registry_type="npm",
        version="1.0.0",
        config=LockedConfig(command=command, args=args or ["-y", "test-pkg"]),
        tools=["query"],
        tools_hash="sha256-abc",
        installed_at="2026-02-19T14:30:00Z",
    )


# Consistent patch targets (all in the verify module namespace)
_PATCH_READ_LOCKFILE = "mcp_tap.tools.verify.read_lockfile"
_PATCH_DETECT_CLIENTS = "mcp_tap.tools.verify.detect_clients"
_PATCH_RESOLVE_CONFIG = "mcp_tap.tools.verify.resolve_config_path"
_PATCH_READ_CONFIG = "mcp_tap.tools.verify.read_config"
_PATCH_PARSE_SERVERS = "mcp_tap.tools.verify.parse_servers"
_PATCH_DIFF_LOCKFILE = "mcp_tap.tools.verify.diff_lockfile"


# === No lockfile found ======================================================


class TestNoLockfile:
    """Tests when lockfile is not found."""

    @patch(_PATCH_READ_LOCKFILE, return_value=None)
    async def test_returns_error_when_no_lockfile(
        self, mock_read: MagicMock
    ) -> None:
        """Should return success=False with error message."""
        ctx = _make_ctx()
        result = await verify("/my/project", ctx)

        assert result["success"] is False
        assert "No lockfile found" in result["error"]
        assert _LOCKFILE_NAME in result["error"]
        assert "hint" in result

    @patch(_PATCH_READ_LOCKFILE, return_value=None)
    async def test_lockfile_path_in_error(self, mock_read: MagicMock) -> None:
        """Should include the expected lockfile path in the error message."""
        ctx = _make_ctx()
        result = await verify("/my/project", ctx)

        assert "/my/project/mcp-tap.lock" in result["error"]

    @patch(_PATCH_READ_LOCKFILE, return_value=None)
    async def test_no_further_calls_after_no_lockfile(
        self, mock_read: MagicMock
    ) -> None:
        """Should not attempt to detect clients or read config."""
        ctx = _make_ctx()
        with (
            patch(_PATCH_DETECT_CLIENTS) as mock_detect,
            patch(_PATCH_READ_CONFIG) as mock_read_cfg,
        ):
            await verify("/my/project", ctx)
            mock_detect.assert_not_called()
            mock_read_cfg.assert_not_called()


# === No client detected =====================================================


class TestNoClientDetected:
    """Tests when no MCP client is detected."""

    @patch(_PATCH_DETECT_CLIENTS, return_value=[])
    @patch(_PATCH_READ_LOCKFILE)
    async def test_auto_detect_no_client(
        self, mock_read: MagicMock, mock_detect: MagicMock
    ) -> None:
        """Should return error when auto-detect finds no clients."""
        mock_read.return_value = _lockfile_with_servers(pg=_locked_server())
        ctx = _make_ctx()
        result = await verify("/my/project", ctx)

        assert result["success"] is False
        assert "No MCP client detected" in result["error"]

    @patch(_PATCH_DETECT_CLIENTS, return_value=[])
    @patch(_PATCH_READ_LOCKFILE)
    async def test_no_client_skips_config_reading(
        self, mock_read: MagicMock, mock_detect: MagicMock
    ) -> None:
        """Should not read config when no client is detected."""
        mock_read.return_value = _lockfile_with_servers(pg=_locked_server())
        ctx = _make_ctx()
        with patch(_PATCH_READ_CONFIG) as mock_read_cfg:
            await verify("/my/project", ctx)
            mock_read_cfg.assert_not_called()


# === Explicit client specified ==============================================


class TestExplicitClient:
    """Tests when a client name is explicitly provided."""

    @patch(_PATCH_DIFF_LOCKFILE, return_value=[])
    @patch(_PATCH_PARSE_SERVERS, return_value=[])
    @patch(_PATCH_READ_CONFIG, return_value={"mcpServers": {}})
    @patch(_PATCH_RESOLVE_CONFIG)
    @patch(_PATCH_READ_LOCKFILE)
    async def test_uses_resolve_config_path_when_client_given(
        self,
        mock_read: MagicMock,
        mock_resolve: MagicMock,
        mock_read_cfg: MagicMock,
        mock_parse: MagicMock,
        mock_diff: MagicMock,
    ) -> None:
        """Should call resolve_config_path instead of detect_clients."""
        mock_read.return_value = _lockfile_with_servers()
        mock_resolve.return_value = _fake_location(MCPClient.CURSOR, "/home/.cursor/mcp.json")

        ctx = _make_ctx()
        result = await verify("/my/project", ctx, client="cursor")

        mock_resolve.assert_called_once()
        assert result["client"] == "cursor"
        assert result["config_file"] == "/home/.cursor/mcp.json"

    @patch(_PATCH_DIFF_LOCKFILE, return_value=[])
    @patch(_PATCH_PARSE_SERVERS, return_value=[])
    @patch(_PATCH_READ_CONFIG, return_value={"mcpServers": {}})
    @patch(_PATCH_RESOLVE_CONFIG)
    @patch(_PATCH_READ_LOCKFILE)
    async def test_does_not_call_detect_clients_when_client_given(
        self,
        mock_read: MagicMock,
        mock_resolve: MagicMock,
        mock_read_cfg: MagicMock,
        mock_parse: MagicMock,
        mock_diff: MagicMock,
    ) -> None:
        """Should skip auto-detection when client is explicitly provided."""
        mock_read.return_value = _lockfile_with_servers()
        mock_resolve.return_value = _fake_location()

        ctx = _make_ctx()
        with patch(_PATCH_DETECT_CLIENTS) as mock_detect:
            await verify("/my/project", ctx, client="claude_code")
            mock_detect.assert_not_called()


# === Clean state (no drift) =================================================


class TestCleanState:
    """Tests when lockfile matches installed state perfectly."""

    @patch(_PATCH_DIFF_LOCKFILE, return_value=[])
    @patch(_PATCH_PARSE_SERVERS)
    @patch(_PATCH_READ_CONFIG, return_value={"mcpServers": {}})
    @patch(_PATCH_DETECT_CLIENTS)
    @patch(_PATCH_READ_LOCKFILE)
    async def test_clean_result_structure(
        self,
        mock_read: MagicMock,
        mock_detect: MagicMock,
        mock_read_cfg: MagicMock,
        mock_parse: MagicMock,
        mock_diff: MagicMock,
    ) -> None:
        """Should return VerifyResult with clean=True and empty drift."""
        mock_read.return_value = _lockfile_with_servers(pg=_locked_server())
        mock_detect.return_value = [_fake_location()]
        mock_parse.return_value = [_installed("pg")]

        ctx = _make_ctx()
        result = await verify("/my/project", ctx)

        assert result["clean"] is True
        assert result["drift"] == []
        assert result["total_locked"] == 1
        assert result["total_installed"] == 1
        assert "lockfile_path" in result
        assert "client" in result
        assert "config_file" in result

    @patch(_PATCH_DIFF_LOCKFILE, return_value=[])
    @patch(_PATCH_PARSE_SERVERS, return_value=[])
    @patch(_PATCH_READ_CONFIG, return_value={"mcpServers": {}})
    @patch(_PATCH_DETECT_CLIENTS)
    @patch(_PATCH_READ_LOCKFILE)
    async def test_empty_lockfile_empty_installed_is_clean(
        self,
        mock_read: MagicMock,
        mock_detect: MagicMock,
        mock_read_cfg: MagicMock,
        mock_parse: MagicMock,
        mock_diff: MagicMock,
    ) -> None:
        """Should be clean when lockfile has no servers and none installed."""
        mock_read.return_value = _lockfile_with_servers()
        mock_detect.return_value = [_fake_location()]

        ctx = _make_ctx()
        result = await verify("/my/project", ctx)

        assert result["clean"] is True
        assert result["total_locked"] == 0
        assert result["total_installed"] == 0

    @patch(_PATCH_DIFF_LOCKFILE, return_value=[])
    @patch(_PATCH_PARSE_SERVERS)
    @patch(_PATCH_READ_CONFIG, return_value={"mcpServers": {}})
    @patch(_PATCH_DETECT_CLIENTS)
    @patch(_PATCH_READ_LOCKFILE)
    async def test_lockfile_path_includes_project_path(
        self,
        mock_read: MagicMock,
        mock_detect: MagicMock,
        mock_read_cfg: MagicMock,
        mock_parse: MagicMock,
        mock_diff: MagicMock,
    ) -> None:
        """Should include the full lockfile path in the result."""
        mock_read.return_value = _lockfile_with_servers()
        mock_detect.return_value = [_fake_location()]
        mock_parse.return_value = []

        ctx = _make_ctx()
        result = await verify("/my/project", ctx)

        assert "/my/project/mcp-tap.lock" in result["lockfile_path"]

    @patch(_PATCH_DIFF_LOCKFILE, return_value=[])
    @patch(_PATCH_PARSE_SERVERS)
    @patch(_PATCH_READ_CONFIG, return_value={"mcpServers": {}})
    @patch(_PATCH_DETECT_CLIENTS)
    @patch(_PATCH_READ_LOCKFILE)
    async def test_client_info_in_result(
        self,
        mock_read: MagicMock,
        mock_detect: MagicMock,
        mock_read_cfg: MagicMock,
        mock_parse: MagicMock,
        mock_diff: MagicMock,
    ) -> None:
        """Should include client name and config file path in result."""
        mock_read.return_value = _lockfile_with_servers()
        mock_detect.return_value = [
            _fake_location(MCPClient.CLAUDE_DESKTOP, "/path/to/claude_config.json")
        ]
        mock_parse.return_value = []

        ctx = _make_ctx()
        result = await verify("/my/project", ctx)

        assert result["client"] == "claude_desktop"
        assert result["config_file"] == "/path/to/claude_config.json"


# === With drift =============================================================


class TestWithDrift:
    """Tests when drift is detected between lockfile and installed state."""

    @patch(_PATCH_DIFF_LOCKFILE)
    @patch(_PATCH_PARSE_SERVERS)
    @patch(_PATCH_READ_CONFIG, return_value={"mcpServers": {}})
    @patch(_PATCH_DETECT_CLIENTS)
    @patch(_PATCH_READ_LOCKFILE)
    async def test_drift_detected_clean_false(
        self,
        mock_read: MagicMock,
        mock_detect: MagicMock,
        mock_read_cfg: MagicMock,
        mock_parse: MagicMock,
        mock_diff: MagicMock,
    ) -> None:
        """Should return clean=False when drift entries exist."""
        mock_read.return_value = _lockfile_with_servers(pg=_locked_server())
        mock_detect.return_value = [_fake_location()]
        mock_parse.return_value = []
        mock_diff.return_value = [
            DriftEntry(
                server="pg",
                drift_type=DriftType.MISSING,
                detail="Server 'pg' is in lockfile but not installed.",
                severity=DriftSeverity.WARNING,
            )
        ]

        ctx = _make_ctx()
        result = await verify("/my/project", ctx)

        assert result["clean"] is False
        assert len(result["drift"]) == 1
        assert result["drift"][0]["drift_type"] == "missing"
        assert result["drift"][0]["server"] == "pg"

    @patch(_PATCH_DIFF_LOCKFILE)
    @patch(_PATCH_PARSE_SERVERS)
    @patch(_PATCH_READ_CONFIG, return_value={"mcpServers": {}})
    @patch(_PATCH_DETECT_CLIENTS)
    @patch(_PATCH_READ_LOCKFILE)
    async def test_multiple_drift_entries(
        self,
        mock_read: MagicMock,
        mock_detect: MagicMock,
        mock_read_cfg: MagicMock,
        mock_parse: MagicMock,
        mock_diff: MagicMock,
    ) -> None:
        """Should include all drift entries in the result."""
        mock_read.return_value = _lockfile_with_servers(pg=_locked_server())
        mock_detect.return_value = [_fake_location()]
        mock_parse.return_value = [_installed("pg")]
        mock_diff.return_value = [
            DriftEntry(server="pg", drift_type=DriftType.CONFIG_CHANGED),
            DriftEntry(server="pg", drift_type=DriftType.TOOLS_CHANGED),
            DriftEntry(server="extra", drift_type=DriftType.EXTRA),
        ]

        ctx = _make_ctx()
        result = await verify("/my/project", ctx)

        assert result["clean"] is False
        assert len(result["drift"]) == 3
        drift_types = {d["drift_type"] for d in result["drift"]}
        assert drift_types == {"config_changed", "tools_changed", "extra"}

    @patch(_PATCH_DIFF_LOCKFILE)
    @patch(_PATCH_PARSE_SERVERS)
    @patch(_PATCH_READ_CONFIG, return_value={"mcpServers": {}})
    @patch(_PATCH_DETECT_CLIENTS)
    @patch(_PATCH_READ_LOCKFILE)
    async def test_drift_entries_serialized_correctly(
        self,
        mock_read: MagicMock,
        mock_detect: MagicMock,
        mock_read_cfg: MagicMock,
        mock_parse: MagicMock,
        mock_diff: MagicMock,
    ) -> None:
        """Should serialize DriftEntry dataclass fields into plain dicts."""
        mock_read.return_value = _lockfile_with_servers(pg=_locked_server())
        mock_detect.return_value = [_fake_location()]
        mock_parse.return_value = []
        mock_diff.return_value = [
            DriftEntry(
                server="pg",
                drift_type=DriftType.MISSING,
                detail="test detail",
                severity=DriftSeverity.ERROR,
            )
        ]

        ctx = _make_ctx()
        result = await verify("/my/project", ctx)

        drift_entry = result["drift"][0]
        assert drift_entry["server"] == "pg"
        assert drift_entry["drift_type"] == "missing"
        assert drift_entry["detail"] == "test detail"
        assert drift_entry["severity"] == "error"


# === Data flow verification =================================================


class TestDataFlow:
    """Tests verifying correct data flow between internal calls."""

    @patch(_PATCH_DIFF_LOCKFILE, return_value=[])
    @patch(_PATCH_PARSE_SERVERS)
    @patch(_PATCH_READ_CONFIG)
    @patch(_PATCH_DETECT_CLIENTS)
    @patch(_PATCH_READ_LOCKFILE)
    async def test_read_config_receives_correct_path(
        self,
        mock_read: MagicMock,
        mock_detect: MagicMock,
        mock_read_cfg: MagicMock,
        mock_parse: MagicMock,
        mock_diff: MagicMock,
    ) -> None:
        """Should pass the config location path to read_config."""
        mock_read.return_value = _lockfile_with_servers()
        mock_detect.return_value = [_fake_location(path="/home/.claude.json")]
        mock_read_cfg.return_value = {"mcpServers": {}}
        mock_parse.return_value = []

        ctx = _make_ctx()
        await verify("/my/project", ctx)

        # read_config should receive a Path object of the config location
        call_args = mock_read_cfg.call_args
        from pathlib import Path

        assert call_args[0][0] == Path("/home/.claude.json")

    @patch(_PATCH_DIFF_LOCKFILE, return_value=[])
    @patch(_PATCH_PARSE_SERVERS)
    @patch(_PATCH_READ_CONFIG)
    @patch(_PATCH_DETECT_CLIENTS)
    @patch(_PATCH_READ_LOCKFILE)
    async def test_parse_servers_receives_raw_config(
        self,
        mock_read: MagicMock,
        mock_detect: MagicMock,
        mock_read_cfg: MagicMock,
        mock_parse: MagicMock,
        mock_diff: MagicMock,
    ) -> None:
        """Should pass read_config output to parse_servers."""
        mock_read.return_value = _lockfile_with_servers()
        mock_detect.return_value = [_fake_location()]
        raw_config = {"mcpServers": {"pg": {"command": "npx"}}}
        mock_read_cfg.return_value = raw_config
        mock_parse.return_value = []

        ctx = _make_ctx()
        await verify("/my/project", ctx)

        mock_parse.assert_called_once_with(raw_config, source_file="/tmp/fake_config.json")

    @patch(_PATCH_DIFF_LOCKFILE, return_value=[])
    @patch(_PATCH_PARSE_SERVERS)
    @patch(_PATCH_READ_CONFIG, return_value={"mcpServers": {}})
    @patch(_PATCH_DETECT_CLIENTS)
    @patch(_PATCH_READ_LOCKFILE)
    async def test_diff_lockfile_receives_lockfile_and_installed(
        self,
        mock_read: MagicMock,
        mock_detect: MagicMock,
        mock_read_cfg: MagicMock,
        mock_parse: MagicMock,
        mock_diff: MagicMock,
    ) -> None:
        """Should pass lockfile and installed servers to diff_lockfile."""
        lockfile = _lockfile_with_servers(pg=_locked_server())
        installed_list = [_installed("pg")]
        mock_read.return_value = lockfile
        mock_detect.return_value = [_fake_location()]
        mock_parse.return_value = installed_list

        ctx = _make_ctx()
        await verify("/my/project", ctx)

        mock_diff.assert_called_once_with(lockfile, installed_list)

    @patch(_PATCH_DIFF_LOCKFILE, return_value=[])
    @patch(_PATCH_PARSE_SERVERS, return_value=[])
    @patch(_PATCH_READ_CONFIG, return_value={"mcpServers": {}})
    @patch(_PATCH_DETECT_CLIENTS)
    @patch(_PATCH_READ_LOCKFILE)
    async def test_uses_first_detected_client(
        self,
        mock_read: MagicMock,
        mock_detect: MagicMock,
        mock_read_cfg: MagicMock,
        mock_parse: MagicMock,
        mock_diff: MagicMock,
    ) -> None:
        """Should use the first detected client when none is specified."""
        mock_read.return_value = _lockfile_with_servers()
        mock_detect.return_value = [
            _fake_location(MCPClient.CURSOR, "/home/.cursor/mcp.json"),
            _fake_location(MCPClient.CLAUDE_CODE, "/home/.claude.json"),
        ]

        ctx = _make_ctx()
        result = await verify("/my/project", ctx)

        assert result["client"] == "cursor"
        assert result["config_file"] == "/home/.cursor/mcp.json"


# === Error handling ==========================================================


class TestErrorHandling:
    """Tests for error handling paths."""

    @patch(_PATCH_READ_LOCKFILE)
    async def test_mcp_tap_error_returns_error_dict(
        self, mock_read: MagicMock
    ) -> None:
        """Should catch McpTapError and return success=False."""
        mock_read.side_effect = LockfileReadError("Invalid JSON in lockfile.")
        ctx = _make_ctx()
        result = await verify("/my/project", ctx)

        assert result["success"] is False
        assert "Invalid JSON" in result["error"]

    @patch(_PATCH_READ_LOCKFILE)
    async def test_config_read_error_returns_error_dict(
        self, mock_read: MagicMock
    ) -> None:
        """Should catch ConfigReadError (subclass of McpTapError)."""
        mock_read.side_effect = ConfigReadError("Permission denied reading config.")
        ctx = _make_ctx()
        result = await verify("/my/project", ctx)

        assert result["success"] is False
        assert "Permission denied" in result["error"]

    @patch(_PATCH_READ_LOCKFILE)
    async def test_unexpected_error_returns_internal_error(
        self, mock_read: MagicMock
    ) -> None:
        """Should catch unexpected exceptions and return generic error."""
        mock_read.side_effect = RuntimeError("something unexpected")
        ctx = _make_ctx()
        result = await verify("/my/project", ctx)

        assert result["success"] is False
        assert "Internal error" in result["error"]
        assert "RuntimeError" in result["error"]

    @patch(_PATCH_READ_LOCKFILE)
    async def test_unexpected_error_logs_to_ctx(
        self, mock_read: MagicMock
    ) -> None:
        """Should log unexpected errors via ctx.error."""
        mock_read.side_effect = ValueError("bad value")
        ctx = _make_ctx()
        await verify("/my/project", ctx)

        ctx.error.assert_awaited_once()
        error_msg = ctx.error.call_args[0][0]
        assert "bad value" in error_msg

    @patch(_PATCH_READ_LOCKFILE)
    async def test_mcp_tap_error_does_not_log_to_ctx(
        self, mock_read: MagicMock
    ) -> None:
        """Should NOT call ctx.error for expected McpTapError."""
        mock_read.side_effect = LockfileReadError("expected error")
        ctx = _make_ctx()
        await verify("/my/project", ctx)

        ctx.error.assert_not_awaited()

    @patch(_PATCH_DIFF_LOCKFILE)
    @patch(_PATCH_PARSE_SERVERS, return_value=[])
    @patch(_PATCH_READ_CONFIG, return_value={"mcpServers": {}})
    @patch(_PATCH_DETECT_CLIENTS)
    @patch(_PATCH_READ_LOCKFILE)
    async def test_error_during_diff_caught_as_unexpected(
        self,
        mock_read: MagicMock,
        mock_detect: MagicMock,
        mock_read_cfg: MagicMock,
        mock_parse: MagicMock,
        mock_diff: MagicMock,
    ) -> None:
        """Should catch unexpected errors from diff_lockfile."""
        mock_read.return_value = _lockfile_with_servers()
        mock_detect.return_value = [_fake_location()]
        mock_diff.side_effect = TypeError("unexpected comparison error")

        ctx = _make_ctx()
        result = await verify("/my/project", ctx)

        assert result["success"] is False
        assert "Internal error" in result["error"]
        assert "TypeError" in result["error"]


# === Lockfile name constant ==================================================


class TestLockfileName:
    """Tests for the lockfile name constant."""

    def test_lockfile_name_value(self) -> None:
        """Should use 'mcp-tap.lock' as the lockfile name."""
        assert _LOCKFILE_NAME == "mcp-tap.lock"
