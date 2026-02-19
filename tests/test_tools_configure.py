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
from mcp_tap.tools.configure import _parse_env_vars, _resolve_client_location, configure_server

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
    exists: bool = True,
) -> ConfigLocation:
    return ConfigLocation(client=client, path=path, scope="user", exists=exists)


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
    @patch("mcp_tap.tools.configure._resolve_client_location")
    async def test_full_success_flow(
        self,
        mock_location: MagicMock,
        mock_resolve_installer: AsyncMock,
        mock_write: MagicMock,
        mock_test_conn: AsyncMock,
    ):
        """Should install, write config, validate, and return success."""
        mock_location.return_value = _fake_location()
        installer = _mock_installer()
        mock_resolve_installer.return_value = installer
        mock_test_conn.return_value = _ok_connection_result("pg-server")

        ctx = _make_ctx()
        result = await configure_server(
            server_name="pg-server",
            package_identifier="@modelcontextprotocol/server-postgres",
            ctx=ctx,
            client="claude_code",
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
    @patch("mcp_tap.tools.configure._resolve_client_location")
    async def test_config_written_contains_command_and_args(
        self,
        mock_location: MagicMock,
        mock_resolve_installer: AsyncMock,
        mock_write: MagicMock,
        mock_test_conn: AsyncMock,
    ):
        """Should include config_written dict with command, args, env."""
        mock_location.return_value = _fake_location()
        mock_resolve_installer.return_value = _mock_installer()
        mock_test_conn.return_value = _ok_connection_result()

        ctx = _make_ctx()
        result = await configure_server(
            server_name="test-server",
            package_identifier="test-pkg",
            ctx=ctx,
            client="claude_code",
            env_vars="KEY=value",
        )

        assert "config_written" in result
        assert result["config_written"]["command"] == "npx"
        assert result["config_written"]["args"] == ["-y", "test-pkg"]
        assert result["config_written"]["env"] == {"KEY": "value"}

    @patch("mcp_tap.tools.configure.test_server_connection")
    @patch("mcp_tap.tools.configure.write_server_config")
    @patch("mcp_tap.tools.configure.resolve_installer")
    @patch("mcp_tap.tools.configure._resolve_client_location")
    async def test_write_server_config_called_correctly(
        self,
        mock_location: MagicMock,
        mock_resolve_installer: AsyncMock,
        mock_write: MagicMock,
        mock_test_conn: AsyncMock,
    ):
        """Should call write_server_config with correct path and config."""
        loc = _fake_location(path="/home/user/.claude.json")
        mock_location.return_value = loc
        mock_resolve_installer.return_value = _mock_installer()
        mock_test_conn.return_value = _ok_connection_result()

        ctx = _make_ctx()
        await configure_server(
            server_name="my-server",
            package_identifier="pkg",
            ctx=ctx,
            client="claude_code",
        )

        mock_write.assert_called_once()
        call_args = mock_write.call_args
        assert call_args[0][0] == Path("/home/user/.claude.json")
        assert call_args[0][1] == "my-server"
        assert isinstance(call_args[0][2], ServerConfig)

    @patch("mcp_tap.tools.configure.test_server_connection")
    @patch("mcp_tap.tools.configure.write_server_config")
    @patch("mcp_tap.tools.configure.resolve_installer")
    @patch("mcp_tap.tools.configure._resolve_client_location")
    async def test_message_mentions_restart(
        self,
        mock_location: MagicMock,
        mock_resolve_installer: AsyncMock,
        mock_write: MagicMock,
        mock_test_conn: AsyncMock,
    ):
        """Should tell user to restart their MCP client."""
        mock_location.return_value = _fake_location()
        mock_resolve_installer.return_value = _mock_installer()
        mock_test_conn.return_value = _ok_connection_result()

        ctx = _make_ctx()
        result = await configure_server(
            server_name="s",
            package_identifier="p",
            ctx=ctx,
            client="claude_code",
        )

        assert "Restart" in result["message"]


# ═══════════════════════════════════════════════════════════════
# Install Failure Tests
# ═══════════════════════════════════════════════════════════════


class TestConfigureInstallFails:
    """Tests for when package installation fails."""

    @patch("mcp_tap.tools.configure.write_server_config")
    @patch("mcp_tap.tools.configure.resolve_installer")
    @patch("mcp_tap.tools.configure._resolve_client_location")
    async def test_install_failure_returns_error(
        self,
        mock_location: MagicMock,
        mock_resolve_installer: AsyncMock,
        mock_write: MagicMock,
    ):
        """Should return success=False when install fails."""
        mock_location.return_value = _fake_location()
        installer = _mock_installer(install_result=_failed_install_result("bad-pkg"))
        mock_resolve_installer.return_value = installer

        ctx = _make_ctx()
        result = await configure_server(
            server_name="bad-server",
            package_identifier="bad-pkg",
            ctx=ctx,
            client="claude_code",
        )

        assert result["success"] is False
        assert result["install_status"] == "failed"
        assert "installation failed" in result["message"].lower()

    @patch("mcp_tap.tools.configure.write_server_config")
    @patch("mcp_tap.tools.configure.resolve_installer")
    @patch("mcp_tap.tools.configure._resolve_client_location")
    async def test_install_failure_does_not_write_config(
        self,
        mock_location: MagicMock,
        mock_resolve_installer: AsyncMock,
        mock_write: MagicMock,
    ):
        """Should NOT write config when install fails."""
        mock_location.return_value = _fake_location()
        installer = _mock_installer(install_result=_failed_install_result())
        mock_resolve_installer.return_value = installer

        ctx = _make_ctx()
        await configure_server(
            server_name="s",
            package_identifier="p",
            ctx=ctx,
            client="claude_code",
        )

        mock_write.assert_not_called()

    @patch("mcp_tap.tools.configure.resolve_installer")
    @patch("mcp_tap.tools.configure._resolve_client_location")
    async def test_installer_not_found_returns_error(
        self,
        mock_location: MagicMock,
        mock_resolve_installer: AsyncMock,
    ):
        """Should return error when package manager is not available."""
        mock_location.return_value = _fake_location()
        mock_resolve_installer.side_effect = InstallerNotFoundError(
            "Package manager for npm is not installed."
        )

        ctx = _make_ctx()
        result = await configure_server(
            server_name="s",
            package_identifier="p",
            ctx=ctx,
            client="claude_code",
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
    @patch("mcp_tap.tools.configure._resolve_client_location")
    async def test_validation_failure_still_succeeds(
        self,
        mock_location: MagicMock,
        mock_resolve_installer: AsyncMock,
        mock_write: MagicMock,
        mock_test_conn: AsyncMock,
    ):
        """Should return success=True even when validation fails (config is written)."""
        mock_location.return_value = _fake_location()
        mock_resolve_installer.return_value = _mock_installer()
        mock_test_conn.return_value = _failed_connection_result("s", "timed out")

        ctx = _make_ctx()
        result = await configure_server(
            server_name="s",
            package_identifier="p",
            ctx=ctx,
            client="claude_code",
        )

        assert result["success"] is True
        assert result["validation_passed"] is False

    @patch("mcp_tap.tools.configure.test_server_connection")
    @patch("mcp_tap.tools.configure.write_server_config")
    @patch("mcp_tap.tools.configure.resolve_installer")
    @patch("mcp_tap.tools.configure._resolve_client_location")
    async def test_validation_failure_config_still_written(
        self,
        mock_location: MagicMock,
        mock_resolve_installer: AsyncMock,
        mock_write: MagicMock,
        mock_test_conn: AsyncMock,
    ):
        """Should still write config even when validation fails."""
        mock_location.return_value = _fake_location()
        mock_resolve_installer.return_value = _mock_installer()
        mock_test_conn.return_value = _failed_connection_result()

        ctx = _make_ctx()
        await configure_server(
            server_name="s",
            package_identifier="p",
            ctx=ctx,
            client="claude_code",
        )

        mock_write.assert_called_once()

    @patch("mcp_tap.tools.configure.test_server_connection")
    @patch("mcp_tap.tools.configure.write_server_config")
    @patch("mcp_tap.tools.configure.resolve_installer")
    @patch("mcp_tap.tools.configure._resolve_client_location")
    async def test_validation_failure_no_tools_discovered(
        self,
        mock_location: MagicMock,
        mock_resolve_installer: AsyncMock,
        mock_write: MagicMock,
        mock_test_conn: AsyncMock,
    ):
        """Should return empty tools_discovered when validation fails."""
        mock_location.return_value = _fake_location()
        mock_resolve_installer.return_value = _mock_installer()
        mock_test_conn.return_value = _failed_connection_result()

        ctx = _make_ctx()
        result = await configure_server(
            server_name="s",
            package_identifier="p",
            ctx=ctx,
            client="claude_code",
        )

        assert result["tools_discovered"] == []

    @patch("mcp_tap.tools.configure.test_server_connection")
    @patch("mcp_tap.tools.configure.write_server_config")
    @patch("mcp_tap.tools.configure.resolve_installer")
    @patch("mcp_tap.tools.configure._resolve_client_location")
    async def test_validation_failure_message_mentions_warning(
        self,
        mock_location: MagicMock,
        mock_resolve_installer: AsyncMock,
        mock_write: MagicMock,
        mock_test_conn: AsyncMock,
    ):
        """Should include validation warning in the message."""
        mock_location.return_value = _fake_location()
        mock_resolve_installer.return_value = _mock_installer()
        mock_test_conn.return_value = _failed_connection_result(error="Connection refused")

        ctx = _make_ctx()
        result = await configure_server(
            server_name="s",
            package_identifier="p",
            ctx=ctx,
            client="claude_code",
        )

        assert "Validation warning" in result["message"]
        assert "Connection refused" in result["message"]


# ═══════════════════════════════════════════════════════════════
# Result Field Tests
# ═══════════════════════════════════════════════════════════════


class TestConfigureResultFields:
    """Tests that ConfigureResult fields are properly populated."""

    @patch("mcp_tap.tools.configure.test_server_connection")
    @patch("mcp_tap.tools.configure.write_server_config")
    @patch("mcp_tap.tools.configure.resolve_installer")
    @patch("mcp_tap.tools.configure._resolve_client_location")
    async def test_install_status_field(
        self,
        mock_location: MagicMock,
        mock_resolve_installer: AsyncMock,
        mock_write: MagicMock,
        mock_test_conn: AsyncMock,
    ):
        """Should set install_status to 'installed' on success."""
        mock_location.return_value = _fake_location()
        mock_resolve_installer.return_value = _mock_installer()
        mock_test_conn.return_value = _ok_connection_result()

        ctx = _make_ctx()
        result = await configure_server(
            server_name="s",
            package_identifier="p",
            ctx=ctx,
            client="claude_code",
        )

        assert result["install_status"] == "installed"

    @patch("mcp_tap.tools.configure.test_server_connection")
    @patch("mcp_tap.tools.configure.write_server_config")
    @patch("mcp_tap.tools.configure.resolve_installer")
    @patch("mcp_tap.tools.configure._resolve_client_location")
    async def test_tools_discovered_field(
        self,
        mock_location: MagicMock,
        mock_resolve_installer: AsyncMock,
        mock_write: MagicMock,
        mock_test_conn: AsyncMock,
    ):
        """Should populate tools_discovered from validation result."""
        mock_location.return_value = _fake_location()
        mock_resolve_installer.return_value = _mock_installer()
        mock_test_conn.return_value = _ok_connection_result(
            tools=["read_query", "write_query"],
        )

        ctx = _make_ctx()
        result = await configure_server(
            server_name="s",
            package_identifier="p",
            ctx=ctx,
            client="claude_code",
        )

        assert result["tools_discovered"] == ["read_query", "write_query"]

    @patch("mcp_tap.tools.configure.test_server_connection")
    @patch("mcp_tap.tools.configure.write_server_config")
    @patch("mcp_tap.tools.configure.resolve_installer")
    @patch("mcp_tap.tools.configure._resolve_client_location")
    async def test_validation_passed_true(
        self,
        mock_location: MagicMock,
        mock_resolve_installer: AsyncMock,
        mock_write: MagicMock,
        mock_test_conn: AsyncMock,
    ):
        """Should set validation_passed=True when connection test succeeds."""
        mock_location.return_value = _fake_location()
        mock_resolve_installer.return_value = _mock_installer()
        mock_test_conn.return_value = _ok_connection_result()

        ctx = _make_ctx()
        result = await configure_server(
            server_name="s",
            package_identifier="p",
            ctx=ctx,
            client="claude_code",
        )

        assert result["validation_passed"] is True

    @patch("mcp_tap.tools.configure.test_server_connection")
    @patch("mcp_tap.tools.configure.write_server_config")
    @patch("mcp_tap.tools.configure.resolve_installer")
    @patch("mcp_tap.tools.configure._resolve_client_location")
    async def test_result_is_plain_dict(
        self,
        mock_location: MagicMock,
        mock_resolve_installer: AsyncMock,
        mock_write: MagicMock,
        mock_test_conn: AsyncMock,
    ):
        """Should return a plain dict (serialized via dataclasses.asdict)."""
        mock_location.return_value = _fake_location()
        mock_resolve_installer.return_value = _mock_installer()
        mock_test_conn.return_value = _ok_connection_result()

        ctx = _make_ctx()
        result = await configure_server(
            server_name="s",
            package_identifier="p",
            ctx=ctx,
            client="claude_code",
        )

        assert isinstance(result, dict)
        # Verify all expected keys are present
        expected_keys = {
            "success", "server_name", "config_file", "message",
            "config_written", "install_status", "tools_discovered",
            "validation_passed",
        }
        assert expected_keys == set(result.keys())


# ═══════════════════════════════════════════════════════════════
# No Client Detected Tests
# ═══════════════════════════════════════════════════════════════


class TestConfigureNoClient:
    """Tests for when no MCP client is detected."""

    @patch("mcp_tap.tools.configure._resolve_client_location", return_value=None)
    async def test_no_client_returns_error(self, _mock_location: MagicMock):
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
# Env Var Parsing Tests
# ═══════════════════════════════════════════════════════════════


class TestConfigureEnvVarParsing:
    """Tests for env var parsing in configure_server."""

    @patch("mcp_tap.tools.configure.test_server_connection")
    @patch("mcp_tap.tools.configure.write_server_config")
    @patch("mcp_tap.tools.configure.resolve_installer")
    @patch("mcp_tap.tools.configure._resolve_client_location")
    async def test_env_vars_parsed_into_config(
        self,
        mock_location: MagicMock,
        mock_resolve_installer: AsyncMock,
        mock_write: MagicMock,
        mock_test_conn: AsyncMock,
    ):
        """Should parse comma-separated KEY=VALUE pairs into env dict."""
        mock_location.return_value = _fake_location()
        mock_resolve_installer.return_value = _mock_installer()
        mock_test_conn.return_value = _ok_connection_result()

        ctx = _make_ctx()
        result = await configure_server(
            server_name="s",
            package_identifier="p",
            ctx=ctx,
            client="claude_code",
            env_vars="DB_URL=postgresql://localhost/db,API_KEY=sk-123",
        )

        written_env = result["config_written"].get("env", {})
        assert written_env["DB_URL"] == "postgresql://localhost/db"
        assert written_env["API_KEY"] == "sk-123"

    @patch("mcp_tap.tools.configure.test_server_connection")
    @patch("mcp_tap.tools.configure.write_server_config")
    @patch("mcp_tap.tools.configure.resolve_installer")
    @patch("mcp_tap.tools.configure._resolve_client_location")
    async def test_empty_env_vars_no_env_in_config(
        self,
        mock_location: MagicMock,
        mock_resolve_installer: AsyncMock,
        mock_write: MagicMock,
        mock_test_conn: AsyncMock,
    ):
        """Should not include env in config_written when env_vars is empty."""
        mock_location.return_value = _fake_location()
        mock_resolve_installer.return_value = _mock_installer()
        mock_test_conn.return_value = _ok_connection_result()

        ctx = _make_ctx()
        result = await configure_server(
            server_name="s",
            package_identifier="p",
            ctx=ctx,
            client="claude_code",
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
        "mcp_tap.tools.configure._resolve_client_location",
        side_effect=RuntimeError("unexpected"),
    )
    async def test_unexpected_error_returns_dict(self, _mock_location: MagicMock):
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
    @patch("mcp_tap.tools.configure._resolve_client_location")
    async def test_config_write_error_returns_mcptap_error(
        self,
        mock_location: MagicMock,
        mock_resolve_installer: AsyncMock,
        mock_write: MagicMock,
        mock_test_conn: AsyncMock,
    ):
        """Should handle ConfigWriteError (server already exists)."""
        mock_location.return_value = _fake_location()
        mock_resolve_installer.return_value = _mock_installer()
        mock_write.side_effect = ConfigWriteError("Server 'x' already exists")

        ctx = _make_ctx()
        result = await configure_server(
            server_name="x",
            package_identifier="p",
            ctx=ctx,
            client="claude_code",
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
    @patch("mcp_tap.tools.configure._resolve_client_location")
    async def test_pypi_registry_resolved(
        self,
        mock_location: MagicMock,
        mock_resolve_installer: AsyncMock,
        mock_write: MagicMock,
        mock_test_conn: AsyncMock,
    ):
        """Should pass pypi RegistryType to resolve_installer."""
        mock_location.return_value = _fake_location()
        installer = _mock_installer(command="uvx", args=["some-mcp-server"])
        mock_resolve_installer.return_value = installer
        mock_test_conn.return_value = _ok_connection_result()

        ctx = _make_ctx()
        result = await configure_server(
            server_name="pypi-server",
            package_identifier="some-mcp-server",
            ctx=ctx,
            client="claude_code",
            registry_type="pypi",
        )

        mock_resolve_installer.assert_awaited_once()
        # Verify the RegistryType.PYPI was passed
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
        """Should return empty dict for empty string."""
        assert _parse_env_vars("") == {}

    def test_single_pair(self):
        """Should parse a single KEY=VALUE pair."""
        assert _parse_env_vars("DB_URL=postgres://localhost") == {
            "DB_URL": "postgres://localhost",
        }

    def test_multiple_pairs(self):
        """Should parse comma-separated pairs."""
        result = _parse_env_vars("KEY1=val1,KEY2=val2,KEY3=val3")
        assert result == {"KEY1": "val1", "KEY2": "val2", "KEY3": "val3"}

    def test_strips_whitespace(self):
        """Should strip whitespace around keys and values."""
        result = _parse_env_vars("  KEY = value , OTHER = stuff  ")
        assert result == {"KEY": "value", "OTHER": "stuff"}

    def test_value_with_equals_sign(self):
        """Should handle values containing '=' (split on first only)."""
        result = _parse_env_vars("URL=postgres://host?opt=true")
        assert result == {"URL": "postgres://host?opt=true"}

    def test_pair_without_equals_ignored(self):
        """Should ignore entries without '=' sign."""
        result = _parse_env_vars("KEY=val,BROKEN_ENTRY,OTHER=x")
        assert result == {"KEY": "val", "OTHER": "x"}


# ═══════════════════════════════════════════════════════════════
# _resolve_client_location Unit Tests
# ═══════════════════════════════════════════════════════════════


class TestResolveClientLocation:
    """Tests for the _resolve_client_location helper function."""

    @patch("mcp_tap.tools.configure.resolve_config_path")
    def test_explicit_client(self, mock_resolve: MagicMock):
        """Should call resolve_config_path for an explicit client."""
        mock_resolve.return_value = _fake_location(client=MCPClient.CURSOR)

        result = _resolve_client_location("cursor")
        assert result is not None
        mock_resolve.assert_called_once_with(MCPClient.CURSOR)

    @patch("mcp_tap.tools.configure.detect_clients", return_value=[])
    def test_no_clients_returns_none(self, _mock_detect: MagicMock):
        """Should return None when no clients are detected."""
        result = _resolve_client_location("")
        assert result is None

    @patch("mcp_tap.tools.configure.detect_clients")
    def test_auto_detect_returns_first(self, mock_detect: MagicMock):
        """Should return the first detected client."""
        loc1 = _fake_location(client=MCPClient.CLAUDE_DESKTOP, path="/a")
        loc2 = _fake_location(client=MCPClient.CURSOR, path="/b")
        mock_detect.return_value = [loc1, loc2]

        result = _resolve_client_location("")
        assert result == loc1
