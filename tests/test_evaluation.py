"""Tests for evaluation module -- GitHub metadata and maturity scoring."""

from __future__ import annotations

import subprocess
import time
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from mcp_tap.evaluation.github import (
    _cache_get,
    _cache_set,
    _check_rate_limit,
    _github_headers,
    _is_rate_limited,
    _parse_github_url,
    _resolve_github_token,
    clear_cache,
    fetch_repo_metadata,
    github_runtime_status,
)
from mcp_tap.evaluation.scorer import score_maturity
from mcp_tap.models import MaturityScore, MaturitySignals


@pytest.fixture(autouse=True)
def _reset_runtime_state() -> None:
    """Ensure GitHub runtime/cache state is isolated between tests."""
    clear_cache()
    yield
    clear_cache()


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


# ─── In-memory cache tests (Fix C2) ──────────────────────────


class TestGitHubCacheGet:
    """Tests for _cache_get cache hit/miss and TTL behavior."""

    def test_cache_miss_returns_none(self) -> None:
        """Should return None for a key not in cache."""
        assert _cache_get("nonexistent/repo") is None

    def test_cache_hit_returns_signals(self) -> None:
        """Should return cached MaturitySignals for a known key."""
        signals = MaturitySignals(stars=42)
        _cache_set("test/repo", signals)

        result = _cache_get("test/repo")
        assert result is not None
        assert result.stars == 42

    def test_cache_expired_entry_returns_none(self) -> None:
        """Should return None when the cached entry is past TTL."""
        signals = MaturitySignals(stars=10)
        _cache_set("expired/repo", signals)

        # Patch time.monotonic to simulate TTL expiry
        original_mono = time.monotonic()
        with patch("mcp_tap.evaluation.github.time.monotonic", return_value=original_mono + 901):
            result = _cache_get("expired/repo")

        assert result is None


class TestGitHubCacheClear:
    """Tests for the clear_cache() function."""

    def test_clear_cache_removes_entries(self) -> None:
        """Should remove all cached entries."""
        _cache_set("a/b", MaturitySignals(stars=1))
        _cache_set("c/d", MaturitySignals(stars=2))

        clear_cache()

        assert _cache_get("a/b") is None
        assert _cache_get("c/d") is None

    def test_clear_cache_resets_rate_limit(self) -> None:
        """Should reset rate limit state so _is_rate_limited returns False."""
        # Simulate being rate limited
        import mcp_tap.evaluation.github as gh_mod

        gh_mod._rate_limit_reset = time.monotonic() + 9999

        assert _is_rate_limited() is True

        clear_cache()

        assert _is_rate_limited() is False


# ─── Rate limit tests (Fix C2) ──────────────────────────────


class TestGitHubRateLimit:
    """Tests for rate limit detection and recovery."""

    def test_not_rate_limited_by_default(self) -> None:
        """Should not be rate limited when _rate_limit_reset is 0."""
        assert _is_rate_limited() is False

    def test_rate_limit_detected_from_header(self) -> None:
        """Should detect rate limit when X-RateLimit-Remaining is 0."""
        resp = httpx.Response(
            200,
            headers={
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(int(time.time()) + 60),
            },
        )
        _check_rate_limit(resp)

        assert _is_rate_limited() is True

    def test_rate_limit_not_triggered_with_remaining(self) -> None:
        """Should not trigger rate limit when remaining > 0."""
        resp = httpx.Response(
            200,
            headers={"X-RateLimit-Remaining": "50"},
        )
        _check_rate_limit(resp)

        assert _is_rate_limited() is False

    def test_rate_limit_recovers_after_reset(self) -> None:
        """Should no longer be rate limited after reset time passes."""
        import mcp_tap.evaluation.github as gh_mod

        # Set rate limit to expire immediately
        gh_mod._rate_limit_reset = time.monotonic() - 1

        assert _is_rate_limited() is False


# ─── GitHub token header tests (Fix C2) ──────────────────────


class TestGitHubHeaders:
    """Tests for _github_headers with and without GITHUB_TOKEN."""

    def test_headers_without_token(self) -> None:
        """Should not include Authorization when GITHUB_TOKEN is not set."""
        with (
            patch.dict("os.environ", {}, clear=True),
            patch("mcp_tap.evaluation.github._resolve_gh_cli_token", return_value=None),
        ):
            headers = _github_headers()

        assert "Accept" in headers
        assert "Authorization" not in headers

    def test_headers_with_token(self) -> None:
        """Should include Bearer token when GITHUB_TOKEN is set."""
        with patch.dict("os.environ", {"GITHUB_TOKEN": "ghp_test123"}):
            headers = _github_headers()

        assert headers["Authorization"] == "Bearer ghp_test123"
        assert "Accept" in headers

    def test_accept_header_always_present(self) -> None:
        """Should always include the GitHub JSON accept header."""
        with (
            patch.dict("os.environ", {}, clear=True),
            patch("mcp_tap.evaluation.github._resolve_gh_cli_token", return_value=None),
        ):
            headers = _github_headers()

        assert headers["Accept"] == "application/vnd.github+json"


class TestGitHubTokenResolution:
    """Tests for token resolution order and runtime state introspection."""

    def test_env_token_has_priority_over_gh_cli(self) -> None:
        """Should prefer env token and skip gh fallback when GITHUB_TOKEN is set."""
        with (
            patch.dict("os.environ", {"GITHUB_TOKEN": "ghp_env"}, clear=True),
            patch("mcp_tap.evaluation.github.subprocess.run") as mock_run,
        ):
            token, source = _resolve_github_token()

        assert token == "ghp_env"
        assert source == "env"
        mock_run.assert_not_called()

    def test_gh_cli_fallback_used_when_env_missing(self) -> None:
        """Should resolve token from gh CLI when env token is absent."""
        completed = subprocess.CompletedProcess(
            args=["gh", "auth", "token"],
            returncode=0,
            stdout="ghp_cli_token\n",
            stderr="",
        )
        with (
            patch.dict("os.environ", {}, clear=True),
            patch("mcp_tap.evaluation.github.subprocess.run", return_value=completed),
        ):
            token, source = _resolve_github_token()

        assert token == "ghp_cli_token"
        assert source == "gh_cli"

    def test_runtime_status_reports_rate_limit_window(self) -> None:
        """Should expose active rate-limit state and reset seconds."""
        import mcp_tap.evaluation.github as gh_mod

        gh_mod._rate_limit_reset = time.monotonic() + 30

        with (
            patch.dict("os.environ", {}, clear=True),
            patch("mcp_tap.evaluation.github._resolve_gh_cli_token", return_value=None),
        ):
            status = github_runtime_status()

        assert status["has_auth"] is False
        assert status["auth_source"] == "none"
        assert status["rate_limited"] is True
        assert isinstance(status["rate_limit_reset_seconds"], int)
        assert status["rate_limit_reset_seconds"] > 0


# ─── Cache integration with fetch_repo_metadata (Fix C2) ─────


class TestFetchRepoMetadataCache:
    """Tests for caching behavior in fetch_repo_metadata."""

    async def test_cache_hit_skips_http_call(self) -> None:
        """Should return cached result without making HTTP request on cache hit."""
        signals = MaturitySignals(stars=100, forks=20)
        _cache_set("owner/repo", signals)

        client = AsyncMock(spec=httpx.AsyncClient)
        result = await fetch_repo_metadata("https://github.com/owner/repo", client)

        assert result is not None
        assert result.stars == 100
        # HTTP client should NOT have been called
        client.get.assert_not_called()

    async def test_cache_miss_makes_http_call(self) -> None:
        """Should make HTTP request when cache has no entry for the key."""
        data = {
            "stargazers_count": 500,
            "forks_count": 50,
            "open_issues_count": 5,
            "pushed_at": "2026-02-10T00:00:00Z",
            "archived": False,
            "license": {"spdx_id": "MIT"},
        }
        client = AsyncMock(spec=httpx.AsyncClient)
        client.get = AsyncMock(return_value=_mock_github_response(data))

        result = await fetch_repo_metadata("https://github.com/new/repo", client)

        assert result is not None
        assert result.stars == 500
        client.get.assert_called_once()

    async def test_second_call_uses_cache(self) -> None:
        """Should cache the result and use it for the second call."""
        data = {
            "stargazers_count": 300,
            "forks_count": 30,
            "open_issues_count": 3,
            "pushed_at": "2026-02-10T00:00:00Z",
            "archived": False,
            "license": None,
        }
        client = AsyncMock(spec=httpx.AsyncClient)
        client.get = AsyncMock(return_value=_mock_github_response(data))

        # First call -- HTTP request
        result1 = await fetch_repo_metadata("https://github.com/cached/repo", client)
        # Second call -- should use cache
        result2 = await fetch_repo_metadata("https://github.com/cached/repo", client)

        assert result1 is not None
        assert result2 is not None
        assert result1.stars == result2.stars
        # Only one HTTP call should have been made
        assert client.get.call_count == 1

    async def test_rate_limited_returns_none_without_http(self) -> None:
        """Should return None without HTTP call when rate limited."""
        import mcp_tap.evaluation.github as gh_mod

        gh_mod._rate_limit_reset = time.monotonic() + 9999

        client = AsyncMock(spec=httpx.AsyncClient)
        result = await fetch_repo_metadata("https://github.com/rate/limited", client)

        assert result is None
        client.get.assert_not_called()

    async def test_rate_limit_reset_allows_http_call(self) -> None:
        """Should make HTTP call again after rate limit resets."""
        data = {
            "stargazers_count": 10,
            "forks_count": 1,
            "open_issues_count": 0,
            "pushed_at": "2026-01-01T00:00:00Z",
            "archived": False,
            "license": None,
        }
        client = AsyncMock(spec=httpx.AsyncClient)
        client.get = AsyncMock(return_value=_mock_github_response(data))

        result = await fetch_repo_metadata("https://github.com/reset/allowed", client)

        assert result is not None
        client.get.assert_called_once()
