"""pip/uvx package installer."""

from __future__ import annotations

import shutil
from dataclasses import dataclass

from mcp_tap.installer.subprocess import run_command
from mcp_tap.models import InstallResult


@dataclass(frozen=True, slots=True)
class PipInstaller:
    """Installs Python packages. Prefers uvx (zero-install) for MCP servers."""

    async def is_available(self) -> bool:
        return shutil.which("uvx") is not None or shutil.which("pip") is not None

    async def install(self, identifier: str, version: str = "latest") -> InstallResult:
        """Install a Python package via uvx or pip."""
        if shutil.which("uvx"):
            pkg = f"{identifier}=={version}" if version != "latest" else identifier
            returncode, stdout, stderr = await run_command(
                ["uvx", pkg, "--help"],
                timeout=60.0,
            )
            method = "uvx"
        else:
            pkg = f"{identifier}=={version}" if version != "latest" else identifier
            returncode, stdout, stderr = await run_command(
                ["pip", "install", pkg],
                timeout=120.0,
            )
            method = "pip install"

        if returncode == 0:
            return InstallResult(
                success=True,
                package_identifier=identifier,
                install_method=method,
                message=f"Package {identifier} installed via {method}.",
            )
        return InstallResult(
            success=False,
            package_identifier=identifier,
            install_method=method,
            message=f"Failed to install {identifier}: {stderr or stdout}",
            command_output=stderr or stdout,
        )

    async def uninstall(self, identifier: str) -> InstallResult:
        returncode, stdout, stderr = await run_command(
            ["pip", "uninstall", "-y", identifier],
            timeout=30.0,
        )
        return InstallResult(
            success=returncode == 0,
            package_identifier=identifier,
            install_method="pip uninstall",
            message=f"Uninstalled {identifier}." if returncode == 0 else stderr,
        )

    def build_server_command(self, identifier: str) -> tuple[str, list[str]]:
        if shutil.which("uvx"):
            return ("uvx", [identifier])
        return ("python", ["-m", identifier])
