"""Fetch repository metadata from the GitHub public API."""

from __future__ import annotations

import asyncio
import logging
import os
import re
import time

import httpx

from mcp_tap.models import MaturitySignals

logger = logging.getLogger(__name__)

# ─── In-memory LRU cache with TTL ──────────────────────────

_cache: dict[str, tuple[float, MaturitySignals]] = {}
_CACHE_TTL = 900  # 15 minutes


def _cache_get(key: str) -> MaturitySignals | None:
    if key in _cache:
        ts, signals = _cache[key]
        if time.monotonic() - ts < _CACHE_TTL:
            return signals
        del _cache[key]
    return None


def _cache_set(key: str, signals: MaturitySignals) -> None:
    _cache[key] = (time.monotonic(), signals)


def clear_cache() -> None:
    """Clear the in-memory cache and rate limit state. Primarily for testing."""
    global _rate_limit_reset
    _cache.clear()
    _rate_limit_reset = 0.0


# ─── Rate limit detection ──────────────────────────────────

_rate_limit_reset: float = 0.0


def _is_rate_limited() -> bool:
    return time.monotonic() < _rate_limit_reset


def _check_rate_limit(resp: httpx.Response) -> None:
    global _rate_limit_reset
    remaining = resp.headers.get("X-RateLimit-Remaining")
    if remaining is not None and int(remaining) == 0:
        reset_epoch = int(resp.headers.get("X-RateLimit-Reset", "0"))
        _rate_limit_reset = time.monotonic() + max(0, reset_epoch - time.time())
        logger.warning(
            "GitHub API rate limit exhausted. "
            "Set GITHUB_TOKEN env var for 5000 req/hr. "
            "Maturity scoring disabled until reset."
        )


# ─── Auth headers ──────────────────────────────────────────


def _github_headers() -> dict[str, str]:
    headers = {"Accept": "application/vnd.github+json"}
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


# ─── Concurrency control ──────────────────────────────────

_github_semaphore = asyncio.Semaphore(5)

# ─── URL parsing ───────────────────────────────────────────


def _parse_github_url(repository_url: str) -> tuple[str, str] | None:
    """Extract (owner, repo) from a GitHub URL.

    Returns None if the URL is not a GitHub repo.
    """
    m = re.match(r"https?://github\.com/([^/]+)/([^/]+?)(?:\.git)?(?:/.*)?$", repository_url)
    if m:
        return m.group(1), m.group(2)
    return None


# ─── Main fetch function ──────────────────────────────────


class DefaultGitHubMetadata:
    """Adapter for GitHubMetadataPort — holds httpx client."""

    def __init__(self, http_client: httpx.AsyncClient) -> None:
        self._http = http_client

    async def fetch_repo_metadata(self, repository_url: str) -> MaturitySignals | None:
        """Fetch repository metadata from GitHub's public API."""
        return await fetch_repo_metadata(repository_url, self._http)


async def fetch_repo_metadata(
    repository_url: str,
    http_client: httpx.AsyncClient,
) -> MaturitySignals | None:
    """Fetch repository metadata from GitHub's public API.

    Features: in-memory cache (15min TTL), rate limit detection,
    GITHUB_TOKEN support, concurrency limiting (5 concurrent requests).
    Returns None if the URL is not a GitHub repo or the API fails.
    """
    parsed = _parse_github_url(repository_url)
    if not parsed:
        return None

    owner, repo = parsed
    cache_key = f"{owner}/{repo}"

    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    if _is_rate_limited():
        return None

    api_url = f"https://api.github.com/repos/{owner}/{repo}"

    async with _github_semaphore:
        try:
            resp = await http_client.get(api_url, headers=_github_headers())
            _check_rate_limit(resp)

            if resp.status_code != 200:
                return None

            data = resp.json()
            signals = MaturitySignals(
                stars=data.get("stargazers_count"),
                forks=data.get("forks_count"),
                open_issues=data.get("open_issues_count"),
                last_commit_date=data.get("pushed_at"),
                last_release_date=None,  # Would need a separate API call
                is_official=False,  # Set by caller from registry data
                is_archived=data.get("archived", False),
                license=(data.get("license") or {}).get("spdx_id"),
            )

            _cache_set(cache_key, signals)
            return signals
        except httpx.HTTPError:
            return None
