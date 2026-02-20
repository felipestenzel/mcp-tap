"""Ports: Maturity scoring and GitHub metadata fetching."""

from __future__ import annotations

from typing import Protocol

from mcp_tap.models import MaturityScore, MaturitySignals


class MaturityScorerPort(Protocol):
    """Port for computing maturity scores from collected signals."""

    def score_maturity(self, signals: MaturitySignals) -> MaturityScore:
        """Compute a maturity score from raw GitHub/registry signals."""
        ...


class GitHubMetadataPort(Protocol):
    """Port for fetching repository metadata from GitHub API."""

    async def fetch_repo_metadata(
        self,
        repository_url: str,
    ) -> MaturitySignals | None:
        """Fetch repository signals from GitHub's public API."""
        ...
