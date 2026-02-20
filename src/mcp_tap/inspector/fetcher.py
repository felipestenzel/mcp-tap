"""Fetch README files from GitHub/GitLab repository URLs."""

from __future__ import annotations

import re

import httpx


def _github_raw_url(repo_url: str) -> str:
    """Convert a GitHub URL to a raw.githubusercontent.com README URL.

    Handles:
    - https://github.com/owner/repo
    - https://github.com/owner/repo/tree/main/packages/server-foo
    """
    # Monorepo path: /owner/repo/tree/branch/path
    m = re.match(
        r"https?://github\.com/([^/]+)/([^/]+)/tree/([^/]+)/(.+)",
        repo_url,
    )
    if m:
        owner, repo, branch, subpath = m.groups()
        return f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{subpath}/README.md"

    # Standard repo URL
    m = re.match(r"https?://github\.com/([^/]+)/([^/]+)(?:/.*)?$", repo_url)
    if m:
        owner, repo = m.groups()
        repo = repo.rstrip("/")
        return f"https://raw.githubusercontent.com/{owner}/{repo}/HEAD/README.md"

    return ""


def _gitlab_raw_url(repo_url: str) -> str:
    """Convert a GitLab URL to a raw README URL."""
    m = re.match(r"https?://gitlab\.com/([^/]+)/([^/]+)(?:/.*)?$", repo_url)
    if m:
        owner, repo = m.groups()
        repo = repo.rstrip("/")
        return f"https://gitlab.com/{owner}/{repo}/-/raw/main/README.md"
    return ""


class DefaultReadmeFetcher:
    """Adapter for ReadmeFetcherPort — holds httpx client."""

    def __init__(self, http_client: httpx.AsyncClient) -> None:
        self._http = http_client

    async def fetch_readme(self, repository_url: str) -> str | None:
        """Fetch README.md from a repository URL."""
        return await fetch_readme(repository_url, self._http)


async def fetch_readme(
    repository_url: str,
    http_client: httpx.AsyncClient,
) -> str | None:
    """Fetch README.md from a repository URL.

    Supports GitHub and GitLab URLs. Falls back to direct fetch for
    unrecognized URLs.

    Returns the raw markdown text, or None if not found/unreachable.
    """
    raw_url = ""

    if "github.com" in repository_url:
        raw_url = _github_raw_url(repository_url)
    elif "gitlab.com" in repository_url:
        raw_url = _gitlab_raw_url(repository_url)
    else:
        # Try appending /README.md as a heuristic
        raw_url = repository_url.rstrip("/") + "/README.md"

    if not raw_url:
        return None

    try:
        resp = await http_client.get(raw_url, follow_redirects=True)
        if resp.status_code == 200:
            return resp.text
        return None
    except httpx.HTTPError:
        return None
