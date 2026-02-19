"""Fetch repository metadata from the GitHub public API."""

from __future__ import annotations

import re

import httpx

from mcp_tap.models import MaturitySignals


def _parse_github_url(repository_url: str) -> tuple[str, str] | None:
    """Extract (owner, repo) from a GitHub URL.

    Returns None if the URL is not a GitHub repo.
    """
    m = re.match(r"https?://github\.com/([^/]+)/([^/]+?)(?:\.git)?(?:/.*)?$", repository_url)
    if m:
        return m.group(1), m.group(2)
    return None


async def fetch_repo_metadata(
    repository_url: str,
    http_client: httpx.AsyncClient,
) -> MaturitySignals | None:
    """Fetch repository metadata from GitHub's public API.

    Uses unauthenticated requests (60 req/hour limit).
    Returns None if the URL is not a GitHub repo or the API fails.
    """
    parsed = _parse_github_url(repository_url)
    if not parsed:
        return None

    owner, repo = parsed
    api_url = f"https://api.github.com/repos/{owner}/{repo}"

    try:
        resp = await http_client.get(
            api_url,
            headers={"Accept": "application/vnd.github+json"},
        )
        if resp.status_code != 200:
            return None

        data = resp.json()
        return MaturitySignals(
            stars=data.get("stargazers_count"),
            forks=data.get("forks_count"),
            open_issues=data.get("open_issues_count"),
            last_commit_date=data.get("pushed_at"),
            last_release_date=None,  # Would need a separate API call
            is_official=False,  # Set by caller from registry data
            is_archived=data.get("archived", False),
            license=(data.get("license") or {}).get("spdx_id"),
        )
    except httpx.HTTPError:
        return None
