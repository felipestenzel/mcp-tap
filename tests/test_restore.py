"""Tests for the restore tool (tools/restore.py)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from mcp_tap.errors import InstallerNotFoundError, LockfileReadError, McpTapError
from mcp_tap.models import (
    ConfigLocation,
    ConnectionTestResult,
    InstallResult,
    LockedConfig,
    LockedServer,
    Lockfile,
    MCPClient,
    ServerConfig,
)
from mcp_tap.server import AppContext
from mcp_tap.tools.restore import _LOCKFILE_NAME, _build_dry_run_result, _restore_server, restore

# --- Helpers ---------------------------------------------------------------


def _make_ctx(
    *,
    installer_resolver: AsyncMock | None = None,
    connection_tester: AsyncMock | None = None,
) -> MagicMock:
    """Build a mock Context with AppContext injected into lifespan_context."""
    app = MagicMock(spec=AppContext)
    app.installer_resolver = installer_resolver or AsyncMock()
    app.connection_tester = connection_tester or AsyncMock()

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


def _lockfile_with_servers(**servers: LockedServer) -> Lockfile:
    return Lockfile(
        lockfile_version=1,
        generated_by="mcp-tap@0.3.0",
        generated_at="2026-02-19T14:30:00Z",
        servers=servers,
    )


def _locked_server(
    package_identifier: str = "test-pkg",
    registry_type: str = "npm",
    version: str = "1.0.0",
    command: str = "npx",
    args: list[str] | None = None,
    env_keys: list[str] | None = None,
) -> LockedServer:
    return LockedServer(
        package_identifier=package_identifier,
        registry_type=registry_type,
        version=version,
        config=LockedConfig(
            command=command,
            args=args or ["-y", "test-pkg"],
            env_keys=env_keys or [],
        ),
        tools=["query"],
        tools_hash="sha256-abc",
        installed_at="2026-02-19T14:30:00Z",
    )


def _install_result(success: bool = True, message: str = "OK") -> InstallResult:
    return InstallResult(
        success=success,
        package_identifier="test-pkg",
        install_method="npm",
        message=message,
    )


def _connection_result(
    success: bool = True,
    server_name: str = "test-server",
    tools: list[str] | None = None,
) -> ConnectionTestResult:
    return ConnectionTestResult(
        success=success,
        server_name=server_name,
        tools_discovered=tools or ["query", "mutate"],
    )


def _mock_installer(
    install_result: InstallResult | None = None,
) -> MagicMock:
    installer = MagicMock()
    installer.install = AsyncMock(return_value=install_result or _install_result())
    installer.build_server_command = MagicMock(return_value=("npx", ["-y", "test-pkg"]))
    return installer


# Consistent patch targets (Tier A only — kept as direct imports)
_P_READ_LOCKFILE = "mcp_tap.tools.restore.read_lockfile"
_P_RESOLVE_LOCATIONS = "mcp_tap.tools.restore.resolve_config_locations"
_P_WRITE_CONFIG = "mcp_tap.tools.restore.write_server_config"


# === No lockfile found ======================================================


class TestNoLockfile:
    """Tests when lockfile is not found."""

    @patch(_P_READ_LOCKFILE, return_value=None)
    async def test_returns_error_when_no_lockfile(self, mock_read: MagicMock) -> None:
        """Should return success=False with error message."""
        ctx = _make_ctx()
        result = await restore("/my/project", ctx)

        assert result["success"] is False
        assert "No lockfile found" in result["error"]

    @patch(_P_READ_LOCKFILE, return_value=None)
    async def test_lockfile_path_in_error(self, mock_read: MagicMock) -> None:
        """Should include the expected lockfile path in the error message."""
        ctx = _make_ctx()
        result = await restore("/my/project", ctx)

        assert "/my/project/mcp-tap.lock" in result["error"]

    @patch(_P_READ_LOCKFILE, return_value=None)
    async def test_includes_hint(self, mock_read: MagicMock) -> None:
        """Should include a hint about how to create a lockfile."""
        ctx = _make_ctx()
        result = await restore("/my/project", ctx)

        assert "hint" in result
        assert "configure_server" in result["hint"]

    @patch(_P_READ_LOCKFILE, return_value=None)
    async def test_no_further_calls_after_no_lockfile(self, mock_read: MagicMock) -> None:
        """Should not attempt to resolve config locations."""
        ctx = _make_ctx()
        with patch(_P_RESOLVE_LOCATIONS) as mock_resolve:
            await restore("/my/project", ctx)
            mock_resolve.assert_not_called()


# === Empty lockfile =========================================================


class TestEmptyLockfile:
    """Tests when lockfile exists but has no servers."""

    @patch(_P_READ_LOCKFILE)
    async def test_returns_success_with_empty_restored(self, mock_read: MagicMock) -> None:
        """Should return success=True with empty restored list."""
        mock_read.return_value = _lockfile_with_servers()  # no servers
        ctx = _make_ctx()
        result = await restore("/my/project", ctx)

        assert result["success"] is True
        assert result["restored"] == []
        assert "no servers" in result["message"].lower()

    @patch(_P_READ_LOCKFILE)
    async def test_includes_lockfile_path(self, mock_read: MagicMock) -> None:
        """Should include lockfile path even when empty."""
        mock_read.return_value = _lockfile_with_servers()
        ctx = _make_ctx()
        result = await restore("/my/project", ctx)

        assert "/my/project/mcp-tap.lock" in result["lockfile_path"]

    @patch(_P_READ_LOCKFILE)
    async def test_does_not_resolve_locations(self, mock_read: MagicMock) -> None:
        """Should not attempt to resolve config locations for empty lockfile."""
        mock_read.return_value = _lockfile_with_servers()
        ctx = _make_ctx()
        with patch(_P_RESOLVE_LOCATIONS) as mock_resolve:
            await restore("/my/project", ctx)
            mock_resolve.assert_not_called()


# === No MCP client detected =================================================


class TestNoClientDetected:
    """Tests when no MCP client is found on the system."""

    @patch(_P_RESOLVE_LOCATIONS, return_value=[])
    @patch(_P_READ_LOCKFILE)
    async def test_returns_error_when_no_client(
        self, mock_read: MagicMock, mock_resolve: MagicMock
    ) -> None:
        """Should return success=False when no client is detected."""
        mock_read.return_value = _lockfile_with_servers(pg=_locked_server())
        ctx = _make_ctx()
        result = await restore("/my/project", ctx)

        assert result["success"] is False
        assert "No MCP client detected" in result["error"]

    @patch(_P_RESOLVE_LOCATIONS, return_value=[])
    @patch(_P_READ_LOCKFILE)
    async def test_does_not_attempt_install(
        self, mock_read: MagicMock, mock_resolve: MagicMock
    ) -> None:
        """Should not attempt any server installs."""
        mock_read.return_value = _lockfile_with_servers(pg=_locked_server())
        installer_resolver = AsyncMock()
        ctx = _make_ctx(installer_resolver=installer_resolver)

        await restore("/my/project", ctx)

        installer_resolver.resolve_installer.assert_not_called()


# === Dry run ================================================================


class TestDryRun:
    """Tests for dry_run=True mode."""

    @patch(_P_RESOLVE_LOCATIONS)
    @patch(_P_READ_LOCKFILE)
    async def test_dry_run_returns_servers_without_installing(
        self, mock_read: MagicMock, mock_resolve: MagicMock
    ) -> None:
        """Should list what would be installed without doing anything."""
        locked = _locked_server(package_identifier="@mcp/postgres", version="2.1.0")
        mock_read.return_value = _lockfile_with_servers(postgres=locked)
        mock_resolve.return_value = [_fake_location()]

        installer_resolver = AsyncMock()
        ctx = _make_ctx(installer_resolver=installer_resolver)

        result = await restore("/my/project", ctx, dry_run=True)

        installer_resolver.resolve_installer.assert_not_called()

        assert result["success"] is True
        assert result["dry_run"] is True
        assert result["total"] == 1
        assert result["servers"][0]["server"] == "postgres"
        assert result["servers"][0]["package"] == "@mcp/postgres"
        assert result["servers"][0]["version"] == "2.1.0"

    @patch(_P_RESOLVE_LOCATIONS)
    @patch(_P_READ_LOCKFILE)
    async def test_dry_run_shows_target_clients(
        self, mock_read: MagicMock, mock_resolve: MagicMock
    ) -> None:
        """Should include the target client names in the dry run output."""
        mock_read.return_value = _lockfile_with_servers(pg=_locked_server())
        mock_resolve.return_value = [
            _fake_location(MCPClient.CLAUDE_DESKTOP, "/path/a.json"),
            _fake_location(MCPClient.CURSOR, "/path/b.json"),
        ]
        ctx = _make_ctx()
        result = await restore("/my/project", ctx, dry_run=True)

        assert "claude_desktop" in result["target_clients"]
        assert "cursor" in result["target_clients"]

    @patch(_P_RESOLVE_LOCATIONS)
    @patch(_P_READ_LOCKFILE)
    async def test_dry_run_includes_env_keys(
        self, mock_read: MagicMock, mock_resolve: MagicMock
    ) -> None:
        """Should include env_keys per server in dry run output."""
        locked = _locked_server(env_keys=["DATABASE_URL", "API_KEY"])
        mock_read.return_value = _lockfile_with_servers(pg=locked)
        mock_resolve.return_value = [_fake_location()]
        ctx = _make_ctx()
        result = await restore("/my/project", ctx, dry_run=True)

        assert result["servers"][0]["env_keys"] == ["DATABASE_URL", "API_KEY"]

    @patch(_P_RESOLVE_LOCATIONS)
    @patch(_P_READ_LOCKFILE)
    async def test_dry_run_message(self, mock_read: MagicMock, mock_resolve: MagicMock) -> None:
        """Should include a message saying no changes were made."""
        mock_read.return_value = _lockfile_with_servers(pg=_locked_server())
        mock_resolve.return_value = [_fake_location()]
        ctx = _make_ctx()
        result = await restore("/my/project", ctx, dry_run=True)

        assert "No changes were made" in result["message"]

    @patch(_P_RESOLVE_LOCATIONS)
    @patch(_P_READ_LOCKFILE)
    async def test_dry_run_includes_lockfile_path(
        self, mock_read: MagicMock, mock_resolve: MagicMock
    ) -> None:
        """Should include the lockfile path in dry run result."""
        mock_read.return_value = _lockfile_with_servers(pg=_locked_server())
        mock_resolve.return_value = [_fake_location()]
        ctx = _make_ctx()
        result = await restore("/my/project", ctx, dry_run=True)

        assert "/my/project/mcp-tap.lock" in result["lockfile_path"]

    @patch(_P_RESOLVE_LOCATIONS)
    @patch(_P_READ_LOCKFILE)
    async def test_dry_run_multiple_servers(
        self, mock_read: MagicMock, mock_resolve: MagicMock
    ) -> None:
        """Should list all servers in dry run output."""
        mock_read.return_value = _lockfile_with_servers(
            pg=_locked_server(package_identifier="@mcp/postgres"),
            redis=_locked_server(package_identifier="mcp-redis", registry_type="pypi"),
        )
        mock_resolve.return_value = [_fake_location()]
        ctx = _make_ctx()
        result = await restore("/my/project", ctx, dry_run=True)

        assert result["total"] == 2
        server_names = {s["server"] for s in result["servers"]}
        assert server_names == {"pg", "redis"}


# === Successful restore =====================================================


class TestSuccessfulRestore:
    """Tests for successful server restoration."""

    @patch(_P_WRITE_CONFIG)
    @patch(_P_RESOLVE_LOCATIONS)
    @patch(_P_READ_LOCKFILE)
    async def test_single_server_success(
        self,
        mock_read: MagicMock,
        mock_resolve_loc: MagicMock,
        mock_write: MagicMock,
    ) -> None:
        """Should restore a single server end-to-end."""
        mock_read.return_value = _lockfile_with_servers(pg=_locked_server())
        mock_resolve_loc.return_value = [_fake_location()]

        installer_resolver = AsyncMock()
        installer_resolver.resolve_installer = AsyncMock(return_value=_mock_installer())

        connection_tester = AsyncMock()
        connection_tester.test_server_connection = AsyncMock(
            return_value=_connection_result(tools=["query", "mutate"])
        )

        ctx = _make_ctx(
            installer_resolver=installer_resolver,
            connection_tester=connection_tester,
        )
        result = await restore("/my/project", ctx)

        assert result["success"] is True
        assert result["total"] == 1
        assert result["restored"] == 1
        assert result["failed"] == 0
        assert result["servers"][0]["server"] == "pg"
        assert result["servers"][0]["success"] is True
        assert result["servers"][0]["validation_passed"] is True
        assert result["servers"][0]["tools_discovered"] == ["query", "mutate"]

    @patch(_P_WRITE_CONFIG)
    @patch(_P_RESOLVE_LOCATIONS)
    @patch(_P_READ_LOCKFILE)
    async def test_calls_installer_with_correct_args(
        self,
        mock_read: MagicMock,
        mock_resolve_loc: MagicMock,
        mock_write: MagicMock,
    ) -> None:
        """Should pass package_identifier and version to installer.install."""
        locked = _locked_server(package_identifier="@mcp/pg", version="3.2.1")
        mock_read.return_value = _lockfile_with_servers(pg=locked)
        mock_resolve_loc.return_value = [_fake_location()]
        installer = _mock_installer()

        installer_resolver = AsyncMock()
        installer_resolver.resolve_installer = AsyncMock(return_value=installer)

        connection_tester = AsyncMock()
        connection_tester.test_server_connection = AsyncMock(return_value=_connection_result())

        ctx = _make_ctx(
            installer_resolver=installer_resolver,
            connection_tester=connection_tester,
        )
        await restore("/my/project", ctx)

        installer.install.assert_awaited_once_with("@mcp/pg", "3.2.1")

    @patch(_P_WRITE_CONFIG)
    @patch(_P_RESOLVE_LOCATIONS)
    @patch(_P_READ_LOCKFILE)
    async def test_writes_config_to_each_location(
        self,
        mock_read: MagicMock,
        mock_resolve_loc: MagicMock,
        mock_write: MagicMock,
    ) -> None:
        """Should write server config to every resolved config location."""
        mock_read.return_value = _lockfile_with_servers(pg=_locked_server())
        locations = [
            _fake_location(MCPClient.CLAUDE_CODE, "/path/a.json"),
            _fake_location(MCPClient.CURSOR, "/path/b.json"),
        ]
        mock_resolve_loc.return_value = locations

        installer_resolver = AsyncMock()
        installer_resolver.resolve_installer = AsyncMock(return_value=_mock_installer())

        connection_tester = AsyncMock()
        connection_tester.test_server_connection = AsyncMock(return_value=_connection_result())

        ctx = _make_ctx(
            installer_resolver=installer_resolver,
            connection_tester=connection_tester,
        )
        await restore("/my/project", ctx)

        assert mock_write.call_count == 2
        written_paths = [str(call.args[0]) for call in mock_write.call_args_list]
        assert "/path/a.json" in written_paths
        assert "/path/b.json" in written_paths

    @patch(_P_WRITE_CONFIG)
    @patch(_P_RESOLVE_LOCATIONS)
    @patch(_P_READ_LOCKFILE)
    async def test_config_written_to_in_server_result(
        self,
        mock_read: MagicMock,
        mock_resolve_loc: MagicMock,
        mock_write: MagicMock,
    ) -> None:
        """Should report which config files were written in the per-server result."""
        mock_read.return_value = _lockfile_with_servers(pg=_locked_server())
        mock_resolve_loc.return_value = [
            _fake_location(MCPClient.CLAUDE_CODE, "/path/a.json"),
            _fake_location(MCPClient.CURSOR, "/path/b.json"),
        ]

        installer_resolver = AsyncMock()
        installer_resolver.resolve_installer = AsyncMock(return_value=_mock_installer())

        connection_tester = AsyncMock()
        connection_tester.test_server_connection = AsyncMock(return_value=_connection_result())

        ctx = _make_ctx(
            installer_resolver=installer_resolver,
            connection_tester=connection_tester,
        )
        result = await restore("/my/project", ctx)

        server_result = result["servers"][0]
        assert "/path/a.json" in server_result["config_written_to"]
        assert "/path/b.json" in server_result["config_written_to"]

    @patch(_P_WRITE_CONFIG)
    @patch(_P_RESOLVE_LOCATIONS)
    @patch(_P_READ_LOCKFILE)
    async def test_includes_clients_in_output(
        self,
        mock_read: MagicMock,
        mock_resolve_loc: MagicMock,
        mock_write: MagicMock,
    ) -> None:
        """Should list target client names in the result."""
        mock_read.return_value = _lockfile_with_servers(pg=_locked_server())
        mock_resolve_loc.return_value = [
            _fake_location(MCPClient.CLAUDE_CODE),
            _fake_location(MCPClient.CURSOR),
        ]

        installer_resolver = AsyncMock()
        installer_resolver.resolve_installer = AsyncMock(return_value=_mock_installer())

        connection_tester = AsyncMock()
        connection_tester.test_server_connection = AsyncMock(return_value=_connection_result())

        ctx = _make_ctx(
            installer_resolver=installer_resolver,
            connection_tester=connection_tester,
        )
        result = await restore("/my/project", ctx)

        assert "claude_code" in result["clients"]
        assert "cursor" in result["clients"]

    @patch(_P_WRITE_CONFIG)
    @patch(_P_RESOLVE_LOCATIONS)
    @patch(_P_READ_LOCKFILE)
    async def test_server_config_has_empty_env(
        self,
        mock_read: MagicMock,
        mock_resolve_loc: MagicMock,
        mock_write: MagicMock,
    ) -> None:
        """Should write server config with empty env dict (lockfile has no env values)."""
        mock_read.return_value = _lockfile_with_servers(pg=_locked_server())
        mock_resolve_loc.return_value = [_fake_location()]

        installer_resolver = AsyncMock()
        installer_resolver.resolve_installer = AsyncMock(return_value=_mock_installer())

        connection_tester = AsyncMock()
        connection_tester.test_server_connection = AsyncMock(return_value=_connection_result())

        ctx = _make_ctx(
            installer_resolver=installer_resolver,
            connection_tester=connection_tester,
        )
        await restore("/my/project", ctx)

        # Check the ServerConfig passed to write_server_config
        _, _, server_config, *_ = mock_write.call_args.args
        assert server_config.env == {}


# === Env keys reporting =====================================================


class TestEnvKeysReporting:
    """Tests for env_vars_needed output when servers have env_keys."""

    @patch(_P_WRITE_CONFIG)
    @patch(_P_RESOLVE_LOCATIONS)
    @patch(_P_READ_LOCKFILE)
    async def test_env_vars_needed_included_when_present(
        self, mock_read: MagicMock, mock_resolve: MagicMock, mock_write: MagicMock
    ) -> None:
        """Should include env_vars_needed when servers have env_keys."""
        locked = _locked_server(env_keys=["DATABASE_URL", "API_KEY"])
        mock_read.return_value = _lockfile_with_servers(pg=locked)
        mock_resolve.return_value = [_fake_location()]

        installer_resolver = AsyncMock()
        installer_resolver.resolve_installer = AsyncMock(return_value=_mock_installer())

        connection_tester = AsyncMock()
        connection_tester.test_server_connection = AsyncMock(return_value=_connection_result())

        ctx = _make_ctx(
            installer_resolver=installer_resolver,
            connection_tester=connection_tester,
        )
        result = await restore("/my/project", ctx)

        assert "env_vars_needed" in result
        assert result["env_vars_needed"][0]["server"] == "pg"
        assert result["env_vars_needed"][0]["env_keys"] == ["DATABASE_URL", "API_KEY"]

    @patch(_P_WRITE_CONFIG)
    @patch(_P_RESOLVE_LOCATIONS)
    @patch(_P_READ_LOCKFILE)
    async def test_env_hint_included_when_env_keys_present(
        self, mock_read: MagicMock, mock_resolve: MagicMock, mock_write: MagicMock
    ) -> None:
        """Should include a human-readable env_hint."""
        locked = _locked_server(env_keys=["SECRET"])
        mock_read.return_value = _lockfile_with_servers(pg=locked)
        mock_resolve.return_value = [_fake_location()]

        installer_resolver = AsyncMock()
        installer_resolver.resolve_installer = AsyncMock(return_value=_mock_installer())

        connection_tester = AsyncMock()
        connection_tester.test_server_connection = AsyncMock(return_value=_connection_result())

        ctx = _make_ctx(
            installer_resolver=installer_resolver,
            connection_tester=connection_tester,
        )
        result = await restore("/my/project", ctx)

        assert "env_hint" in result
        assert "environment variables" in result["env_hint"].lower()

    @patch(_P_WRITE_CONFIG)
    @patch(_P_RESOLVE_LOCATIONS)
    @patch(_P_READ_LOCKFILE)
    async def test_no_env_vars_needed_when_no_env_keys(
        self, mock_read: MagicMock, mock_resolve: MagicMock, mock_write: MagicMock
    ) -> None:
        """Should not include env_vars_needed when no servers have env_keys."""
        locked = _locked_server(env_keys=[])
        mock_read.return_value = _lockfile_with_servers(pg=locked)
        mock_resolve.return_value = [_fake_location()]

        installer_resolver = AsyncMock()
        installer_resolver.resolve_installer = AsyncMock(return_value=_mock_installer())

        connection_tester = AsyncMock()
        connection_tester.test_server_connection = AsyncMock(return_value=_connection_result())

        ctx = _make_ctx(
            installer_resolver=installer_resolver,
            connection_tester=connection_tester,
        )
        result = await restore("/my/project", ctx)

        assert "env_vars_needed" not in result
        assert "env_hint" not in result


# === Install failure ========================================================


class TestInstallFailure:
    """Tests when package installation fails."""

    @patch(_P_WRITE_CONFIG)
    @patch(_P_RESOLVE_LOCATIONS)
    @patch(_P_READ_LOCKFILE)
    async def test_install_failure_returns_success_false_for_server(
        self,
        mock_read: MagicMock,
        mock_resolve_loc: MagicMock,
        mock_write: MagicMock,
    ) -> None:
        """Should mark server as failed when install returns success=False."""
        mock_read.return_value = _lockfile_with_servers(pg=_locked_server())
        mock_resolve_loc.return_value = [_fake_location()]

        installer_resolver = AsyncMock()
        installer_resolver.resolve_installer = AsyncMock(
            return_value=_mock_installer(
                _install_result(success=False, message="npm install failed")
            )
        )

        connection_tester = AsyncMock()
        ctx = _make_ctx(
            installer_resolver=installer_resolver,
            connection_tester=connection_tester,
        )
        result = await restore("/my/project", ctx)

        assert result["servers"][0]["success"] is False
        assert "Install failed" in result["servers"][0]["error"]
        # Should not write config or test connection
        mock_write.assert_not_called()
        connection_tester.test_server_connection.assert_not_called()

    @patch(_P_WRITE_CONFIG)
    @patch(_P_RESOLVE_LOCATIONS)
    @patch(_P_READ_LOCKFILE)
    async def test_install_failure_overall_success_false_when_only_server(
        self,
        mock_read: MagicMock,
        mock_resolve_loc: MagicMock,
        mock_write: MagicMock,
    ) -> None:
        """Should report overall success=False when all servers fail."""
        mock_read.return_value = _lockfile_with_servers(pg=_locked_server())
        mock_resolve_loc.return_value = [_fake_location()]

        installer_resolver = AsyncMock()
        installer_resolver.resolve_installer = AsyncMock(
            return_value=_mock_installer(_install_result(success=False, message="failed"))
        )

        ctx = _make_ctx(installer_resolver=installer_resolver)
        result = await restore("/my/project", ctx)

        assert result["success"] is False
        assert result["restored"] == 0
        assert result["failed"] == 1


# === Multiple servers: mixed success/failure ================================


class TestMultipleServers:
    """Tests when restoring multiple servers with mixed outcomes."""

    @patch(_P_WRITE_CONFIG)
    @patch(_P_RESOLVE_LOCATIONS)
    @patch(_P_READ_LOCKFILE)
    async def test_one_succeeds_one_fails(
        self,
        mock_read: MagicMock,
        mock_resolve_loc: MagicMock,
        mock_write: MagicMock,
    ) -> None:
        """Should report partial success when one server fails."""
        mock_read.return_value = _lockfile_with_servers(
            pg=_locked_server(package_identifier="@mcp/postgres"),
            redis=_locked_server(package_identifier="mcp-redis"),
        )
        mock_resolve_loc.return_value = [_fake_location()]

        # First call succeeds, second fails
        good_installer = _mock_installer(_install_result(success=True))
        bad_installer = _mock_installer(_install_result(success=False, message="not found"))

        installer_resolver = AsyncMock()
        installer_resolver.resolve_installer = AsyncMock(
            side_effect=[good_installer, bad_installer]
        )

        connection_tester = AsyncMock()
        connection_tester.test_server_connection = AsyncMock(return_value=_connection_result())

        ctx = _make_ctx(
            installer_resolver=installer_resolver,
            connection_tester=connection_tester,
        )
        result = await restore("/my/project", ctx)

        assert result["success"] is True  # at least one succeeded
        assert result["total"] == 2
        assert result["restored"] == 1
        assert result["failed"] == 1

    @patch(_P_WRITE_CONFIG)
    @patch(_P_RESOLVE_LOCATIONS)
    @patch(_P_READ_LOCKFILE)
    async def test_all_fail_overall_false(
        self,
        mock_read: MagicMock,
        mock_resolve_loc: MagicMock,
        mock_write: MagicMock,
    ) -> None:
        """Should report overall success=False when all servers fail."""
        mock_read.return_value = _lockfile_with_servers(
            pg=_locked_server(),
            redis=_locked_server(),
        )
        mock_resolve_loc.return_value = [_fake_location()]

        installer_resolver = AsyncMock()
        installer_resolver.resolve_installer = AsyncMock(
            return_value=_mock_installer(_install_result(success=False, message="fail"))
        )

        ctx = _make_ctx(installer_resolver=installer_resolver)
        result = await restore("/my/project", ctx)

        assert result["success"] is False
        assert result["restored"] == 0
        assert result["failed"] == 2


# === Validation failure =====================================================


class TestValidationFailure:
    """Tests when connection validation fails after successful install."""

    @patch(_P_WRITE_CONFIG)
    @patch(_P_RESOLVE_LOCATIONS)
    @patch(_P_READ_LOCKFILE)
    async def test_validation_failed_still_success_true(
        self,
        mock_read: MagicMock,
        mock_resolve_loc: MagicMock,
        mock_write: MagicMock,
    ) -> None:
        """Should report server success=True but validation_passed=False."""
        mock_read.return_value = _lockfile_with_servers(pg=_locked_server())
        mock_resolve_loc.return_value = [_fake_location()]

        installer_resolver = AsyncMock()
        installer_resolver.resolve_installer = AsyncMock(return_value=_mock_installer())

        connection_tester = AsyncMock()
        connection_tester.test_server_connection = AsyncMock(
            return_value=_connection_result(success=False)
        )

        ctx = _make_ctx(
            installer_resolver=installer_resolver,
            connection_tester=connection_tester,
        )
        result = await restore("/my/project", ctx)

        server = result["servers"][0]
        assert server["success"] is True  # install succeeded
        assert server["validation_passed"] is False  # but connection failed

    @patch(_P_WRITE_CONFIG)
    @patch(_P_RESOLVE_LOCATIONS)
    @patch(_P_READ_LOCKFILE)
    async def test_validation_failed_config_still_written(
        self,
        mock_read: MagicMock,
        mock_resolve_loc: MagicMock,
        mock_write: MagicMock,
    ) -> None:
        """Should write config even if validation fails."""
        mock_read.return_value = _lockfile_with_servers(pg=_locked_server())
        mock_resolve_loc.return_value = [_fake_location()]

        installer_resolver = AsyncMock()
        installer_resolver.resolve_installer = AsyncMock(return_value=_mock_installer())

        connection_tester = AsyncMock()
        connection_tester.test_server_connection = AsyncMock(
            return_value=_connection_result(success=False)
        )

        ctx = _make_ctx(
            installer_resolver=installer_resolver,
            connection_tester=connection_tester,
        )
        await restore("/my/project", ctx)

        mock_write.assert_called_once()


# === InstallerNotFoundError =================================================


class TestInstallerNotFound:
    """Tests when the required package manager is not installed."""

    @patch(_P_RESOLVE_LOCATIONS)
    @patch(_P_READ_LOCKFILE)
    async def test_installer_not_found_handled_gracefully(
        self,
        mock_read: MagicMock,
        mock_resolve_loc: MagicMock,
    ) -> None:
        """Should catch InstallerNotFoundError and mark server as failed."""
        mock_read.return_value = _lockfile_with_servers(pg=_locked_server())
        mock_resolve_loc.return_value = [_fake_location()]

        installer_resolver = AsyncMock()
        installer_resolver.resolve_installer = AsyncMock(
            side_effect=InstallerNotFoundError(
                "npm is not installed. Install it from https://nodejs.org/"
            )
        )

        ctx = _make_ctx(installer_resolver=installer_resolver)
        result = await restore("/my/project", ctx)

        assert result["servers"][0]["success"] is False
        assert "npm is not installed" in result["servers"][0]["error"]
        # Overall should be False since the only server failed
        assert result["success"] is False


# === McpTapError in outer try ===============================================


class TestMcpTapErrorOuter:
    """Tests when McpTapError occurs in the outer try block."""

    @patch(_P_READ_LOCKFILE)
    async def test_lockfile_read_error_caught(self, mock_read: MagicMock) -> None:
        """Should catch LockfileReadError and return error dict."""
        mock_read.side_effect = LockfileReadError("Invalid JSON in lockfile.")
        ctx = _make_ctx()

        result = await restore("/my/project", ctx)

        assert result["success"] is False
        assert "Invalid JSON" in result["error"]

    @patch(_P_READ_LOCKFILE)
    async def test_mcp_tap_error_does_not_call_ctx_error(self, mock_read: MagicMock) -> None:
        """Should NOT call ctx.error for expected McpTapError."""
        mock_read.side_effect = McpTapError("expected error")
        ctx = _make_ctx()

        await restore("/my/project", ctx)

        ctx.error.assert_not_awaited()


# === Unexpected exception ===================================================


class TestUnexpectedException:
    """Tests for unexpected exceptions in the outer try block."""

    @patch(_P_READ_LOCKFILE)
    async def test_returns_internal_error(self, mock_read: MagicMock) -> None:
        """Should return generic internal error for unexpected exceptions."""
        mock_read.side_effect = RuntimeError("something broke")
        ctx = _make_ctx()

        result = await restore("/my/project", ctx)

        assert result["success"] is False
        assert "Internal error" in result["error"]
        assert "RuntimeError" in result["error"]

    @patch(_P_READ_LOCKFILE)
    async def test_logs_to_ctx_error(self, mock_read: MagicMock) -> None:
        """Should log unexpected errors via ctx.error."""
        mock_read.side_effect = ValueError("bad value")
        ctx = _make_ctx()

        await restore("/my/project", ctx)

        ctx.error.assert_awaited_once()
        error_msg = ctx.error.call_args[0][0]
        assert "bad value" in error_msg

    @patch(_P_RESOLVE_LOCATIONS)
    @patch(_P_READ_LOCKFILE)
    async def test_unexpected_error_during_resolve_locations(
        self, mock_read: MagicMock, mock_resolve: MagicMock
    ) -> None:
        """Should catch unexpected error from resolve_config_locations."""
        mock_read.return_value = _lockfile_with_servers(pg=_locked_server())
        mock_resolve.side_effect = TypeError("unexpected")
        ctx = _make_ctx()

        result = await restore("/my/project", ctx)

        assert result["success"] is False
        assert "Internal error" in result["error"]
        assert "TypeError" in result["error"]


# === _restore_server helper =================================================


class TestRestoreServerHelper:
    """Tests for the _restore_server helper function."""

    @patch(_P_WRITE_CONFIG)
    async def test_calls_ctx_info(self, mock_write: MagicMock) -> None:
        """Should log info message at the start of restore."""
        installer_resolver = AsyncMock()
        installer_resolver.resolve_installer = AsyncMock(return_value=_mock_installer())

        connection_tester = AsyncMock()
        connection_tester.test_server_connection = AsyncMock(return_value=_connection_result())

        ctx = _make_ctx()
        locations = [_fake_location()]

        await _restore_server(
            "pg",
            _locked_server(),
            locations,
            ctx,
            installer_resolver,
            connection_tester,
        )

        ctx.info.assert_awaited()
        info_msg = ctx.info.call_args[0][0]
        assert "pg" in info_msg

    @patch(_P_WRITE_CONFIG)
    async def test_writes_overwrite_existing_true(self, mock_write: MagicMock) -> None:
        """Should write config with overwrite_existing=True."""
        installer_resolver = AsyncMock()
        installer_resolver.resolve_installer = AsyncMock(return_value=_mock_installer())

        connection_tester = AsyncMock()
        connection_tester.test_server_connection = AsyncMock(return_value=_connection_result())

        ctx = _make_ctx()

        await _restore_server(
            "pg",
            _locked_server(),
            [_fake_location()],
            ctx,
            installer_resolver,
            connection_tester,
        )

        call_args = mock_write.call_args
        # write_server_config(Path, name, config, overwrite_existing=True)
        assert call_args.kwargs.get("overwrite_existing") is True or (
            len(call_args.args) > 3 and call_args.args[3] is True
        )

    async def test_unexpected_exception_caught_in_restore_server(self) -> None:
        """Should catch unexpected exceptions and return internal error."""
        installer_resolver = AsyncMock()
        installer_resolver.resolve_installer = AsyncMock(side_effect=RuntimeError("boom"))

        connection_tester = AsyncMock()
        ctx = _make_ctx()

        result = await _restore_server(
            "pg",
            _locked_server(),
            [_fake_location()],
            ctx,
            installer_resolver,
            connection_tester,
        )

        assert result["server"] == "pg"
        assert result["success"] is False
        assert "Internal error" in result["error"]

    async def test_mcp_tap_error_caught_in_restore_server(self) -> None:
        """Should catch McpTapError and return server-level error."""
        installer_resolver = AsyncMock()
        installer_resolver.resolve_installer = AsyncMock(
            side_effect=InstallerNotFoundError("no npm")
        )

        connection_tester = AsyncMock()
        ctx = _make_ctx()

        result = await _restore_server(
            "pg",
            _locked_server(),
            [_fake_location()],
            ctx,
            installer_resolver,
            connection_tester,
        )

        assert result["server"] == "pg"
        assert result["success"] is False
        assert "no npm" in result["error"]

    @patch(_P_WRITE_CONFIG)
    async def test_returns_package_and_version(self, mock_write: MagicMock) -> None:
        """Should include package identifier and version in success result."""
        locked = _locked_server(package_identifier="@mcp/fancy", version="5.0.0")

        installer_resolver = AsyncMock()
        installer_resolver.resolve_installer = AsyncMock(return_value=_mock_installer())

        connection_tester = AsyncMock()
        connection_tester.test_server_connection = AsyncMock(
            return_value=_connection_result(tools=["tool_a"])
        )

        ctx = _make_ctx()

        result = await _restore_server(
            "fancy",
            locked,
            [_fake_location()],
            ctx,
            installer_resolver,
            connection_tester,
        )

        assert result["package"] == "@mcp/fancy"
        assert result["version"] == "5.0.0"


# === _build_dry_run_result helper ===========================================


class TestBuildDryRunResult:
    """Tests for the _build_dry_run_result helper function."""

    def test_basic_structure(self) -> None:
        """Should return a well-structured dry run dict."""
        from pathlib import Path

        lockfile = _lockfile_with_servers(pg=_locked_server())
        locations = [_fake_location()]
        result = _build_dry_run_result(lockfile, locations, Path("/proj/mcp-tap.lock"))

        assert result["success"] is True
        assert result["dry_run"] is True
        assert result["total"] == 1
        assert result["message"] == "Dry run complete. No changes were made."

    def test_server_details(self) -> None:
        """Should include all server details in the output."""
        from pathlib import Path

        locked = _locked_server(
            package_identifier="@mcp/pg",
            registry_type="npm",
            version="2.0.0",
            command="npx",
            args=["-y", "@mcp/pg"],
            env_keys=["PG_URL"],
        )
        lockfile = _lockfile_with_servers(pg=locked)
        result = _build_dry_run_result(lockfile, [_fake_location()], Path("/proj/mcp-tap.lock"))

        server = result["servers"][0]
        assert server["server"] == "pg"
        assert server["package"] == "@mcp/pg"
        assert server["registry_type"] == "npm"
        assert server["version"] == "2.0.0"
        assert server["command"] == "npx"
        assert server["args"] == ["-y", "@mcp/pg"]
        assert server["env_keys"] == ["PG_URL"]

    def test_target_clients(self) -> None:
        """Should list target client values."""
        from pathlib import Path

        lockfile = _lockfile_with_servers(pg=_locked_server())
        locations = [
            _fake_location(MCPClient.CLAUDE_DESKTOP),
            _fake_location(MCPClient.WINDSURF),
        ]
        result = _build_dry_run_result(lockfile, locations, Path("/proj/mcp-tap.lock"))

        assert result["target_clients"] == ["claude_desktop", "windsurf"]

    def test_lockfile_path(self) -> None:
        """Should include the lockfile path as a string."""
        from pathlib import Path

        lockfile = _lockfile_with_servers()
        result = _build_dry_run_result(lockfile, [_fake_location()], Path("/proj/mcp-tap.lock"))

        assert result["lockfile_path"] == "/proj/mcp-tap.lock"


# === Data flow verification =================================================


class TestDataFlow:
    """Tests verifying correct data flow between internal calls."""

    @patch(_P_RESOLVE_LOCATIONS)
    @patch(_P_READ_LOCKFILE)
    async def test_resolve_locations_called_with_client_arg(
        self, mock_read: MagicMock, mock_resolve: MagicMock
    ) -> None:
        """Should pass the client argument to resolve_config_locations."""
        mock_read.return_value = _lockfile_with_servers(pg=_locked_server())
        mock_resolve.return_value = []  # triggers no-client error
        ctx = _make_ctx()

        await restore("/my/project", ctx, client="cursor")

        mock_resolve.assert_called_once_with("cursor", scope="user", project_path="/my/project")

    @patch(_P_RESOLVE_LOCATIONS)
    @patch(_P_READ_LOCKFILE)
    async def test_resolve_locations_called_with_empty_client(
        self, mock_read: MagicMock, mock_resolve: MagicMock
    ) -> None:
        """Should pass empty string when no client is specified."""
        mock_read.return_value = _lockfile_with_servers(pg=_locked_server())
        mock_resolve.return_value = []
        ctx = _make_ctx()

        await restore("/my/project", ctx)

        mock_resolve.assert_called_once_with("", scope="user", project_path="/my/project")

    @patch(_P_WRITE_CONFIG)
    @patch(_P_RESOLVE_LOCATIONS)
    @patch(_P_READ_LOCKFILE)
    async def test_resolve_installer_called_with_registry_type(
        self,
        mock_read: MagicMock,
        mock_resolve_loc: MagicMock,
        mock_write: MagicMock,
    ) -> None:
        """Should resolve installer using the locked registry_type."""
        from mcp_tap.models import RegistryType

        locked = _locked_server(registry_type="pypi")
        mock_read.return_value = _lockfile_with_servers(pg=locked)
        mock_resolve_loc.return_value = [_fake_location()]

        installer_resolver = AsyncMock()
        installer_resolver.resolve_installer = AsyncMock(return_value=_mock_installer())

        connection_tester = AsyncMock()
        connection_tester.test_server_connection = AsyncMock(return_value=_connection_result())

        ctx = _make_ctx(
            installer_resolver=installer_resolver,
            connection_tester=connection_tester,
        )
        await restore("/my/project", ctx)

        installer_resolver.resolve_installer.assert_awaited_once_with(RegistryType.PYPI)

    @patch(_P_WRITE_CONFIG)
    @patch(_P_RESOLVE_LOCATIONS)
    @patch(_P_READ_LOCKFILE)
    async def test_test_connection_called_with_correct_args(
        self,
        mock_read: MagicMock,
        mock_resolve_loc: MagicMock,
        mock_write: MagicMock,
    ) -> None:
        """Should test connection with server name, config, and timeout=15."""
        locked = _locked_server(command="uvx", args=["mcp-pg"])
        mock_read.return_value = _lockfile_with_servers(pg=locked)
        mock_resolve_loc.return_value = [_fake_location()]

        installer_resolver = AsyncMock()
        installer_resolver.resolve_installer = AsyncMock(return_value=_mock_installer())

        connection_tester = AsyncMock()
        connection_tester.test_server_connection = AsyncMock(return_value=_connection_result())

        ctx = _make_ctx(
            installer_resolver=installer_resolver,
            connection_tester=connection_tester,
        )
        await restore("/my/project", ctx)

        connection_tester.test_server_connection.assert_awaited_once()
        call_args = connection_tester.test_server_connection.call_args
        assert call_args.args[0] == "pg"  # server name
        # The ServerConfig should match the locked config
        server_config = call_args.args[1]
        assert isinstance(server_config, ServerConfig)
        assert server_config.command == "uvx"
        assert server_config.args == ["mcp-pg"]
        assert call_args.kwargs.get("timeout_seconds") == 15


# === Lockfile name constant =================================================


class TestLockfileName:
    """Tests for the lockfile name constant."""

    def test_lockfile_name_value(self) -> None:
        """Should use 'mcp-tap.lock' as the lockfile name."""
        assert _LOCKFILE_NAME == "mcp-tap.lock"
