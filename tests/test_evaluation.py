"""Tests for evaluation module -- GitHub metadata and maturity scoring."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import httpx
import pytest

from mcp_tap.evaluation.github import _parse_github_url, fetch_repo_metadata
from mcp_tap.evaluation.scorer import score_maturity
from mcp_tap.models import MaturityScore, MaturitySignals

# ─── GitHub URL parsing ──────────────────────────────────────


class TestParseGitHubUrl:
    def test_standard_url(self) -> None:
        result = _parse_github_url("https://github.com/owner/repo")
        assert result == ("owner", "repo")

    def test_url_with_path(self) -> None:
        result = _parse_github_url("https://github.com/owner/repo/tree/main")
        assert result == ("owner", "repo")

    def test_url_with_git_suffix(self) -> None:
        result = _parse_github_url("https://github.com/owner/repo.git")
        assert result == ("owner", "repo")

    def test_non_github_returns_none(self) -> None:
        result = _parse_github_url("https://gitlab.com/owner/repo")
        assert result is None

    def test_invalid_url_returns_none(self) -> None:
        result = _parse_github_url("not-a-url")
        assert result is None


# ─── GitHub API fetch ────────────────────────────────────────


def _mock_github_response(data: dict, status_code: int = 200) -> httpx.Response:
    """Create a mock httpx.Response with JSON data."""
    import json

    return httpx.Response(
        status_code,
        content=json.dumps(data).encode(),
        headers={"content-type": "application/json"},
    )


class TestFetchRepoMetadata:
    async def test_successful_fetch(self) -> None:
        data = {
            "stargazers_count": 1500,
            "forks_count": 200,
            "open_issues_count": 15,
            "pushed_at": "2026-02-15T10:00:00Z",
            "archived": False,
            "license": {"spdx_id": "MIT"},
        }
        client = AsyncMock(spec=httpx.AsyncClient)
        client.get = AsyncMock(return_value=_mock_github_response(data))

        signals = await fetch_repo_metadata("https://github.com/owner/repo", client)
        assert signals is not None
        assert signals.stars == 1500
        assert signals.forks == 200
        assert signals.open_issues == 15
        assert signals.is_archived is False
        assert signals.license == "MIT"

    async def test_404_returns_none(self) -> None:
        client = AsyncMock(spec=httpx.AsyncClient)
        client.get = AsyncMock(return_value=httpx.Response(404))

        signals = await fetch_repo_metadata("https://github.com/owner/repo", client)
        assert signals is None

    async def test_rate_limited_returns_none(self) -> None:
        client = AsyncMock(spec=httpx.AsyncClient)
        client.get = AsyncMock(return_value=httpx.Response(403))

        signals = await fetch_repo_metadata("https://github.com/owner/repo", client)
        assert signals is None

    async def test_non_github_returns_none(self) -> None:
        client = AsyncMock(spec=httpx.AsyncClient)
        signals = await fetch_repo_metadata("https://gitlab.com/owner/repo", client)
        assert signals is None

    async def test_network_error_returns_none(self) -> None:
        client = AsyncMock(spec=httpx.AsyncClient)
        client.get = AsyncMock(side_effect=httpx.ConnectError("Connection failed"))

        signals = await fetch_repo_metadata("https://github.com/owner/repo", client)
        assert signals is None

    async def test_archived_repo(self) -> None:
        data = {
            "stargazers_count": 50,
            "forks_count": 5,
            "open_issues_count": 0,
            "pushed_at": "2024-01-01T00:00:00Z",
            "archived": True,
            "license": None,
        }
        client = AsyncMock(spec=httpx.AsyncClient)
        client.get = AsyncMock(return_value=_mock_github_response(data))

        signals = await fetch_repo_metadata("https://github.com/owner/repo", client)
        assert signals is not None
        assert signals.is_archived is True


# ─── Maturity scoring ────────────────────────────────────────


def _recent_date(days_ago: int = 5) -> str:
    """Return an ISO 8601 date string for N days ago."""
    return (datetime.now(tz=UTC) - timedelta(days=days_ago)).isoformat()


class TestScoreMaturity:
    def test_official_recent_high_stars(self) -> None:
        signals = MaturitySignals(
            stars=2300,
            forks=150,
            open_issues=10,
            last_commit_date=_recent_date(3),
            is_official=True,
        )
        score = score_maturity(signals)
        assert score.tier == "recommended"
        assert score.score >= 0.6
        assert "Official MCP server" in score.reasons

    def test_archived_repo_gets_avoid(self) -> None:
        signals = MaturitySignals(
            stars=500,
            is_archived=True,
            last_commit_date=_recent_date(400),
        )
        score = score_maturity(signals)
        assert score.tier == "avoid"
        assert score.score < 0.2
        assert score.warning is not None
        assert "archived" in score.warning.lower()

    def test_stale_repo_gets_caution_or_avoid(self) -> None:
        signals = MaturitySignals(
            stars=200,
            last_commit_date=_recent_date(200),
        )
        score = score_maturity(signals)
        assert score.tier in ("caution", "avoid")

    def test_recent_active_repo(self) -> None:
        signals = MaturitySignals(
            stars=100,
            last_commit_date=_recent_date(10),
        )
        score = score_maturity(signals)
        assert score.score >= 0.3

    def test_no_stars_no_commits(self) -> None:
        signals = MaturitySignals()
        score = score_maturity(signals)
        assert score.tier == "avoid"
        assert score.score == 0.0

    def test_high_open_issues_penalty(self) -> None:
        signals = MaturitySignals(
            stars=500,
            open_issues=80,
            last_commit_date=_recent_date(15),
        )
        score_with_issues = score_maturity(signals)

        signals_low = MaturitySignals(
            stars=500,
            open_issues=10,
            last_commit_date=_recent_date(15),
        )
        score_without = score_maturity(signals_low)
        assert score_with_issues.score < score_without.score

    def test_official_bonus_is_significant(self) -> None:
        base = MaturitySignals(stars=50, last_commit_date=_recent_date(60))
        official = MaturitySignals(stars=50, last_commit_date=_recent_date(60), is_official=True)
        assert score_maturity(official).score > score_maturity(base).score + 0.2

    def test_score_clamped_to_0_1(self) -> None:
        signals = MaturitySignals(
            stars=100000,
            is_official=True,
            last_commit_date=_recent_date(1),
        )
        score = score_maturity(signals)
        assert 0.0 <= score.score <= 1.0

    def test_license_in_reasons(self) -> None:
        signals = MaturitySignals(license="MIT")
        score = score_maturity(signals)
        assert any("MIT" in r for r in score.reasons)


# ─── Model validation ────────────────────────────────────────


class TestModels:
    def test_maturity_signals_frozen(self) -> None:
        s = MaturitySignals(stars=10)
        with pytest.raises(AttributeError):
            s.stars = 20  # type: ignore[misc]

    def test_maturity_score_frozen(self) -> None:
        s = MaturityScore(score=0.5, tier="acceptable")
        with pytest.raises(AttributeError):
            s.score = 0.9  # type: ignore[misc]
