"""Pick the right installer for a package."""

from __future__ import annotations

from mcp_tap.errors import InstallerNotFoundError
from mcp_tap.installer.docker import DockerInstaller
from mcp_tap.installer.npm import NpmInstaller
from mcp_tap.installer.pip import PipInstaller
from mcp_tap.models import RegistryType

PackageInstaller = NpmInstaller | PipInstaller | DockerInstaller

_INSTALLERS: dict[RegistryType, type] = {
    RegistryType.NPM: NpmInstaller,
    RegistryType.PYPI: PipInstaller,
    RegistryType.OCI: DockerInstaller,
}

_INSTALL_URLS: dict[RegistryType, str] = {
    RegistryType.NPM: "https://nodejs.org/",
    RegistryType.PYPI: "https://docs.astral.sh/uv/getting-started/installation/",
    RegistryType.OCI: "https://docs.docker.com/get-docker/",
}


async def resolve_installer(registry_type: RegistryType | str) -> PackageInstaller:
    """Resolve the appropriate installer for a registry type.

    Checks that the underlying package manager is actually available.
    """
    rt = RegistryType(registry_type) if isinstance(registry_type, str) else registry_type

    installer_cls = _INSTALLERS.get(rt)
    if installer_cls is None:
        raise InstallerNotFoundError(f"Unsupported registry type: {rt}")

    installer = installer_cls()
    if not await installer.is_available():
        url = _INSTALL_URLS.get(rt, "")
        raise InstallerNotFoundError(
            f"Package manager for {rt.value} is not installed. Install it from {url}"
        )

    return installer
