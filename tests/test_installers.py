"""Tests for the installer adapters and resolver."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from mcp_tap.errors import InstallerNotFoundError
from mcp_tap.installer.docker import DockerInstaller
from mcp_tap.installer.npm import NpmInstaller
from mcp_tap.installer.pip import PipInstaller
from mcp_tap.installer.resolver import resolve_installer
from mcp_tap.models import RegistryType

# ═══════════════════════════════════════════════════════════════════
# NpmInstaller
# ═══════════════════════════════════════════════════════════════════


class TestNpmInstaller:
    def test_build_server_command(self):
        installer = NpmInstaller()
        cmd, args = installer.build_server_command("@modelcontextprotocol/server-github")
        assert cmd == "npx"
        assert args == ["-y", "@modelcontextprotocol/server-github"]

    @patch("mcp_tap.installer.npm.shutil.which", return_value="/usr/local/bin/npx")
    async def test_is_available_true(self, _mock_which):
        assert await NpmInstaller().is_available() is True

    @patch("mcp_tap.installer.npm.shutil.which", return_value=None)
    async def test_is_available_false(self, _mock_which):
        assert await NpmInstaller().is_available() is False

    @patch("mcp_tap.installer.npm.run_command", new_callable=AsyncMock)
    async def test_install_success(self, mock_run):
        mock_run.return_value = (0, "OK", "")
        result = await NpmInstaller().install("my-package")
        assert result.success is True
        assert result.install_method == "npx"
        assert "my-package" in result.message

    @patch("mcp_tap.installer.npm.run_command", new_callable=AsyncMock)
    async def test_install_failure(self, mock_run):
        mock_run.return_value = (1, "", "not found")
        result = await NpmInstaller().install("bad-package")
        assert result.success is False
        assert "not found" in result.message

    @patch("mcp_tap.installer.npm.run_command", new_callable=AsyncMock)
    async def test_install_with_version(self, mock_run):
        mock_run.return_value = (0, "OK", "")
        await NpmInstaller().install("pkg", version="1.2.3")
        cmd_args = mock_run.call_args[0][0]
        assert "pkg@1.2.3" in cmd_args

    @patch("mcp_tap.installer.npm.run_command", new_callable=AsyncMock)
    async def test_uninstall(self, mock_run):
        mock_run.return_value = (0, "", "")
        result = await NpmInstaller().uninstall("my-package")
        assert result.success is True


# ═══════════════════════════════════════════════════════════════════
# PipInstaller
# ═══════════════════════════════════════════════════════════════════


class TestPipInstaller:
    def test_build_server_command_with_uvx(self):
        with patch("mcp_tap.installer.pip.shutil.which", return_value="/usr/bin/uvx"):
            cmd, args = PipInstaller().build_server_command("mcp-server-git")
            assert cmd == "uvx"
            assert args == ["mcp-server-git"]

    def test_build_server_command_without_uvx(self):
        with patch("mcp_tap.installer.pip.shutil.which", return_value=None):
            cmd, args = PipInstaller().build_server_command("mcp-server-git")
            assert cmd == "python"
            assert args == ["-m", "mcp-server-git"]

    @patch("mcp_tap.installer.pip.shutil.which")
    async def test_is_available_uvx(self, mock_which):
        mock_which.side_effect = lambda x: "/usr/bin/uvx" if x == "uvx" else None
        assert await PipInstaller().is_available() is True

    @patch("mcp_tap.installer.pip.shutil.which")
    async def test_is_available_pip_only(self, mock_which):
        mock_which.side_effect = lambda x: "/usr/bin/pip" if x == "pip" else None
        assert await PipInstaller().is_available() is True

    @patch("mcp_tap.installer.pip.shutil.which", return_value=None)
    async def test_is_available_neither(self, _mock):
        assert await PipInstaller().is_available() is False

    @patch("mcp_tap.installer.pip.shutil.which", return_value="/usr/bin/uvx")
    @patch("mcp_tap.installer.pip.run_command", new_callable=AsyncMock)
    async def test_install_via_uvx(self, mock_run, _mock_which):
        mock_run.return_value = (0, "OK", "")
        result = await PipInstaller().install("mcp-server-git")
        assert result.success is True
        assert result.install_method == "uvx"

    @patch("mcp_tap.installer.pip.shutil.which", return_value=None)
    @patch("mcp_tap.installer.pip.run_command", new_callable=AsyncMock)
    async def test_install_via_pip(self, mock_run, _mock_which):
        mock_run.return_value = (0, "OK", "")
        result = await PipInstaller().install("mcp-server-git")
        assert result.success is True
        assert result.install_method == "pip install"

    @patch("mcp_tap.installer.pip.shutil.which", return_value="/usr/bin/uvx")
    @patch("mcp_tap.installer.pip.run_command", new_callable=AsyncMock)
    async def test_install_failure(self, mock_run, _mock_which):
        mock_run.return_value = (1, "", "error: not found")
        result = await PipInstaller().install("bad-pkg")
        assert result.success is False

    @patch("mcp_tap.installer.pip.run_command", new_callable=AsyncMock)
    async def test_uninstall(self, mock_run):
        mock_run.return_value = (0, "", "")
        result = await PipInstaller().uninstall("mcp-server-git")
        assert result.success is True


# ═══════════════════════════════════════════════════════════════════
# DockerInstaller
# ═══════════════════════════════════════════════════════════════════


class TestDockerInstaller:
    def test_build_server_command(self):
        cmd, args = DockerInstaller().build_server_command("mcp/git-server")
        assert cmd == "docker"
        assert args == ["run", "-i", "--rm", "mcp/git-server"]

    @patch("mcp_tap.installer.docker.shutil.which", return_value="/usr/bin/docker")
    async def test_is_available_true(self, _mock):
        assert await DockerInstaller().is_available() is True

    @patch("mcp_tap.installer.docker.shutil.which", return_value=None)
    async def test_is_available_false(self, _mock):
        assert await DockerInstaller().is_available() is False

    @patch("mcp_tap.installer.docker.run_command", new_callable=AsyncMock)
    async def test_install_success(self, mock_run):
        mock_run.return_value = (0, "Pulling...", "")
        result = await DockerInstaller().install("mcp/server", version="1.0")
        assert result.success is True
        assert result.install_method == "docker pull"
        cmd_args = mock_run.call_args[0][0]
        assert "mcp/server:1.0" in cmd_args

    @patch("mcp_tap.installer.docker.run_command", new_callable=AsyncMock)
    async def test_install_failure(self, mock_run):
        mock_run.return_value = (1, "", "Error: not found")
        result = await DockerInstaller().install("bad/image")
        assert result.success is False

    @patch("mcp_tap.installer.docker.run_command", new_callable=AsyncMock)
    async def test_uninstall(self, mock_run):
        mock_run.return_value = (0, "", "")
        result = await DockerInstaller().uninstall("mcp/server")
        assert result.success is True
        assert result.install_method == "docker rmi"


# ═══════════════════════════════════════════════════════════════════
# resolve_installer
# ═══════════════════════════════════════════════════════════════════


class TestResolveInstaller:
    @patch("mcp_tap.installer.npm.shutil.which", return_value="/usr/bin/npx")
    async def test_resolve_npm(self, _mock):
        installer = await resolve_installer(RegistryType.NPM)
        assert isinstance(installer, NpmInstaller)

    @patch("mcp_tap.installer.pip.shutil.which")
    async def test_resolve_pypi(self, mock_which):
        mock_which.side_effect = lambda x: "/usr/bin/uvx" if x == "uvx" else None
        installer = await resolve_installer(RegistryType.PYPI)
        assert isinstance(installer, PipInstaller)

    @patch("mcp_tap.installer.docker.shutil.which", return_value="/usr/bin/docker")
    async def test_resolve_oci(self, _mock):
        installer = await resolve_installer(RegistryType.OCI)
        assert isinstance(installer, DockerInstaller)

    @patch("mcp_tap.installer.npm.shutil.which", return_value="/usr/bin/npx")
    async def test_resolve_from_string(self, _mock):
        installer = await resolve_installer("npm")
        assert isinstance(installer, NpmInstaller)

    @patch("mcp_tap.installer.npm.shutil.which", return_value=None)
    async def test_unavailable_package_manager(self, _mock):
        with pytest.raises(InstallerNotFoundError, match="not installed"):
            await resolve_installer(RegistryType.NPM)

    async def test_unsupported_registry_type(self):
        with pytest.raises((InstallerNotFoundError, ValueError)):
            await resolve_installer("unknown_registry")
