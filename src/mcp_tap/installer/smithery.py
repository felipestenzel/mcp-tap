"""Smithery CLI installer -- installs MCP servers via @smithery/cli."""

from __future__ import annotations

import shutil
from dataclasses import dataclass

from mcp_tap.installer.subprocess import run_command
from mcp_tap.models import InstallResult


@dataclass(frozen=True, slots=True)
class SmitheryInstaller:
    """Installs MCP servers from Smithery using ``@smithery/cli``.

    Requires ``npx`` to be available on the system (same as NpmInstaller).
    The ``@smithery/cli`` package is fetched on-the-fly via ``npx -y``.
    """

    async def is_available(self) -> bool:
        """Check if npx is installed (required to run @smithery/cli)."""
        return shutil.which("npx") is not None

    async def install(self, identifier: str, version: str = "latest") -> InstallResult:
        """Verify the Smithery server is accessible via @smithery/cli.

        Runs ``npx -y @smithery/cli@latest install <identifier>`` with
        ``--client claude --config "{}"`` to skip interactive prompts.

        Args:
            identifier: Smithery server qualified name (e.g. ``"neon"``).
            version: Ignored for Smithery (always uses latest CLI).

        Returns:
            InstallResult indicating success or failure.
        """
        returncode, stdout, stderr = await run_command(
            [
                "npx",
                "-y",
                "@smithery/cli@latest",
                "install",
                identifier,
                "--client",
                "claude",
                "--config",
                "{}",
            ],
            timeout=90.0,
        )

        if returncode == 0:
            return InstallResult(
                success=True,
                package_identifier=identifier,
                install_method="smithery",
                message=f"Smithery server '{identifier}' installed via @smithery/cli.",
            )
        return InstallResult(
            success=False,
            package_identifier=identifier,
            install_method="smithery",
            message=f"Failed to install Smithery server '{identifier}': {stderr or stdout}",
            command_output=stderr or stdout,
        )

    async def uninstall(self, identifier: str) -> InstallResult:
        """Smithery CLI does not support uninstall -- return a no-op result.

        Args:
            identifier: Smithery server qualified name.

        Returns:
            InstallResult with success=True and an explanatory message.
        """
        return InstallResult(
            success=True,
            package_identifier=identifier,
            install_method="smithery",
            message=(
                f"Smithery CLI does not have an uninstall command. "
                f"Server '{identifier}' config was removed, but cached "
                f"packages may remain in the npx cache."
            ),
        )

    def build_server_command(self, identifier: str) -> tuple[str, list[str]]:
        """Return (command, args) for running a Smithery server.

        Args:
            identifier: Smithery server qualified name.

        Returns:
            Tuple of command and argument list for ``npx @smithery/cli run``.
        """
        return ("npx", ["-y", "@smithery/cli@latest", "run", identifier])
