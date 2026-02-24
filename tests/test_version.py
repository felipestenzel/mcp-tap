"""Tests for runtime package version resolution."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as distribution_version

import mcp_tap


class TestRuntimeVersion:
    """Version resolution should reflect installed package metadata."""

    def test_module_version_matches_installed_distribution(self):
        assert mcp_tap.__version__ == distribution_version("mcp-tap")

    def test_resolve_version_uses_deterministic_fallback_when_metadata_missing(self, monkeypatch):
        def _raise_package_not_found(_: str) -> str:
            raise PackageNotFoundError

        monkeypatch.setattr(mcp_tap, "_distribution_version", _raise_package_not_found)

        assert mcp_tap._resolve_version() == mcp_tap._LOCAL_VERSION_FALLBACK
