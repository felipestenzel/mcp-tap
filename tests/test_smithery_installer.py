"""Tests for the Smithery CLI installer (installer/smithery.py)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from mcp_tap.installer.smithery import SmitheryInstaller

# ═══════════════════════════════════════════════════════════════════
# TestSmitheryInstallerAvailability
# ═══════════════════════════════════════════════════════════════════


class TestSmitheryInstallerAvailability:
    """Tests for SmitheryInstaller.is_available."""

    @patch("mcp_tap.installer.smithery.shutil.which", return_value="/usr/local/bin/npx")
    async def test_is_available_when_npx_found(self, _mock_which):
        """Should return True when npx is found on PATH."""
        installer = SmitheryInstaller()
        assert await installer.is_available() is True

    @patch("mcp_tap.installer.smithery.shutil.which", return_value=None)
    async def test_not_available_when_npx_missing(self, _mock_which):
        """Should return False when npx is not found on PATH."""
        installer = SmitheryInstaller()
        assert await installer.is_available() is False


# ═══════════════════════════════════════════════════════════════════
# TestSmitheryInstallerInstall
# ═══════════════════════════════════════════════════════════════════


class TestSmitheryInstallerInstall:
    """Tests for SmitheryInstaller.install."""

    @patch("mcp_tap.installer.smithery.run_command", new_callable=AsyncMock)
    async def test_install_success(self, mock_run):
        """Should return success=True when run_command returns exit code 0."""
        mock_run.return_value = (0, "ok", "")
        installer = SmitheryInstaller()

        result = await installer.install("neon")

        assert result.success is True
        assert result.install_method == "smithery"
        assert "neon" in result.message
        assert result.package_identifier == "neon"

    @patch("mcp_tap.installer.smithery.run_command", new_callable=AsyncMock)
    async def test_install_failure(self, mock_run):
        """Should return success=False with error message on non-zero exit."""
        mock_run.return_value = (1, "", "error: server not found")
        installer = SmitheryInstaller()

        result = await installer.install("bad-server")

        assert result.success is False
        assert "error: server not found" in result.message
        assert result.install_method == "smithery"
        assert result.command_output == "error: server not found"

    @patch("mcp_tap.installer.smithery.run_command", new_callable=AsyncMock)
    async def test_install_uses_smithery_cli_command(self, mock_run):
        """Should call run_command with npx @smithery/cli@latest install <identifier>."""
        mock_run.return_value = (0, "ok", "")
        installer = SmitheryInstaller()

        await installer.install("neon")

        cmd_args = mock_run.call_args[0][0]
        assert cmd_args[0] == "npx"
        assert "-y" in cmd_args
        assert "@smithery/cli@latest" in cmd_args
        assert "install" in cmd_args
        assert "neon" in cmd_args

    @patch("mcp_tap.installer.smithery.run_command", new_callable=AsyncMock)
    async def test_install_passes_client_and_config_flags(self, mock_run):
        """Should pass --client claude --config {} to skip interactive prompts."""
        mock_run.return_value = (0, "ok", "")
        installer = SmitheryInstaller()

        await installer.install("test-server")

        cmd_args = mock_run.call_args[0][0]
        assert "--client" in cmd_args
        assert "claude" in cmd_args
        assert "--config" in cmd_args
        assert "{}" in cmd_args

    @patch("mcp_tap.installer.smithery.run_command", new_callable=AsyncMock)
    async def test_install_uses_90s_timeout(self, mock_run):
        """Should pass timeout=90.0 to run_command."""
        mock_run.return_value = (0, "ok", "")
        installer = SmitheryInstaller()

        await installer.install("neon")

        _, kwargs = mock_run.call_args
        assert kwargs.get("timeout") == 90.0

    @patch("mcp_tap.installer.smithery.run_command", new_callable=AsyncMock)
    async def test_install_failure_uses_stdout_when_no_stderr(self, mock_run):
        """Should fall back to stdout in the error message when stderr is empty."""
        mock_run.return_value = (1, "stdout error details", "")
        installer = SmitheryInstaller()

        result = await installer.install("bad-server")

        assert result.success is False
        assert "stdout error details" in result.message
        assert result.command_output == "stdout error details"


# ═══════════════════════════════════════════════════════════════════
# TestSmitheryInstallerBuildCommand
# ═══════════════════════════════════════════════════════════════════


class TestSmitheryInstallerBuildCommand:
    """Tests for SmitheryInstaller.build_server_command."""

    def test_build_server_command(self):
        """Should return tuple of ('npx', [..., 'run', identifier])."""
        installer = SmitheryInstaller()

        cmd, args = installer.build_server_command("neon")

        assert cmd == "npx"
        assert args == ["-y", "@smithery/cli@latest", "run", "neon"]

    def test_build_server_command_with_complex_identifier(self):
        """Should pass through the identifier as-is."""
        installer = SmitheryInstaller()

        cmd, args = installer.build_server_command("org/complex-server-name")

        assert cmd == "npx"
        assert "org/complex-server-name" in args
        assert "run" in args


# ═══════════════════════════════════════════════════════════════════
# TestSmitheryInstallerUninstall
# ═══════════════════════════════════════════════════════════════════


class TestSmitheryInstallerUninstall:
    """Tests for SmitheryInstaller.uninstall."""

    async def test_uninstall_returns_success(self):
        """Should return success=True with explanatory message (no actual uninstall)."""
        installer = SmitheryInstaller()

        result = await installer.uninstall("neon")

        assert result.success is True
        assert result.install_method == "smithery"
        assert result.package_identifier == "neon"
        assert "does not have an uninstall command" in result.message
        assert "neon" in result.message

    async def test_uninstall_mentions_npx_cache(self):
        """Should mention that cached packages may remain in npx cache."""
        installer = SmitheryInstaller()

        result = await installer.uninstall("test-server")

        assert "npx cache" in result.message
