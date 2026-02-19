"""npm/npx package installer."""

from __future__ import annotations

import shutil
from dataclasses import dataclass

from mcp_tap.installer.subprocess import run_command
from mcp_tap.models import InstallResult


@dataclass(frozen=True, slots=True)
class NpmInstaller:
    """Installs npm packages. Uses npx (zero-install) for MCP servers."""

    async def is_available(self) -> bool:
        return shutil.which("npx") is not None

    async def install(self, identifier: str, version: str = "latest") -> InstallResult:
        """Verify the npm package exists and is downloadable via npx."""
        pkg = f"{identifier}@{version}" if version != "latest" else identifier
        returncode, stdout, stderr = await run_command(
            ["npx", "-y", "--package", pkg, "--", "--help"],
            timeout=60.0,
        )

        if returncode == 0:
            return InstallResult(
                success=True,
                package_identifier=identifier,
                install_method="npx",
                message=f"Package {identifier} verified and cached by npx.",
            )
        return InstallResult(
            success=False,
            package_identifier=identifier,
            install_method="npx",
            message=f"Failed to verify {identifier}: {stderr or stdout}",
            command_output=stderr or stdout,
        )

    async def uninstall(self, identifier: str) -> InstallResult:
        returncode, stdout, stderr = await run_command(
            ["npm", "cache", "clean", "--force"],
            timeout=30.0,
        )
        return InstallResult(
            success=returncode == 0,
            package_identifier=identifier,
            install_method="npm cache clean",
            message="npm cache cleared." if returncode == 0 else stderr,
        )

    def build_server_command(self, identifier: str) -> tuple[str, list[str]]:
        return ("npx", ["-y", identifier])
