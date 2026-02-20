"""Package installer protocol -- one implementation per package manager."""

from __future__ import annotations

from typing import Protocol

from mcp_tap.models import InstallResult, RegistryType


class PackageInstaller(Protocol):
    """Protocol for package-manager-specific install logic."""

    async def is_available(self) -> bool:
        """Check if this package manager is installed on the system."""
        ...

    async def install(self, identifier: str, version: str = "latest") -> InstallResult:
        """Install/verify a package. Returns result even on failure (never raises)."""
        ...

    async def uninstall(self, identifier: str) -> InstallResult:
        """Uninstall a package."""
        ...

    def build_server_command(self, identifier: str) -> tuple[str, list[str]]:
        """Return (command, args) for running this package as an MCP server."""
        ...


class InstallerResolverPort(Protocol):
    """Port for resolving the appropriate package installer by registry type."""

    async def resolve_installer(self, registry_type: RegistryType | str) -> PackageInstaller:
        """Resolve and return a ready-to-use installer for the given registry type."""
        ...
