"""Docker image installer."""

from __future__ import annotations

import shutil
from dataclasses import dataclass

from mcp_tap.installer.subprocess import run_command
from mcp_tap.models import InstallResult


@dataclass(frozen=True, slots=True)
class DockerInstaller:
    """Installs MCP servers packaged as Docker/OCI images."""

    async def is_available(self) -> bool:
        return shutil.which("docker") is not None

    async def install(self, identifier: str, version: str = "latest") -> InstallResult:
        tag = f"{identifier}:{version}"
        returncode, stdout, stderr = await run_command(
            ["docker", "pull", tag],
            timeout=120.0,
        )

        if returncode == 0:
            return InstallResult(
                success=True,
                package_identifier=identifier,
                install_method="docker pull",
                message=f"Image {tag} pulled successfully.",
            )
        return InstallResult(
            success=False,
            package_identifier=identifier,
            install_method="docker pull",
            message=f"Failed to pull {tag}: {stderr or stdout}",
            command_output=stderr or stdout,
        )

    async def uninstall(self, identifier: str) -> InstallResult:
        returncode, _stdout, stderr = await run_command(
            ["docker", "rmi", identifier],
            timeout=30.0,
        )
        return InstallResult(
            success=returncode == 0,
            package_identifier=identifier,
            install_method="docker rmi",
            message=f"Removed image {identifier}." if returncode == 0 else stderr,
        )

    def build_server_command(self, identifier: str) -> tuple[str, list[str]]:
        return ("docker", ["run", "-i", "--rm", identifier])
