"""Shared test fixtures."""

from __future__ import annotations

import pytest

from mcp_tap.evaluation.github import clear_cache


@pytest.fixture(autouse=True)
def _clear_github_cache() -> None:
    """Clear the GitHub API cache before each test to prevent cross-test pollution."""
    clear_cache()
