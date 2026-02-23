"""Tests for the configure_server MCP tool (tools/configure.py)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from mcp_tap.errors import ConfigWriteError, InstallerNotFoundError
from mcp_tap.models import (
    ConfigLocation,
    ConnectionTestResult,
    InstallResult,
    MCPClient,
    ServerConfig,
)
from mcp_tap.server import AppContext
from mcp_tap.tools.configure import _is_http_transport, _parse_env_vars, configure_server

# ─── Helpers ─────────────────────────────────────────────────


def _default_healing_mock() -> AsyncMock:
    """Build a healing mock that returns a failed HealingResult by default.

    Without this, AsyncMock() returns truthy mock objects for `.fixed`,
    causing the code to think healing succeeded.
    """
    from mcp_tap.models import HealingResult

    healing = AsyncMock()
    healing.heal_and_retry = AsyncMock(return_value=HealingResult(fixed=False, attempts=[]))
    return healing


def _make_ctx(
    *,
    connection_tester: AsyncMock | None = None,
    healing: AsyncMock | None = None,
    installer_resolver: AsyncMock | None = None,
    security_gate: AsyncMock | None = None,
    http_reachability: AsyncMock | None = None,
) -> MagicMock:
    """Build a mock Context with AppContext injected into lifespan_context."""
    app = MagicMock(spec=AppContext)
    app.connection_tester = connection_tester or AsyncMock()
    app.healing = healing or _default_healing_mock()
    app.installer_resolver = installer_resolver or AsyncMock()
    app.security_gate = security_gate or AsyncMock()
    app.http_reachability = http_reachability or AsyncMock()

    ctx = MagicMock()
    ctx.request_context.lifespan_context = app
    ctx.info = AsyncMock()
    ctx.error = AsyncMock()
    return ctx


def _fake_location(
    client: MCPClient = MCPClient.CLAUDE_CODE,
    path: str = "/tmp/fake_config.json",
    scope: str = "user",
    exists: bool = True,
) -> ConfigLocation:
    return ConfigLocation(client=client, path=path, scope=scope, exists=exists)


def _ok_install_result(identifier: str = "test-pkg") -> InstallResult:
    return InstallResult(
        success=True,
        package_identifier=identifier,
        install_method="npx",
        message=f"Package {identifier} verified and cached by npx.",
    )


def _failed_install_result(identifier: str = "test-pkg") -> InstallResult:
    return InstallResult(
        success=False,
        package_identifier=identifier,
        install_method="npx",
        message=f"Failed to verify {identifier}: package not found",
        command_output="npm ERR! 404 Not Found",
    )


def _ok_connection_result(
    server_name: str = "test-server",
    tools: list[str] | None = None,
) -> ConnectionTestResult:
    return ConnectionTestResult(
        success=True,
        server_name=server_name,
        tools_discovered=tools or ["read_query", "write_query", "create_table"],
    )


def _failed_connection_result(
    server_name: str = "test-server",
    error: str = "Server did not respond within 15s.",
) -> ConnectionTestResult:
    return ConnectionTestResult(
        success=False,
        server_name=server_name,
        error=error,
    )


def _mock_installer(
    install_result: InstallResult | None = None,
    command: str = "npx",
    args: list[str] | None = None,
) -> MagicMock:
    """Build a mock installer with configurable install result and command."""
    installer = MagicMock()
    installer.install = AsyncMock(return_value=install_result or _ok_install_result())
    installer.build_server_command = MagicMock(
        return_value=(command, args if args is not None else ["-y", "test-pkg"]),
    )
    installer.is_available = AsyncMock(return_value=True)
    return installer


# ═══════════════════════════════════════════════════════════════
# Happy Path Tests
# ═══════════════════════════════════════════════════════════════


class TestConfigureHappyPath:
    """Tests for the full success flow: install -> write -> validate."""

    @patch("mcp_tap.tools.configure.write_server_config")
    @patch("mcp_tap.tools.configure.resolve_config_locations")
    async def test_full_success_flow(
        self,
        mock_locations: MagicMock,
        mock_write: MagicMock,
    ):
        """Should install, write config, validate, and return success."""
        mock_locations.return_value = [_fake_location()]
        installer = _mock_installer()

        installer_resolver = AsyncMock()
        installer_resolver.resolve_installer = AsyncMock(return_value=installer)

        connection_tester = AsyncMock()
        connection_tester.test_server_connection = AsyncMock(
            return_value=_ok_connection_result("pg-server")
        )

        ctx = _make_ctx(
            installer_resolver=installer_resolver,
            connection_tester=connection_tester,
        )
        result = await configure_server(
            server_name="pg-server",
            package_identifier="@modelcontextprotocol/server-postgres",
            ctx=ctx,
            clients="claude_code",
            registry_type="npm",
            env_vars="POSTGRES_URL=postgresql://localhost/db",
        )

        assert result["success"] is True
        assert result["server_name"] == "pg-server"
        assert result["config_file"] == "/tmp/fake_config.json"
        assert result["install_status"] == "installed"
        assert result["validation_passed"] is True
        assert len(result["tools_discovered"]) == 3

    @patch("mcp_tap.tools.configure.write_server_config")
    @patch("mcp_tap.tools.configure.resolve_config_locations")
    async def test_config_written_contains_command_and_args(
        self,
        mock_locations: MagicMock,
        mock_write: MagicMock,
    ):
        """Should include config_written dict with command, args, env."""
        mock_locations.return_value = [_fake_location()]

        installer_resolver = AsyncMock()
        installer_resolver.resolve_installer = AsyncMock(return_value=_mock_installer())

        connection_tester = AsyncMock()
        connection_tester.test_server_connection = AsyncMock(return_value=_ok_connection_result())

        ctx = _make_ctx(
            installer_resolver=installer_resolver,
            connection_tester=connection_tester,
        )
        result = await configure_server(
            server_name="test-server",
            package_identifier="test-pkg",
            ctx=ctx,
            clients="claude_code",
            env_vars="KEY=value",
        )

        assert "config_written" in result
        assert result["config_written"]["command"] == "npx"
        assert result["config_written"]["args"] == ["-y", "test-pkg"]
        assert result["config_written"]["env"] == {"KEY": "value"}

    @patch("mcp_tap.tools.configure.write_server_config")
    @patch("mcp_tap.tools.configure.resolve_config_locations")
    async def test_write_server_config_called_correctly(
        self,
        mock_locations: MagicMock,
        mock_write: MagicMock,
    ):
        """Should call write_server_config with correct path and config."""
        loc = _fake_location(path="/home/user/.claude.json")
        mock_locations.return_value = [loc]

        installer_resolver = AsyncMock()
        installer_resolver.resolve_installer = AsyncMock(return_value=_mock_installer())

        connection_tester = AsyncMock()
        connection_tester.test_server_connection = AsyncMock(return_value=_ok_connection_result())

        ctx = _make_ctx(
            installer_resolver=installer_resolver,
            connection_tester=connection_tester,
        )
        await configure_server(
            server_name="my-server",
            package_identifier="pkg",
            ctx=ctx,
            clients="claude_code",
        )

        mock_write.assert_called_once()
        call_args = mock_write.call_args
        assert call_args[0][0] == Path("/home/user/.claude.json")
        assert call_args[0][1] == "my-server"
        assert isinstance(call_args[0][2], ServerConfig)

    @patch("mcp_tap.tools.configure.write_server_config")
    @patch("mcp_tap.tools.configure.resolve_config_locations")
    async def test_message_mentions_restart(
        self,
        mock_locations: MagicMock,
        mock_write: MagicMock,
    ):
        """Should tell user to restart their MCP client."""
        mock_locations.return_value = [_fake_location()]

        installer_resolver = AsyncMock()
        installer_resolver.resolve_installer = AsyncMock(return_value=_mock_installer())

        connection_tester = AsyncMock()
        connection_tester.test_server_connection = AsyncMock(return_value=_ok_connection_result())

        ctx = _make_ctx(
            installer_resolver=installer_resolver,
            connection_tester=connection_tester,
        )
        result = await configure_server(
            server_name="s",
            package_identifier="p",
            ctx=ctx,
            clients="claude_code",
        )

        assert "Restart" in result["message"]


# ═══════════════════════════════════════════════════════════════
# Install Failure Tests
# ═══════════════════════════════════════════════════════════════


class TestConfigureInstallFails:
    """Tests for when package installation fails."""

    @patch("mcp_tap.tools.configure.write_server_config")
    @patch("mcp_tap.tools.configure.resolve_config_locations")
    async def test_install_failure_returns_error(
        self,
        mock_locations: MagicMock,
        mock_write: MagicMock,
    ):
        """Should return success=False when install fails."""
        mock_locations.return_value = [_fake_location()]
        installer = _mock_installer(install_result=_failed_install_result("bad-pkg"))

        installer_resolver = AsyncMock()
        installer_resolver.resolve_installer = AsyncMock(return_value=installer)

        ctx = _make_ctx(installer_resolver=installer_resolver)
        result = await configure_server(
            server_name="bad-server",
            package_identifier="bad-pkg",
            ctx=ctx,
            clients="claude_code",
        )

        assert result["success"] is False
        assert result["install_status"] == "failed"
        assert "installation failed" in result["message"].lower()

    @patch("mcp_tap.tools.configure.write_server_config")
    @patch("mcp_tap.tools.configure.resolve_config_locations")
    async def test_install_failure_does_not_write_config(
        self,
        mock_locations: MagicMock,
        mock_write: MagicMock,
    ):
        """Should NOT write config when install fails."""
        mock_locations.return_value = [_fake_location()]
        installer = _mock_installer(install_result=_failed_install_result())

        installer_resolver = AsyncMock()
        installer_resolver.resolve_installer = AsyncMock(return_value=installer)

        ctx = _make_ctx(installer_resolver=installer_resolver)
        await configure_server(
            server_name="s",
            package_identifier="p",
            ctx=ctx,
            clients="claude_code",
        )

        mock_write.assert_not_called()

    @patch("mcp_tap.tools.configure.resolve_config_locations")
    async def test_installer_not_found_returns_error(
        self,
        mock_locations: MagicMock,
    ):
        """Should return error when package manager is not available."""
        mock_locations.return_value = [_fake_location()]

        installer_resolver = AsyncMock()
        installer_resolver.resolve_installer = AsyncMock(
            side_effect=InstallerNotFoundError("Package manager for npm is not installed.")
        )

        ctx = _make_ctx(installer_resolver=installer_resolver)
        result = await configure_server(
            server_name="s",
            package_identifier="p",
            ctx=ctx,
            clients="claude_code",
        )

        assert result["success"] is False
        assert "not installed" in result["message"].lower()


# ═══════════════════════════════════════════════════════════════
# Validation Failure Tests
# ═══════════════════════════════════════════════════════════════


class TestConfigureValidationFails:
    """Tests for when install succeeds but validation fails."""

    @patch("mcp_tap.tools.configure.write_server_config")
    @patch("mcp_tap.tools.configure.resolve_config_locations")
    async def test_validation_failure_returns_failure(
        self,
        mock_locations: MagicMock,
        mock_write: MagicMock,
    ):
        """Should return success=False when validation fails (config NOT written)."""
        mock_locations.return_value = [_fake_location()]

        installer_resolver = AsyncMock()
        installer_resolver.resolve_installer = AsyncMock(return_value=_mock_installer())

        connection_tester = AsyncMock()
        connection_tester.test_server_connection = AsyncMock(
            return_value=_failed_connection_result("s", "timed out")
        )

        ctx = _make_ctx(
            installer_resolver=installer_resolver,
            connection_tester=connection_tester,
        )
        result = await configure_server(
            server_name="s",
            package_identifier="p",
            ctx=ctx,
            clients="claude_code",
        )

        assert result["success"] is False
        assert result["validation_passed"] is False

    @patch("mcp_tap.tools.configure.write_server_config")
    @patch("mcp_tap.tools.configure.resolve_config_locations")
    async def test_validation_failure_config_not_written(
        self,
        mock_locations: MagicMock,
        mock_write: MagicMock,
    ):
        """Should NOT write config when validation fails (transactional behavior)."""
        mock_locations.return_value = [_fake_location()]

        installer_resolver = AsyncMock()
        installer_resolver.resolve_installer = AsyncMock(return_value=_mock_installer())

        connection_tester = AsyncMock()
        connection_tester.test_server_connection = AsyncMock(
            return_value=_failed_connection_result()
        )

        ctx = _make_ctx(
            installer_resolver=installer_resolver,
            connection_tester=connection_tester,
        )
        await configure_server(
            server_name="s",
            package_identifier="p",
            ctx=ctx,
            clients="claude_code",
        )

        mock_write.assert_not_called()

    @patch("mcp_tap.tools.configure.write_server_config")
    @patch("mcp_tap.tools.configure.resolve_config_locations")
    async def test_validation_failure_no_tools_discovered(
        self,
        mock_locations: MagicMock,
        mock_write: MagicMock,
    ):
        """Should return empty tools_discovered when validation fails."""
        mock_locations.return_value = [_fake_location()]

        installer_resolver = AsyncMock()
        installer_resolver.resolve_installer = AsyncMock(return_value=_mock_installer())

        connection_tester = AsyncMock()
        connection_tester.test_server_connection = AsyncMock(
            return_value=_failed_connection_result()
        )

        ctx = _make_ctx(
            installer_resolver=installer_resolver,
            connection_tester=connection_tester,
        )
        result = await configure_server(
            server_name="s",
            package_identifier="p",
            ctx=ctx,
            clients="claude_code",
        )

        assert result["tools_discovered"] == []

    @patch("mcp_tap.tools.configure.write_server_config")
    @patch("mcp_tap.tools.configure.resolve_config_locations")
    async def test_validation_failure_message_mentions_warning(
        self,
        mock_locations: MagicMock,
        mock_write: MagicMock,
    ):
        """Should include validation warning in the message."""
        mock_locations.return_value = [_fake_location()]

        installer_resolver = AsyncMock()
        installer_resolver.resolve_installer = AsyncMock(return_value=_mock_installer())

        connection_tester = AsyncMock()
        connection_tester.test_server_connection = AsyncMock(
            return_value=_failed_connection_result(error="Connection refused")
        )

        ctx = _make_ctx(
            installer_resolver=installer_resolver,
            connection_tester=connection_tester,
        )
        result = await configure_server(
            server_name="s",
            package_identifier="p",
            ctx=ctx,
            clients="claude_code",
        )

        assert "Validation warning" in result["message"]
        assert "Connection refused" in result["message"]


# ═══════════════════════════════════════════════════════════════
# No Client Detected Tests
# ═══════════════════════════════════════════════════════════════


class TestConfigureNoClient:
    """Tests for when no MCP client is detected."""

    @patch("mcp_tap.tools.configure.resolve_config_locations", return_value=[])
    async def test_no_client_returns_error(self, _mock_locations: MagicMock):
        """Should return success=False with helpful message."""
        ctx = _make_ctx()
        result = await configure_server(
            server_name="s",
            package_identifier="p",
            ctx=ctx,
        )

        assert result["success"] is False
        assert "No MCP client detected" in result["message"]
        assert result["install_status"] == "skipped"


# ═══════════════════════════════════════════════════════════════
# Multi-Client Tests
# ═══════════════════════════════════════════════════════════════


class TestConfigureMultiClient:
    """Tests for configuring multiple clients at once."""

    @patch("mcp_tap.tools.configure.write_server_config")
    @patch("mcp_tap.tools.configure.resolve_config_locations")
    async def test_multi_client_success(
        self,
        mock_locations: MagicMock,
        mock_write: MagicMock,
    ):
        """Should write config to all clients and return per-client results."""
        mock_locations.return_value = [
            _fake_location(MCPClient.CLAUDE_DESKTOP, "/a"),
            _fake_location(MCPClient.CURSOR, "/b"),
        ]

        installer_resolver = AsyncMock()
        installer_resolver.resolve_installer = AsyncMock(return_value=_mock_installer())

        connection_tester = AsyncMock()
        connection_tester.test_server_connection = AsyncMock(return_value=_ok_connection_result())

        ctx = _make_ctx(
            installer_resolver=installer_resolver,
            connection_tester=connection_tester,
        )
        result = await configure_server(
            server_name="s",
            package_identifier="p",
            ctx=ctx,
            clients="claude_desktop,cursor",
        )

        assert result["success"] is True
        assert "per_client_results" in result
        assert len(result["per_client_results"]) == 2
        assert mock_write.call_count == 2

    @patch("mcp_tap.tools.configure.write_server_config")
    @patch("mcp_tap.tools.configure.resolve_config_locations")
    async def test_multi_client_partial_failure(
        self,
        mock_locations: MagicMock,
        mock_write: MagicMock,
    ):
        """Should succeed overall even if one client config write fails."""
        mock_locations.return_value = [
            _fake_location(MCPClient.CLAUDE_DESKTOP, "/a"),
            _fake_location(MCPClient.CURSOR, "/b"),
        ]
        # Second write fails
        mock_write.side_effect = [None, ConfigWriteError("Permission denied")]

        installer_resolver = AsyncMock()
        installer_resolver.resolve_installer = AsyncMock(return_value=_mock_installer())

        connection_tester = AsyncMock()
        connection_tester.test_server_connection = AsyncMock(return_value=_ok_connection_result())

        ctx = _make_ctx(
            installer_resolver=installer_resolver,
            connection_tester=connection_tester,
        )
        result = await configure_server(
            server_name="s",
            package_identifier="p",
            ctx=ctx,
            clients="claude_desktop,cursor",
        )

        assert result["success"] is True
        per_client = result["per_client_results"]
        assert per_client[0]["success"] is True
        assert per_client[1]["success"] is False

    @patch("mcp_tap.tools.configure.write_server_config")
    @patch("mcp_tap.tools.configure.resolve_config_locations")
    async def test_multi_client_message_lists_clients(
        self,
        mock_locations: MagicMock,
        mock_write: MagicMock,
    ):
        """Should mention which clients were configured in the message."""
        mock_locations.return_value = [
            _fake_location(MCPClient.CLAUDE_DESKTOP, "/a"),
            _fake_location(MCPClient.CURSOR, "/b"),
        ]

        installer_resolver = AsyncMock()
        installer_resolver.resolve_installer = AsyncMock(return_value=_mock_installer())

        connection_tester = AsyncMock()
        connection_tester.test_server_connection = AsyncMock(return_value=_ok_connection_result())

        ctx = _make_ctx(
            installer_resolver=installer_resolver,
            connection_tester=connection_tester,
        )
        result = await configure_server(
            server_name="s",
            package_identifier="p",
            ctx=ctx,
            clients="claude_desktop,cursor",
        )

        assert "2/2" in result["message"]


# ═══════════════════════════════════════════════════════════════
# Project-Scoped Config Tests
# ═══════════════════════════════════════════════════════════════


class TestConfigureProjectScope:
    """Tests for project-scoped configuration."""

    @patch("mcp_tap.tools.configure.write_server_config")
    @patch("mcp_tap.tools.configure.resolve_config_locations")
    async def test_project_scope_passes_params(
        self,
        mock_locations: MagicMock,
        mock_write: MagicMock,
    ):
        """Should pass scope and project_path to resolve_config_locations."""
        mock_locations.return_value = [
            _fake_location(MCPClient.CURSOR, "/project/.cursor/mcp.json", scope="project")
        ]

        installer_resolver = AsyncMock()
        installer_resolver.resolve_installer = AsyncMock(return_value=_mock_installer())

        connection_tester = AsyncMock()
        connection_tester.test_server_connection = AsyncMock(return_value=_ok_connection_result())

        ctx = _make_ctx(
            installer_resolver=installer_resolver,
            connection_tester=connection_tester,
        )
        await configure_server(
            server_name="s",
            package_identifier="p",
            ctx=ctx,
            clients="cursor",
            scope="project",
            project_path="/project",
        )

        mock_locations.assert_called_once_with("cursor", scope="project", project_path="/project")


# ═══════════════════════════════════════════════════════════════
# Env Var Parsing Tests
# ═══════════════════════════════════════════════════════════════


class TestConfigureEnvVarParsing:
    """Tests for env var parsing in configure_server."""

    @patch("mcp_tap.tools.configure.write_server_config")
    @patch("mcp_tap.tools.configure.resolve_config_locations")
    async def test_env_vars_parsed_into_config(
        self,
        mock_locations: MagicMock,
        mock_write: MagicMock,
    ):
        """Should parse comma-separated KEY=VALUE pairs into env dict."""
        mock_locations.return_value = [_fake_location()]

        installer_resolver = AsyncMock()
        installer_resolver.resolve_installer = AsyncMock(return_value=_mock_installer())

        connection_tester = AsyncMock()
        connection_tester.test_server_connection = AsyncMock(return_value=_ok_connection_result())

        ctx = _make_ctx(
            installer_resolver=installer_resolver,
            connection_tester=connection_tester,
        )
        result = await configure_server(
            server_name="s",
            package_identifier="p",
            ctx=ctx,
            clients="claude_code",
            env_vars="DB_URL=postgresql://localhost/db,API_KEY=sk-123",
        )

        written_env = result["config_written"].get("env", {})
        assert written_env["DB_URL"] == "postgresql://localhost/db"
        assert written_env["API_KEY"] == "sk-123"

    @patch("mcp_tap.tools.configure.write_server_config")
    @patch("mcp_tap.tools.configure.resolve_config_locations")
    async def test_empty_env_vars_no_env_in_config(
        self,
        mock_locations: MagicMock,
        mock_write: MagicMock,
    ):
        """Should not include env in config_written when env_vars is empty."""
        mock_locations.return_value = [_fake_location()]

        installer_resolver = AsyncMock()
        installer_resolver.resolve_installer = AsyncMock(return_value=_mock_installer())

        connection_tester = AsyncMock()
        connection_tester.test_server_connection = AsyncMock(return_value=_ok_connection_result())

        ctx = _make_ctx(
            installer_resolver=installer_resolver,
            connection_tester=connection_tester,
        )
        result = await configure_server(
            server_name="s",
            package_identifier="p",
            ctx=ctx,
            clients="claude_code",
            env_vars="",
        )

        # ServerConfig.to_dict() omits env when empty
        assert "env" not in result["config_written"]


# ═══════════════════════════════════════════════════════════════
# Unexpected Exception Tests
# ═══════════════════════════════════════════════════════════════


class TestConfigureUnexpectedErrors:
    """Tests for unexpected exception handling."""

    @patch(
        "mcp_tap.tools.configure.resolve_config_locations",
        side_effect=RuntimeError("unexpected"),
    )
    async def test_unexpected_error_returns_dict(self, _mock_locations: MagicMock):
        """Should return error dict for unexpected exceptions."""
        ctx = _make_ctx()
        result = await configure_server(
            server_name="s",
            package_identifier="p",
            ctx=ctx,
        )

        assert result["success"] is False
        assert "Internal error" in result["message"]
        ctx.error.assert_awaited_once()

    @patch("mcp_tap.tools.configure.write_server_config")
    @patch("mcp_tap.tools.configure.resolve_config_locations")
    async def test_config_write_error_returns_mcptap_error(
        self,
        mock_locations: MagicMock,
        mock_write: MagicMock,
    ):
        """Should handle ConfigWriteError (server already exists)."""
        mock_locations.return_value = [_fake_location()]
        mock_write.side_effect = ConfigWriteError("Server 'x' already exists")

        installer_resolver = AsyncMock()
        installer_resolver.resolve_installer = AsyncMock(return_value=_mock_installer())

        connection_tester = AsyncMock()
        connection_tester.test_server_connection = AsyncMock(return_value=_ok_connection_result())

        ctx = _make_ctx(
            installer_resolver=installer_resolver,
            connection_tester=connection_tester,
        )
        result = await configure_server(
            server_name="x",
            package_identifier="p",
            ctx=ctx,
            clients="claude_code",
        )

        assert result["success"] is False
        assert "already exists" in result["message"]


# ═══════════════════════════════════════════════════════════════
# PyPI Registry Type Tests
# ═══════════════════════════════════════════════════════════════


class TestConfigurePypiRegistry:
    """Tests for configuring a server from PyPI registry."""

    @patch("mcp_tap.tools.configure.write_server_config")
    @patch("mcp_tap.tools.configure.resolve_config_locations")
    async def test_pypi_registry_resolved(
        self,
        mock_locations: MagicMock,
        mock_write: MagicMock,
    ):
        """Should pass pypi RegistryType to resolve_installer."""
        mock_locations.return_value = [_fake_location()]
        installer = _mock_installer(command="uvx", args=["some-mcp-server"])

        installer_resolver = AsyncMock()
        installer_resolver.resolve_installer = AsyncMock(return_value=installer)

        connection_tester = AsyncMock()
        connection_tester.test_server_connection = AsyncMock(return_value=_ok_connection_result())

        ctx = _make_ctx(
            installer_resolver=installer_resolver,
            connection_tester=connection_tester,
        )
        result = await configure_server(
            server_name="pypi-server",
            package_identifier="some-mcp-server",
            ctx=ctx,
            clients="claude_code",
            registry_type="pypi",
        )

        installer_resolver.resolve_installer.assert_awaited_once()
        call_args = installer_resolver.resolve_installer.call_args[0]
        from mcp_tap.models import RegistryType

        assert call_args[0] == RegistryType.PYPI

        assert result["success"] is True
        assert result["config_written"]["command"] == "uvx"


# ═══════════════════════════════════════════════════════════════
# _parse_env_vars Unit Tests
# ═══════════════════════════════════════════════════════════════


class TestParseEnvVars:
    """Tests for the _parse_env_vars helper function."""

    def test_empty_string(self):
        assert _parse_env_vars("") == {}

    def test_single_pair(self):
        assert _parse_env_vars("DB_URL=postgres://localhost") == {
            "DB_URL": "postgres://localhost",
        }

    def test_multiple_pairs(self):
        result = _parse_env_vars("KEY1=val1,KEY2=val2,KEY3=val3")
        assert result == {"KEY1": "val1", "KEY2": "val2", "KEY3": "val3"}

    def test_strips_whitespace(self):
        result = _parse_env_vars("  KEY = value , OTHER = stuff  ")
        assert result == {"KEY": "value", "OTHER": "stuff"}

    def test_value_with_equals_sign(self):
        result = _parse_env_vars("URL=postgres://host?opt=true")
        assert result == {"URL": "postgres://host?opt=true"}

    def test_pair_without_equals_preserved_in_value(self):
        """Non-KEY= entries after a comma are preserved as part of the previous value."""
        result = _parse_env_vars("KEY=val,BROKEN_ENTRY,OTHER=x")
        assert result == {"KEY": "val,BROKEN_ENTRY", "OTHER": "x"}

    # ── Bug M3: Commas inside values ────────────────────────────

    def test_comma_in_value_preserved(self):
        """Should preserve commas in values when not followed by KEY= (Bug M3).

        The regex only splits on commas followed by a valid KEY= pattern.
        Commas followed by text without = are preserved in the value.
        """
        result = _parse_env_vars("URL=http://host:8080/path,API_KEY=sk-123")
        assert result == {"URL": "http://host:8080/path", "API_KEY": "sk-123"}

    def test_multiple_pairs_with_commas_in_values(self):
        """Should correctly parse multiple pairs where values contain commas (Bug M3)."""
        result = _parse_env_vars("A=1,B=2,C=val,with,commas,D=4")
        assert result == {"A": "1", "B": "2", "C": "val,with,commas", "D": "4"}

    def test_single_pair_with_many_commas_in_value(self):
        """Should return a single pair when value has commas but no other KEY= follows (Bug M3)."""
        result = _parse_env_vars("SINGLE=value,with,many,commas")
        assert result == {"SINGLE": "value,with,many,commas"}


# ═══════════════════════════════════════════════════════════════
# Bug H2 — No Redundant test_server_connection After Healing
# ═══════════════════════════════════════════════════════════════


class TestConfigureNoRedundantValidation:
    """After healing succeeds, test_server_connection should NOT be called again."""

    @patch("mcp_tap.tools.configure.write_server_config")
    @patch("mcp_tap.tools.configure.resolve_config_locations")
    async def test_no_extra_test_after_healing(
        self,
        mock_locations: MagicMock,
        mock_write: MagicMock,
    ):
        """test_server_connection should be called exactly once (for initial validation).

        The healing loop's own re-validation counts separately within
        heal_and_retry. After healing succeeds, _configure_single should NOT
        spawn yet another test_server_connection call (Bug H2).
        """
        from mcp_tap.models import HealingResult

        mock_locations.return_value = [_fake_location()]

        installer_resolver = AsyncMock()
        installer_resolver.resolve_installer = AsyncMock(return_value=_mock_installer())

        # Initial validation fails
        connection_tester = AsyncMock()
        connection_tester.test_server_connection = AsyncMock(
            return_value=_failed_connection_result("s", "Connection refused")
        )

        # Healing succeeds
        healed_config = ServerConfig(command="/usr/local/bin/npx", args=["-y", "test-pkg"])
        healing = AsyncMock()
        healing.heal_and_retry = AsyncMock(
            return_value=HealingResult(
                fixed=True,
                attempts=[],
                fixed_config=healed_config,
            )
        )

        ctx = _make_ctx(
            installer_resolver=installer_resolver,
            connection_tester=connection_tester,
            healing=healing,
        )
        result = await configure_server(
            server_name="s",
            package_identifier="p",
            ctx=ctx,
            clients="claude_code",
        )

        assert result["success"] is True
        # test_server_connection called exactly once — for the initial validation
        # NOT called again after healing
        connection_tester.test_server_connection.assert_awaited_once()


# ═══════════════════════════════════════════════════════════════
# Bug H3 — Transactional Config Write (After Validation)
# ═══════════════════════════════════════════════════════════════


class TestConfigureTransactionalWrite:
    """Config is ONLY written after validation passes (Bug H3)."""

    @patch("mcp_tap.tools.configure.write_server_config")
    @patch("mcp_tap.tools.configure.resolve_config_locations")
    async def test_config_written_on_success(
        self,
        mock_locations: MagicMock,
        mock_write: MagicMock,
    ):
        """Should write config AFTER validation passes (Bug H3)."""
        mock_locations.return_value = [_fake_location()]

        installer_resolver = AsyncMock()
        installer_resolver.resolve_installer = AsyncMock(return_value=_mock_installer())

        connection_tester = AsyncMock()
        connection_tester.test_server_connection = AsyncMock(return_value=_ok_connection_result())

        ctx = _make_ctx(
            installer_resolver=installer_resolver,
            connection_tester=connection_tester,
        )
        result = await configure_server(
            server_name="srv",
            package_identifier="pkg",
            ctx=ctx,
            clients="claude_code",
        )

        assert result["success"] is True
        assert result["validation_passed"] is True
        mock_write.assert_called_once()

    @patch("mcp_tap.tools.configure.write_server_config")
    @patch("mcp_tap.tools.configure.resolve_config_locations")
    async def test_config_not_written_on_failed_validation_and_healing(
        self,
        mock_locations: MagicMock,
        mock_write: MagicMock,
    ):
        """Should NOT write config when validation fails AND healing fails (Bug H3)."""
        from mcp_tap.models import HealingResult

        mock_locations.return_value = [_fake_location()]

        installer_resolver = AsyncMock()
        installer_resolver.resolve_installer = AsyncMock(return_value=_mock_installer())

        connection_tester = AsyncMock()
        connection_tester.test_server_connection = AsyncMock(
            return_value=_failed_connection_result("s", "Connection refused")
        )

        healing = AsyncMock()
        healing.heal_and_retry = AsyncMock(
            return_value=HealingResult(
                fixed=False,
                attempts=[],
                user_action_needed="Set env vars",
            )
        )

        ctx = _make_ctx(
            installer_resolver=installer_resolver,
            connection_tester=connection_tester,
            healing=healing,
        )
        result = await configure_server(
            server_name="s",
            package_identifier="p",
            ctx=ctx,
            clients="claude_code",
        )

        assert result["success"] is False
        mock_write.assert_not_called()

    @patch("mcp_tap.tools.configure.write_server_config")
    @patch("mcp_tap.tools.configure.resolve_config_locations")
    async def test_multi_client_config_not_written_when_validation_fails(
        self,
        mock_locations: MagicMock,
        mock_write: MagicMock,
    ):
        """Should NOT write config to ANY client when validation + healing fail (Bug H3)."""
        from mcp_tap.models import HealingResult

        mock_locations.return_value = [
            _fake_location(MCPClient.CLAUDE_DESKTOP, "/a"),
            _fake_location(MCPClient.CURSOR, "/b"),
        ]

        installer_resolver = AsyncMock()
        installer_resolver.resolve_installer = AsyncMock(return_value=_mock_installer())

        connection_tester = AsyncMock()
        connection_tester.test_server_connection = AsyncMock(
            return_value=_failed_connection_result("s", "Timeout")
        )

        healing = AsyncMock()
        healing.heal_and_retry = AsyncMock(
            return_value=HealingResult(
                fixed=False,
                attempts=[],
                user_action_needed="Manual fix required",
            )
        )

        ctx = _make_ctx(
            installer_resolver=installer_resolver,
            connection_tester=connection_tester,
            healing=healing,
        )
        result = await configure_server(
            server_name="s",
            package_identifier="p",
            ctx=ctx,
            clients="claude_desktop,cursor",
        )

        assert result["success"] is False
        mock_write.assert_not_called()


# ═══════════════════════════════════════════════════════════════
# HTTP Transport Detection Tests
# ═══════════════════════════════════════════════════════════════


class TestIsHttpTransport:
    """Tests for the _is_http_transport helper function."""

    def test_https_url_detected(self):
        assert _is_http_transport("https://mcp.vercel.com", "npm") is True

    def test_http_url_detected(self):
        assert _is_http_transport("http://localhost:3000/mcp", "npm") is True

    def test_streamable_http_registry_type(self):
        assert _is_http_transport("some-package", "streamable-http") is True

    def test_http_registry_type(self):
        assert _is_http_transport("some-package", "http") is True

    def test_sse_registry_type(self):
        assert _is_http_transport("some-package", "sse") is True

    def test_npm_package_not_detected(self):
        assert _is_http_transport("@modelcontextprotocol/server-postgres", "npm") is False

    def test_pypi_package_not_detected(self):
        assert _is_http_transport("mcp-server-git", "pypi") is False

    def test_url_with_path_detected(self):
        assert _is_http_transport("https://mcp.example.com/v1/sse", "npm") is True

    def test_url_takes_priority_over_registry_type(self):
        """URL detection should work even with registry_type='npm'."""
        assert _is_http_transport("https://mcp.vercel.com", "npm") is True


# ═══════════════════════════════════════════════════════════════
# HTTP Transport Configure Tests
# ═══════════════════════════════════════════════════════════════


class TestConfigureHttpTransport:
    """Tests for configuring HTTP transport servers (native config + mcp-remote fallback)."""

    @patch("mcp_tap.tools.configure.write_server_config")
    @patch("mcp_tap.tools.configure.resolve_config_locations")
    async def test_http_url_skips_install(
        self,
        mock_locations: MagicMock,
        mock_write: MagicMock,
    ):
        """Should skip package install for HTTPS URLs."""
        mock_locations.return_value = [_fake_location()]  # Claude Code

        http_reachability = AsyncMock()
        http_reachability.check_reachability = AsyncMock(
            return_value=_ok_connection_result("vercel")
        )

        installer_resolver = AsyncMock()
        installer_resolver.resolve_installer = AsyncMock()

        ctx = _make_ctx(
            http_reachability=http_reachability,
            installer_resolver=installer_resolver,
        )
        result = await configure_server(
            server_name="vercel",
            package_identifier="https://mcp.vercel.com",
            ctx=ctx,
            clients="claude_code",
        )

        assert result["success"] is True
        assert result["validation_passed"] is True
        installer_resolver.resolve_installer.assert_not_awaited()

    @patch("mcp_tap.tools.configure.write_server_config")
    @patch("mcp_tap.tools.configure.resolve_config_locations")
    async def test_http_url_builds_native_config_for_claude_code(
        self,
        mock_locations: MagicMock,
        mock_write: MagicMock,
    ):
        """Should build HttpServerConfig with type/url for Claude Code."""
        mock_locations.return_value = [_fake_location()]  # Claude Code

        http_reachability = AsyncMock()
        http_reachability.check_reachability = AsyncMock(
            return_value=_ok_connection_result("vercel")
        )

        ctx = _make_ctx(http_reachability=http_reachability)
        result = await configure_server(
            server_name="vercel",
            package_identifier="https://mcp.vercel.com",
            ctx=ctx,
            clients="claude_code",
        )

        config_written = result["config_written"]
        assert config_written["type"] == "http"
        assert config_written["url"] == "https://mcp.vercel.com"
        # Should NOT have command/args (native config, not mcp-remote)
        assert "command" not in config_written

    @patch("mcp_tap.tools.configure.write_server_config")
    @patch("mcp_tap.tools.configure.resolve_config_locations")
    async def test_http_url_with_env_vars(
        self,
        mock_locations: MagicMock,
        mock_write: MagicMock,
    ):
        """Should include env vars in the native HTTP config."""
        mock_locations.return_value = [_fake_location()]  # Claude Code

        http_reachability = AsyncMock()
        http_reachability.check_reachability = AsyncMock(
            return_value=_ok_connection_result("vercel")
        )

        ctx = _make_ctx(http_reachability=http_reachability)
        result = await configure_server(
            server_name="vercel",
            package_identifier="https://mcp.vercel.com",
            ctx=ctx,
            clients="claude_code",
            env_vars="API_KEY=sk-123",
        )

        config_written = result["config_written"]
        assert config_written["env"] == {"API_KEY": "sk-123"}

    @patch("mcp_tap.tools.configure.write_server_config")
    @patch("mcp_tap.tools.configure.resolve_config_locations")
    async def test_streamable_http_registry_type_skips_install(
        self,
        mock_locations: MagicMock,
        mock_write: MagicMock,
    ):
        """Should detect HTTP transport via registry_type='streamable-http'."""
        mock_locations.return_value = [_fake_location()]

        http_reachability = AsyncMock()
        http_reachability.check_reachability = AsyncMock(
            return_value=_ok_connection_result("remote-srv")
        )

        installer_resolver = AsyncMock()
        installer_resolver.resolve_installer = AsyncMock()

        ctx = _make_ctx(
            http_reachability=http_reachability,
            installer_resolver=installer_resolver,
        )
        result = await configure_server(
            server_name="remote-srv",
            package_identifier="https://remote.example.com/mcp",
            ctx=ctx,
            clients="claude_code",
            registry_type="streamable-http",
        )

        assert result["success"] is True
        installer_resolver.resolve_installer.assert_not_awaited()

    @patch("mcp_tap.tools.configure.write_server_config")
    @patch("mcp_tap.tools.configure.resolve_config_locations")
    async def test_sse_registry_type_uses_native_sse_type(
        self,
        mock_locations: MagicMock,
        mock_write: MagicMock,
    ):
        """Should use native SSE config type for Claude Code with registry_type='sse'."""
        mock_locations.return_value = [_fake_location()]  # Claude Code

        http_reachability = AsyncMock()
        http_reachability.check_reachability = AsyncMock(
            return_value=_ok_connection_result("sse-srv")
        )

        ctx = _make_ctx(http_reachability=http_reachability)
        result = await configure_server(
            server_name="sse-srv",
            package_identifier="https://sse.example.com",
            ctx=ctx,
            clients="claude_code",
            registry_type="sse",
        )

        config_written = result["config_written"]
        assert config_written["type"] == "sse"
        assert config_written["url"] == "https://sse.example.com"

    @patch("mcp_tap.tools.configure.write_server_config")
    @patch("mcp_tap.tools.configure.resolve_config_locations")
    async def test_http_transport_reachability_check_runs(
        self,
        mock_locations: MagicMock,
        mock_write: MagicMock,
    ):
        """Reachability check should run for HTTP transport servers.

        Config is ALWAYS written -- failure is a warning, not a blocker.
        """
        mock_locations.return_value = [_fake_location()]

        http_reachability = AsyncMock()
        http_reachability.check_reachability = AsyncMock(
            return_value=_failed_connection_result("srv", "Cannot reach https://mcp.example.com")
        )

        ctx = _make_ctx(http_reachability=http_reachability)
        result = await configure_server(
            server_name="srv",
            package_identifier="https://mcp.example.com",
            ctx=ctx,
            clients="claude_code",
        )

        # Config is ALWAYS written for HTTP servers
        assert result["success"] is True
        assert result["validation_passed"] is False
        mock_write.assert_called_once()

    @patch("mcp_tap.tools.configure.write_server_config")
    @patch("mcp_tap.tools.configure.resolve_config_locations")
    async def test_http_transport_multi_client_uses_mcp_remote(
        self,
        mock_locations: MagicMock,
        mock_write: MagicMock,
    ):
        """Should use mcp-remote for mixed clients (non-native HTTP support)."""
        mock_locations.return_value = [
            _fake_location(MCPClient.CLAUDE_DESKTOP, "/a"),
            _fake_location(MCPClient.CURSOR, "/b"),
        ]

        http_reachability = AsyncMock()
        http_reachability.check_reachability = AsyncMock(return_value=_ok_connection_result("srv"))

        ctx = _make_ctx(http_reachability=http_reachability)
        result = await configure_server(
            server_name="srv",
            package_identifier="https://mcp.example.com",
            ctx=ctx,
            clients="claude_desktop,cursor",
        )

        assert result["success"] is True
        assert "per_client_results" in result
        assert len(result["per_client_results"]) == 2
        assert mock_write.call_count == 2
        # Mixed clients -> mcp-remote fallback
        config_written = result["config_written"]
        assert config_written["command"] == "npx"
        assert config_written["args"] == ["-y", "mcp-remote", "https://mcp.example.com"]

    @patch("mcp_tap.tools.configure.write_server_config")
    @patch("mcp_tap.tools.configure.resolve_config_locations")
    async def test_http_transport_security_gate_runs(
        self,
        mock_locations: MagicMock,
        mock_write: MagicMock,
    ):
        """Security gate should still run for HTTP transport servers."""
        from mcp_tap.models import SecurityReport, SecurityRisk, SecuritySignal

        mock_locations.return_value = [_fake_location()]

        security_gate = AsyncMock()
        security_gate.run_security_gate = AsyncMock(
            return_value=SecurityReport(
                overall_risk=SecurityRisk.BLOCK,
                signals=[
                    SecuritySignal(
                        category="command",
                        risk=SecurityRisk.BLOCK,
                        message="Suspicious command",
                    )
                ],
            )
        )

        ctx = _make_ctx(security_gate=security_gate)
        result = await configure_server(
            server_name="suspicious",
            package_identifier="https://evil.example.com",
            ctx=ctx,
            clients="claude_code",
        )

        assert result["success"] is False
        assert result["install_status"] == "blocked_by_security"
        security_gate.run_security_gate.assert_awaited_once()

    @patch("mcp_tap.tools.configure.write_server_config")
    @patch("mcp_tap.tools.configure.resolve_config_locations")
    async def test_http_transport_install_status_is_configured(
        self,
        mock_locations: MagicMock,
        mock_write: MagicMock,
    ):
        """install_status should be 'configured' for HTTP transport (no install needed)."""
        mock_locations.return_value = [_fake_location()]

        http_reachability = AsyncMock()
        http_reachability.check_reachability = AsyncMock(return_value=_ok_connection_result("srv"))

        ctx = _make_ctx(http_reachability=http_reachability)
        result = await configure_server(
            server_name="srv",
            package_identifier="https://mcp.example.com",
            ctx=ctx,
            clients="claude_code",
        )

        assert result["success"] is True
        assert result["install_status"] == "configured"

    @patch("mcp_tap.tools.configure._update_lockfile")
    @patch("mcp_tap.tools.configure.write_server_config")
    @patch("mcp_tap.tools.configure.resolve_config_locations")
    async def test_http_transport_updates_lockfile(
        self,
        mock_locations: MagicMock,
        mock_write: MagicMock,
        mock_lockfile: MagicMock,
    ):
        """Should update lockfile for HTTP transport when project_path is set."""
        mock_locations.return_value = [_fake_location()]

        http_reachability = AsyncMock()
        http_reachability.check_reachability = AsyncMock(return_value=_ok_connection_result("srv"))

        ctx = _make_ctx(http_reachability=http_reachability)
        await configure_server(
            server_name="srv",
            package_identifier="https://mcp.example.com",
            ctx=ctx,
            clients="claude_code",
            project_path="/my/project",
            registry_type="streamable-http",
        )

        mock_lockfile.assert_called_once()
        call_kwargs = mock_lockfile.call_args[1]
        assert call_kwargs["server_name"] == "srv"
        assert call_kwargs["package_identifier"] == "https://mcp.example.com"
        assert call_kwargs["registry_type"] == "streamable-http"


# ===============================================================
# HTTP Native Config Tests (new behavior)
# ===============================================================


class TestConfigureHttpNative:
    """Tests for native HTTP config for Claude Code vs mcp-remote fallback."""

    @patch("mcp_tap.tools.configure.write_server_config")
    @patch("mcp_tap.tools.configure.resolve_config_locations")
    async def test_claude_code_gets_native_http_config(
        self,
        mock_locations: MagicMock,
        mock_write: MagicMock,
    ):
        """Claude Code should receive native HTTP config (type+url)."""
        mock_locations.return_value = [_fake_location(MCPClient.CLAUDE_CODE)]

        http_reachability = AsyncMock()
        http_reachability.check_reachability = AsyncMock(
            return_value=_ok_connection_result("vercel")
        )

        ctx = _make_ctx(http_reachability=http_reachability)
        result = await configure_server(
            server_name="vercel",
            package_identifier="https://mcp.vercel.com",
            ctx=ctx,
            clients="claude_code",
        )

        config_written = result["config_written"]
        assert config_written["type"] == "http"
        assert config_written["url"] == "https://mcp.vercel.com"
        assert "command" not in config_written

    @patch("mcp_tap.tools.configure.write_server_config")
    @patch("mcp_tap.tools.configure.resolve_config_locations")
    async def test_cursor_gets_mcp_remote_fallback(
        self,
        mock_locations: MagicMock,
        mock_write: MagicMock,
    ):
        """Cursor should receive mcp-remote fallback config."""
        mock_locations.return_value = [_fake_location(MCPClient.CURSOR, "/cursor/mcp.json")]

        http_reachability = AsyncMock()
        http_reachability.check_reachability = AsyncMock(
            return_value=_ok_connection_result("vercel")
        )

        ctx = _make_ctx(http_reachability=http_reachability)
        result = await configure_server(
            server_name="vercel",
            package_identifier="https://mcp.vercel.com",
            ctx=ctx,
            clients="cursor",
        )

        config_written = result["config_written"]
        assert config_written["command"] == "npx"
        assert config_written["args"] == ["-y", "mcp-remote", "https://mcp.vercel.com"]

    @patch("mcp_tap.tools.configure.write_server_config")
    @patch("mcp_tap.tools.configure.resolve_config_locations")
    async def test_mixed_locations_use_per_client_best_config(
        self,
        mock_locations: MagicMock,
        mock_write: MagicMock,
    ):
        """Mixed Claude Code + Cursor: native HTTP for Claude Code, mcp-remote for Cursor."""
        mock_locations.return_value = [
            _fake_location(MCPClient.CLAUDE_CODE, "/claude.json"),
            _fake_location(MCPClient.CURSOR, "/cursor/mcp.json"),
        ]

        http_reachability = AsyncMock()
        http_reachability.check_reachability = AsyncMock(return_value=_ok_connection_result("srv"))

        ctx = _make_ctx(http_reachability=http_reachability)
        result = await configure_server(
            server_name="srv",
            package_identifier="https://mcp.example.com",
            ctx=ctx,
            clients="claude_code,cursor",
        )

        assert result["success"] is True
        per_client = result["per_client_results"]
        assert len(per_client) == 2

        # Claude Code gets native HTTP config
        cc = next(r for r in per_client if r["client"] == "claude_code")
        assert cc["success"] is True
        assert cc["config_written"].get("url") == "https://mcp.example.com"
        assert "command" not in cc["config_written"]

        # Cursor gets mcp-remote fallback
        cursor = next(r for r in per_client if r["client"] == "cursor")
        assert cursor["success"] is True
        assert cursor["config_written"].get("command") == "npx"
        assert "mcp-remote" in cursor["config_written"].get("args", [])

        # Top-level config_written is the first successful client's (Claude Code = native)
        assert result["config_written"].get("url") == "https://mcp.example.com"

    @patch("mcp_tap.tools.configure.write_server_config")
    @patch("mcp_tap.tools.configure.resolve_config_locations")
    async def test_config_written_even_when_reachability_fails(
        self,
        mock_locations: MagicMock,
        mock_write: MagicMock,
    ):
        """Config should ALWAYS be written for HTTP servers, even on reachability failure."""
        mock_locations.return_value = [_fake_location()]

        http_reachability = AsyncMock()
        http_reachability.check_reachability = AsyncMock(
            return_value=_failed_connection_result("srv", "Cannot reach https://down.example.com")
        )

        ctx = _make_ctx(http_reachability=http_reachability)
        result = await configure_server(
            server_name="srv",
            package_identifier="https://down.example.com",
            ctx=ctx,
            clients="claude_code",
        )

        assert result["success"] is True
        assert result["validation_passed"] is False
        mock_write.assert_called_once()

    @patch("mcp_tap.tools.configure.write_server_config")
    @patch("mcp_tap.tools.configure.resolve_config_locations")
    async def test_401_counts_as_reachable(
        self,
        mock_locations: MagicMock,
        mock_write: MagicMock,
    ):
        """401 (OAuth) should count as reachable -> validation_passed=True."""
        mock_locations.return_value = [_fake_location()]

        http_reachability = AsyncMock()
        http_reachability.check_reachability = AsyncMock(
            return_value=ConnectionTestResult(
                success=True, server_name="oauth-srv", tools_discovered=[]
            )
        )

        ctx = _make_ctx(http_reachability=http_reachability)
        result = await configure_server(
            server_name="oauth-srv",
            package_identifier="https://oauth.example.com",
            ctx=ctx,
            clients="claude_code",
        )

        assert result["success"] is True
        assert result["validation_passed"] is True

    @patch("mcp_tap.tools.configure.write_server_config")
    @patch("mcp_tap.tools.configure.resolve_config_locations")
    async def test_message_mentions_restart_and_oauth(
        self,
        mock_locations: MagicMock,
        mock_write: MagicMock,
    ):
        """HTTP server message should mention Restart and OAuth."""
        mock_locations.return_value = [_fake_location()]

        http_reachability = AsyncMock()
        http_reachability.check_reachability = AsyncMock(return_value=_ok_connection_result("srv"))

        ctx = _make_ctx(http_reachability=http_reachability)
        result = await configure_server(
            server_name="srv",
            package_identifier="https://mcp.example.com",
            ctx=ctx,
            clients="claude_code",
        )

        assert "Restart" in result["message"]
        assert "OAuth" in result["message"]

    @patch("mcp_tap.tools.configure.write_server_config")
    @patch("mcp_tap.tools.configure.resolve_config_locations")
    async def test_sse_registry_type_produces_sse_type(
        self,
        mock_locations: MagicMock,
        mock_write: MagicMock,
    ):
        """registry_type='sse' should produce type='sse' in native config."""
        mock_locations.return_value = [_fake_location()]

        http_reachability = AsyncMock()
        http_reachability.check_reachability = AsyncMock(
            return_value=_ok_connection_result("sse-srv")
        )

        ctx = _make_ctx(http_reachability=http_reachability)
        result = await configure_server(
            server_name="sse-srv",
            package_identifier="https://sse.example.com",
            ctx=ctx,
            clients="claude_code",
            registry_type="sse",
        )

        config_written = result["config_written"]
        assert config_written["type"] == "sse"

    @patch("mcp_tap.tools.configure.write_server_config")
    @patch("mcp_tap.tools.configure.resolve_config_locations")
    async def test_connection_tester_not_called_for_http(
        self,
        mock_locations: MagicMock,
        mock_write: MagicMock,
    ):
        """connection_tester.test_server_connection should NOT be called for HTTP."""
        mock_locations.return_value = [_fake_location()]

        connection_tester = AsyncMock()
        connection_tester.test_server_connection = AsyncMock()

        http_reachability = AsyncMock()
        http_reachability.check_reachability = AsyncMock(return_value=_ok_connection_result("srv"))

        ctx = _make_ctx(
            connection_tester=connection_tester,
            http_reachability=http_reachability,
        )
        await configure_server(
            server_name="srv",
            package_identifier="https://mcp.example.com",
            ctx=ctx,
            clients="claude_code",
        )

        connection_tester.test_server_connection.assert_not_awaited()
        http_reachability.check_reachability.assert_awaited_once()

    @patch("mcp_tap.tools.configure.write_server_config")
    @patch("mcp_tap.tools.configure.resolve_config_locations")
    async def test_http_security_gate_still_runs(
        self,
        mock_locations: MagicMock,
        mock_write: MagicMock,
    ):
        """Security gate should still run for HTTP servers even with native config."""
        from mcp_tap.models import SecurityReport, SecurityRisk

        mock_locations.return_value = [_fake_location()]

        security_gate = AsyncMock()
        security_gate.run_security_gate = AsyncMock(
            return_value=SecurityReport(overall_risk=SecurityRisk.PASS, signals=[])
        )

        http_reachability = AsyncMock()
        http_reachability.check_reachability = AsyncMock(return_value=_ok_connection_result("srv"))

        ctx = _make_ctx(security_gate=security_gate, http_reachability=http_reachability)
        result = await configure_server(
            server_name="srv",
            package_identifier="https://mcp.example.com",
            ctx=ctx,
            clients="claude_code",
        )

        assert result["success"] is True
        security_gate.run_security_gate.assert_awaited_once()

    @patch("mcp_tap.tools.configure.write_server_config")
    @patch("mcp_tap.tools.configure.resolve_config_locations")
    async def test_http_install_status_is_configured(
        self,
        mock_locations: MagicMock,
        mock_write: MagicMock,
    ):
        """install_status should be 'configured' for all HTTP servers."""
        mock_locations.return_value = [_fake_location()]

        http_reachability = AsyncMock()
        http_reachability.check_reachability = AsyncMock(return_value=_ok_connection_result("srv"))

        ctx = _make_ctx(http_reachability=http_reachability)
        result = await configure_server(
            server_name="srv",
            package_identifier="https://mcp.example.com",
            ctx=ctx,
            clients="claude_code",
        )

        assert result["install_status"] == "configured"

    @patch("mcp_tap.tools.configure.write_server_config")
    @patch("mcp_tap.tools.configure.resolve_config_locations")
    async def test_http_multi_claude_code_only_gets_native(
        self,
        mock_locations: MagicMock,
        mock_write: MagicMock,
    ):
        """Multiple Claude Code locations should all get native HTTP config."""
        mock_locations.return_value = [
            _fake_location(MCPClient.CLAUDE_CODE, "/a"),
            _fake_location(MCPClient.CLAUDE_CODE, "/b"),
        ]

        http_reachability = AsyncMock()
        http_reachability.check_reachability = AsyncMock(return_value=_ok_connection_result("srv"))

        ctx = _make_ctx(http_reachability=http_reachability)
        result = await configure_server(
            server_name="srv",
            package_identifier="https://mcp.example.com",
            ctx=ctx,
            clients="claude_code,claude_code",
        )

        config_written = result["config_written"]
        assert config_written["type"] == "http"
        assert config_written["url"] == "https://mcp.example.com"
