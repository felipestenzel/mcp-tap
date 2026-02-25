"""Fetch repository metadata from the GitHub public API."""

from __future__ import annotations

import asyncio
import logging
import os
import re
import subprocess
import time

import httpx

from mcp_tap.models import MaturitySignals

logger = logging.getLogger(__name__)

# ─── In-memory LRU cache with TTL ──────────────────────────

_cache: dict[str, tuple[float, MaturitySignals]] = {}
_CACHE_TTL = 900  # 15 minutes

# ─── Runtime state ─────────────────────────────────────────

_rate_limit_reset: float = 0.0
_token_resolved: bool = False
_resolved_token: str | None = None
_resolved_token_source: str = "none"  # env | gh_cli | none

_logged_no_token_hint: bool = False
_logged_gh_cli_auth_hint: bool = False
_logged_rate_limit_hint: bool = False


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
    """Clear in-memory cache plus auth/rate-limit runtime state (primarily for tests)."""
    global _logged_gh_cli_auth_hint
    global _logged_no_token_hint
    global _logged_rate_limit_hint
    global _rate_limit_reset
    global _resolved_token
    global _resolved_token_source
    global _token_resolved

    _cache.clear()
    _rate_limit_reset = 0.0
    _token_resolved = False
    _resolved_token = None
    _resolved_token_source = "none"
    _logged_no_token_hint = False
    _logged_gh_cli_auth_hint = False
    _logged_rate_limit_hint = False


# ─── Rate limit detection ──────────────────────────────────


def _is_rate_limited() -> bool:
    return time.monotonic() < _rate_limit_reset


def _check_rate_limit(resp: httpx.Response) -> None:
    """Update local rate-limit gate and emit a single clear warning message."""
    global _logged_rate_limit_hint
    global _rate_limit_reset

    remaining = resp.headers.get("X-RateLimit-Remaining")
    if remaining is None:
        return
    try:
        remaining_value = int(remaining)
    except ValueError:
        return
    if remaining_value != 0:
        return

    reset_epoch = int(resp.headers.get("X-RateLimit-Reset", "0"))
    _rate_limit_reset = time.monotonic() + max(0, reset_epoch - time.time())

    if _logged_rate_limit_hint:
        return
    _, source = _resolve_github_token()
    source_hint = (
        "env GITHUB_TOKEN"
        if source == "env"
        else "gh auth token"
        if source == "gh_cli"
        else "no auth token"
    )
    logger.warning(
        "GitHub API rate limit exhausted (%s). Maturity scoring degraded until reset.",
        source_hint,
    )
    _logged_rate_limit_hint = True


# ─── Auth resolution ───────────────────────────────────────


def _github_headers() -> dict[str, str]:
    headers = {"Accept": "application/vnd.github+json"}
    token, _ = _resolve_github_token()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _resolve_github_token() -> tuple[str | None, str]:
    """Resolve auth token: env first, then `gh auth token` fallback."""
    global _logged_gh_cli_auth_hint
    global _logged_no_token_hint
    global _resolved_token
    global _resolved_token_source
    global _token_resolved

    env_token = os.environ.get("GITHUB_TOKEN", "").strip()
    if env_token:
        _token_resolved = True
        _resolved_token = env_token
        _resolved_token_source = "env"
        return env_token, "env"

    if _token_resolved:
        return _resolved_token, _resolved_token_source

    _token_resolved = True
    gh_token = _resolve_gh_cli_token()
    if gh_token:
        _resolved_token = gh_token
        _resolved_token_source = "gh_cli"
        if not _logged_gh_cli_auth_hint:
            logger.info("Using GitHub token from `gh auth token` fallback.")
            _logged_gh_cli_auth_hint = True
        return gh_token, "gh_cli"

    _resolved_token = None
    _resolved_token_source = "none"
    if not _logged_no_token_hint:
        logger.info(
            "No GitHub auth token found (checked GITHUB_TOKEN and `gh auth token`). "
            "Maturity scoring may degrade under rate limits."
        )
        _logged_no_token_hint = True
    return None, "none"


def _resolve_gh_cli_token() -> str | None:
    """Try to read a token from local GitHub CLI auth context."""
    try:
        completed = subprocess.run(
            ["gh", "auth", "token"],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None

    if completed.returncode != 0:
        return None
    token = completed.stdout.strip()
    return token or None


def github_runtime_status() -> dict[str, object]:
    """Return auth/rate-limit runtime state for search result annotations."""
    token, source = _resolve_github_token()
    rate_limited = _is_rate_limited()
    reset_seconds = int(max(0.0, _rate_limit_reset - time.monotonic())) if rate_limited else 0
    return {
        "has_auth": bool(token),
        "auth_source": source,
        "rate_limited": rate_limited,
        "rate_limit_reset_seconds": reset_seconds,
    }


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
    auth fallback (`GITHUB_TOKEN` -> `gh auth token`),
    concurrency limiting (5 concurrent requests).
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
