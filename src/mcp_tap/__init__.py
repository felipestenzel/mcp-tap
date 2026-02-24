"""mcp-tap: The last MCP server you install by hand."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _distribution_version

_LOCAL_VERSION_FALLBACK = "0.0.0+local"


def _resolve_version() -> str:
    """Resolve package version from installed metadata with deterministic fallback."""
    try:
        return _distribution_version("mcp-tap")
    except PackageNotFoundError:
        return _LOCAL_VERSION_FALLBACK


__version__ = _resolve_version()


def main() -> None:
    """Entry point for `mcp-tap` CLI."""
    from mcp_tap.server import mcp

    mcp.run(transport="stdio")
