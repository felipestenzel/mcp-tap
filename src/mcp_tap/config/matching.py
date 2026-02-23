"""Canonical identity matching helpers for installed MCP servers."""

from __future__ import annotations

from collections.abc import Iterable

from mcp_tap.models import HttpServerConfig, InstalledServer, LockedServer

_HTTP_URL_PREFIXES = ("https://", "http://")


def is_http_package_identifier(package_identifier: str) -> bool:
    """Return True when a package identifier is an HTTP(S) URL."""
    return package_identifier.strip().startswith(_HTTP_URL_PREFIXES)


def extract_http_url(args: Iterable[str]) -> str | None:
    """Return the first HTTP URL found in args."""
    for arg in args:
        if str(arg).startswith(_HTTP_URL_PREFIXES):
            return str(arg)
    return None


def locked_http_url(locked: LockedServer) -> str | None:
    """Extract canonical HTTP URL from a lockfile entry."""
    pkg_id = locked.package_identifier.strip()
    if is_http_package_identifier(pkg_id):
        return pkg_id
    return extract_http_url(locked.config.args)


def installed_http_url(installed: InstalledServer) -> str | None:
    """Extract configured HTTP URL from an installed server entry."""
    if isinstance(installed.config, HttpServerConfig):
        return installed.config.url
    return extract_http_url(installed.config.args)


def is_locked_http_server(locked: LockedServer) -> bool:
    """Return True when lockfile entry describes an HTTP/SSE remote server."""
    if locked.registry_type in {"streamable-http", "http", "sse"}:
        return True
    return locked_http_url(locked) is not None


def installed_matches_package_identifier(
    installed: InstalledServer,
    package_identifier: str,
) -> bool:
    """Check if installed runtime config matches a canonical package identifier."""
    pkg_id = package_identifier.strip()
    if not pkg_id:
        return False

    if is_http_package_identifier(pkg_id):
        return installed_http_url(installed) == pkg_id

    if isinstance(installed.config, HttpServerConfig):
        return installed.config.url == pkg_id

    return installed.config.command == pkg_id or pkg_id in installed.config.args


def find_matching_installed_server(
    locked_name: str,
    locked: LockedServer,
    installed_servers: list[InstalledServer],
    used_installed_names: set[str] | None = None,
) -> InstalledServer | None:
    """Find installed server matching a lockfile entry by name, then canonical identity."""
    used = used_installed_names or set()

    by_name = next(
        (s for s in installed_servers if s.name == locked_name and s.name not in used),
        None,
    )
    if by_name is not None:
        return by_name

    pkg_id = locked.package_identifier.strip()
    if pkg_id:
        by_pkg = next(
            (
                s
                for s in installed_servers
                if s.name not in used and installed_matches_package_identifier(s, pkg_id)
            ),
            None,
        )
        if by_pkg is not None:
            return by_pkg

    url = locked_http_url(locked)
    if url:
        return next(
            (s for s in installed_servers if s.name not in used and installed_http_url(s) == url),
            None,
        )

    return None


def find_matching_locked_server(
    installed: InstalledServer,
    locked_servers: dict[str, LockedServer],
    used_locked_names: set[str] | None = None,
) -> tuple[str, LockedServer] | None:
    """Find lockfile entry matching an installed server by name, then canonical identity."""
    used = used_locked_names or set()

    if installed.name in locked_servers and installed.name not in used:
        return installed.name, locked_servers[installed.name]

    for locked_name, locked in locked_servers.items():
        if locked_name in used:
            continue
        if installed_matches_package_identifier(installed, locked.package_identifier):
            return locked_name, locked
        url = locked_http_url(locked)
        if url and installed_http_url(installed) == url:
            return locked_name, locked

    return None
