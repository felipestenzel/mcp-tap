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
from mcp_tap.tools.configure import _parse_env_vars, configure_server

# ─── Helpers ─────────────────────────────────────────────────


def _make_ctx() -> MagicMock:
    """Build a mock Context with async info/error methods."""
    ctx = MagicMock()
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

    @patch("mcp_tap.tools.configure.test_server_connection")
    @patch("mcp_tap.tools.configure.write_server_config")
    @patch("mcp_tap.tools.configure.resolve_installer")
    @patch("mcp_tap.tools.configure.resolve_config_locations")
    async def test_full_success_flow(
        self,
        mock_locations: MagicMock,
        mock_resolve_installer: AsyncMock,
        mock_write: MagicMock,
        mock_test_conn: AsyncMock,
    ):
        """Should install, write config, validate, and return success."""
        mock_locations.return_value = [_fake_location()]
        installer = _mock_installer()
        mock_resolve_installer.return_value = installer
        mock_test_conn.return_value = _ok_connection_result("pg-server")

        ctx = _make_ctx()
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

    @patch("mcp_tap.tools.configure.test_server_connection")
    @patch("mcp_tap.tools.configure.write_server_config")
    @patch("mcp_tap.tools.configure.resolve_installer")
    @patch("mcp_tap.tools.configure.resolve_config_locations")
    async def test_config_written_contains_command_and_args(
        self,
        mock_locations: MagicMock,
        mock_resolve_installer: AsyncMock,
        mock_write: MagicMock,
        mock_test_conn: AsyncMock,
    ):
        """Should include config_written dict with command, args, env."""
        mock_locations.return_value = [_fake_location()]
        mock_resolve_installer.return_value = _mock_installer()
        mock_test_conn.return_value = _ok_connection_result()

        ctx = _make_ctx()
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

    @patch("mcp_tap.tools.configure.test_server_connection")
    @patch("mcp_tap.tools.configure.write_server_config")
    @patch("mcp_tap.tools.configure.resolve_installer")
    @patch("mcp_tap.tools.configure.resolve_config_locations")
    async def test_write_server_config_called_correctly(
        self,
        mock_locations: MagicMock,
        mock_resolve_installer: AsyncMock,
        mock_write: MagicMock,
        mock_test_conn: AsyncMock,
    ):
        """Should call write_server_config with correct path and config."""
        loc = _fake_location(path="/home/user/.claude.json")
        mock_locations.return_value = [loc]
        mock_resolve_installer.return_value = _mock_installer()
        mock_test_conn.return_value = _ok_connection_result()

        ctx = _make_ctx()
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

    @patch("mcp_tap.tools.configure.test_server_connection")
    @patch("mcp_tap.tools.configure.write_server_config")
    @patch("mcp_tap.tools.configure.resolve_installer")
    @patch("mcp_tap.tools.configure.resolve_config_locations")
    async def test_message_mentions_restart(
        self,
        mock_locations: MagicMock,
        mock_resolve_installer: AsyncMock,
        mock_write: MagicMock,
        mock_test_conn: AsyncMock,
    ):
        """Should tell user to restart their MCP client."""
        mock_locations.return_value = [_fake_location()]
        mock_resolve_installer.return_value = _mock_installer()
        mock_test_conn.return_value = _ok_connection_result()

        ctx = _make_ctx()
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
    @patch("mcp_tap.tools.configure.resolve_installer")
    @patch("mcp_tap.tools.configure.resolve_config_locations")
    async def test_install_failure_returns_error(
        self,
        mock_locations: MagicMock,
        mock_resolve_installer: AsyncMock,
        mock_write: MagicMock,
    ):
        """Should return success=False when install fails."""
        mock_locations.return_value = [_fake_location()]
        installer = _mock_installer(install_result=_failed_install_result("bad-pkg"))
        mock_resolve_installer.return_value = installer

        ctx = _make_ctx()
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
    @patch("mcp_tap.tools.configure.resolve_installer")
    @patch("mcp_tap.tools.configure.resolve_config_locations")
    async def test_install_failure_does_not_write_config(
        self,
        mock_locations: MagicMock,
        mock_resolve_installer: AsyncMock,
        mock_write: MagicMock,
    ):
        """Should NOT write config when install fails."""
        mock_locations.return_value = [_fake_location()]
        installer = _mock_installer(install_result=_failed_install_result())
        mock_resolve_installer.return_value = installer

        ctx = _make_ctx()
        await configure_server(
            server_name="s",
            package_identifier="p",
            ctx=ctx,
            clients="claude_code",
        )

        mock_write.assert_not_called()

    @patch("mcp_tap.tools.configure.resolve_installer")
    @patch("mcp_tap.tools.configure.resolve_config_locations")
    async def test_installer_not_found_returns_error(
        self,
        mock_locations: MagicMock,
        mock_resolve_installer: AsyncMock,
    ):
        """Should return error when package manager is not available."""
        mock_locations.return_value = [_fake_location()]
        mock_resolve_installer.side_effect = InstallerNotFoundError(
            "Package manager for npm is not installed."
        )

        ctx = _make_ctx()
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

    @patch("mcp_tap.tools.configure.test_server_connection")
    @patch("mcp_tap.tools.configure.write_server_config")
    @patch("mcp_tap.tools.configure.resolve_installer")
    @patch("mcp_tap.tools.configure.resolve_config_locations")
    async def test_validation_failure_still_succeeds(
        self,
        mock_locations: MagicMock,
        mock_resolve_installer: AsyncMock,
        mock_write: MagicMock,
        mock_test_conn: AsyncMock,
    ):
        """Should return success=True even when validation fails (config is written)."""
        mock_locations.return_value = [_fake_location()]
        mock_resolve_installer.return_value = _mock_installer()
        mock_test_conn.return_value = _failed_connection_result("s", "timed out")

        ctx = _make_ctx()
        result = await configure_server(
            server_name="s",
            package_identifier="p",
            ctx=ctx,
            clients="claude_code",
        )

        assert result["success"] is True
        assert result["validation_passed"] is False

    @patch("mcp_tap.tools.configure.test_server_connection")
    @patch("mcp_tap.tools.configure.write_server_config")
    @patch("mcp_tap.tools.configure.resolve_installer")
    @patch("mcp_tap.tools.configure.resolve_config_locations")
    async def test_validation_failure_config_still_written(
        self,
        mock_locations: MagicMock,
        mock_resolve_installer: AsyncMock,
        mock_write: MagicMock,
        mock_test_conn: AsyncMock,
    ):
        """Should still write config even when validation fails."""
        mock_locations.return_value = [_fake_location()]
        mock_resolve_installer.return_value = _mock_installer()
        mock_test_conn.return_value = _failed_connection_result()

        ctx = _make_ctx()
        await configure_server(
            server_name="s",
            package_identifier="p",
            ctx=ctx,
            clients="claude_code",
        )

        mock_write.assert_called_once()

    @patch("mcp_tap.tools.configure.test_server_connection")
    @patch("mcp_tap.tools.configure.write_server_config")
    @patch("mcp_tap.tools.configure.resolve_installer")
    @patch("mcp_tap.tools.configure.resolve_config_locations")
    async def test_validation_failure_no_tools_discovered(
        self,
        mock_locations: MagicMock,
        mock_resolve_installer: AsyncMock,
        mock_write: MagicMock,
        mock_test_conn: AsyncMock,
    ):
        """Should return empty tools_discovered when validation fails."""
        mock_locations.return_value = [_fake_location()]
        mock_resolve_installer.return_value = _mock_installer()
        mock_test_conn.return_value = _failed_connection_result()

        ctx = _make_ctx()
        result = await configure_server(
            server_name="s",
            package_identifier="p",
            ctx=ctx,
            clients="claude_code",
        )

        assert result["tools_discovered"] == []

    @patch("mcp_tap.tools.configure.test_server_connection")
    @patch("mcp_tap.tools.configure.write_server_config")
    @patch("mcp_tap.tools.configure.resolve_installer")
    @patch("mcp_tap.tools.configure.resolve_config_locations")
    async def test_validation_failure_message_mentions_warning(
        self,
        mock_locations: MagicMock,
        mock_resolve_installer: AsyncMock,
        mock_write: MagicMock,
        mock_test_conn: AsyncMock,
    ):
        """Should include validation warning in the message."""
        mock_locations.return_value = [_fake_location()]
        mock_resolve_installer.return_value = _mock_installer()
        mock_test_conn.return_value = _failed_connection_result(error="Connection refused")

        ctx = _make_ctx()
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

    @patch("mcp_tap.tools.configure.test_server_connection")
    @patch("mcp_tap.tools.configure.write_server_config")
    @patch("mcp_tap.tools.configure.resolve_installer")
    @patch("mcp_tap.tools.configure.resolve_config_locations")
    async def test_multi_client_success(
        self,
        mock_locations: MagicMock,
        mock_resolve_installer: AsyncMock,
        mock_write: MagicMock,
        mock_test_conn: AsyncMock,
    ):
        """Should write config to all clients and return per-client results."""
        mock_locations.return_value = [
            _fake_location(MCPClient.CLAUDE_DESKTOP, "/a"),
            _fake_location(MCPClient.CURSOR, "/b"),
        ]
        mock_resolve_installer.return_value = _mock_installer()
        mock_test_conn.return_value = _ok_connection_result()

        ctx = _make_ctx()
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

    @patch("mcp_tap.tools.configure.test_server_connection")
    @patch("mcp_tap.tools.configure.write_server_config")
    @patch("mcp_tap.tools.configure.resolve_installer")
    @patch("mcp_tap.tools.configure.resolve_config_locations")
    async def test_multi_client_partial_failure(
        self,
        mock_locations: MagicMock,
        mock_resolve_installer: AsyncMock,
        mock_write: MagicMock,
        mock_test_conn: AsyncMock,
    ):
        """Should succeed overall even if one client config write fails."""
        mock_locations.return_value = [
            _fake_location(MCPClient.CLAUDE_DESKTOP, "/a"),
            _fake_location(MCPClient.CURSOR, "/b"),
        ]
        mock_resolve_installer.return_value = _mock_installer()
        mock_test_conn.return_value = _ok_connection_result()
        # Second write fails
        mock_write.side_effect = [None, ConfigWriteError("Permission denied")]

        ctx = _make_ctx()
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

    @patch("mcp_tap.tools.configure.test_server_connection")
    @patch("mcp_tap.tools.configure.write_server_config")
    @patch("mcp_tap.tools.configure.resolve_installer")
    @patch("mcp_tap.tools.configure.resolve_config_locations")
    async def test_multi_client_message_lists_clients(
        self,
        mock_locations: MagicMock,
        mock_resolve_installer: AsyncMock,
        mock_write: MagicMock,
        mock_test_conn: AsyncMock,
    ):
        """Should mention which clients were configured in the message."""
        mock_locations.return_value = [
            _fake_location(MCPClient.CLAUDE_DESKTOP, "/a"),
            _fake_location(MCPClient.CURSOR, "/b"),
        ]
        mock_resolve_installer.return_value = _mock_installer()
        mock_test_conn.return_value = _ok_connection_result()

        ctx = _make_ctx()
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

    @patch("mcp_tap.tools.configure.test_server_connection")
    @patch("mcp_tap.tools.configure.write_server_config")
    @patch("mcp_tap.tools.configure.resolve_installer")
    @patch("mcp_tap.tools.configure.resolve_config_locations")
    async def test_project_scope_passes_params(
        self,
        mock_locations: MagicMock,
        mock_resolve_installer: AsyncMock,
        mock_write: MagicMock,
        mock_test_conn: AsyncMock,
    ):
        """Should pass scope and project_path to resolve_config_locations."""
        mock_locations.return_value = [
            _fake_location(MCPClient.CURSOR, "/project/.cursor/mcp.json", scope="project")
        ]
        mock_resolve_installer.return_value = _mock_installer()
        mock_test_conn.return_value = _ok_connection_result()

        ctx = _make_ctx()
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

    @patch("mcp_tap.tools.configure.test_server_connection")
    @patch("mcp_tap.tools.configure.write_server_config")
    @patch("mcp_tap.tools.configure.resolve_installer")
    @patch("mcp_tap.tools.configure.resolve_config_locations")
    async def test_env_vars_parsed_into_config(
        self,
        mock_locations: MagicMock,
        mock_resolve_installer: AsyncMock,
        mock_write: MagicMock,
        mock_test_conn: AsyncMock,
    ):
        """Should parse comma-separated KEY=VALUE pairs into env dict."""
        mock_locations.return_value = [_fake_location()]
        mock_resolve_installer.return_value = _mock_installer()
        mock_test_conn.return_value = _ok_connection_result()

        ctx = _make_ctx()
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

    @patch("mcp_tap.tools.configure.test_server_connection")
    @patch("mcp_tap.tools.configure.write_server_config")
    @patch("mcp_tap.tools.configure.resolve_installer")
    @patch("mcp_tap.tools.configure.resolve_config_locations")
    async def test_empty_env_vars_no_env_in_config(
        self,
        mock_locations: MagicMock,
        mock_resolve_installer: AsyncMock,
        mock_write: MagicMock,
        mock_test_conn: AsyncMock,
    ):
        """Should not include env in config_written when env_vars is empty."""
        mock_locations.return_value = [_fake_location()]
        mock_resolve_installer.return_value = _mock_installer()
        mock_test_conn.return_value = _ok_connection_result()

        ctx = _make_ctx()
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

    @patch("mcp_tap.tools.configure.test_server_connection")
    @patch("mcp_tap.tools.configure.write_server_config")
    @patch("mcp_tap.tools.configure.resolve_installer")
    @patch("mcp_tap.tools.configure.resolve_config_locations")
    async def test_config_write_error_returns_mcptap_error(
        self,
        mock_locations: MagicMock,
        mock_resolve_installer: AsyncMock,
        mock_write: MagicMock,
        mock_test_conn: AsyncMock,
    ):
        """Should handle ConfigWriteError (server already exists)."""
        mock_locations.return_value = [_fake_location()]
        mock_resolve_installer.return_value = _mock_installer()
        mock_write.side_effect = ConfigWriteError("Server 'x' already exists")

        ctx = _make_ctx()
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

    @patch("mcp_tap.tools.configure.test_server_connection")
    @patch("mcp_tap.tools.configure.write_server_config")
    @patch("mcp_tap.tools.configure.resolve_installer")
    @patch("mcp_tap.tools.configure.resolve_config_locations")
    async def test_pypi_registry_resolved(
        self,
        mock_locations: MagicMock,
        mock_resolve_installer: AsyncMock,
        mock_write: MagicMock,
        mock_test_conn: AsyncMock,
    ):
        """Should pass pypi RegistryType to resolve_installer."""
        mock_locations.return_value = [_fake_location()]
        installer = _mock_installer(command="uvx", args=["some-mcp-server"])
        mock_resolve_installer.return_value = installer
        mock_test_conn.return_value = _ok_connection_result()

        ctx = _make_ctx()
        result = await configure_server(
            server_name="pypi-server",
            package_identifier="some-mcp-server",
            ctx=ctx,
            clients="claude_code",
            registry_type="pypi",
        )

        mock_resolve_installer.assert_awaited_once()
        call_args = mock_resolve_installer.call_args[0]
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

    def test_pair_without_equals_ignored(self):
        result = _parse_env_vars("KEY=val,BROKEN_ENTRY,OTHER=x")
        assert result == {"KEY": "val", "OTHER": "x"}
