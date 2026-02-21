"""AggregatedRegistry -- busca paralela em multiplas fontes de MCP servers."""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass, replace

from mcp_tap.models import RegistryServer
from mcp_tap.registry.base import RegistryClientPort

logger = logging.getLogger(__name__)

_GITHUB_URL_RE = re.compile(
    r"https?://github\.com/([^/]+)/([^/]+?)(?:\.git)?(?:/.*)?$",
    re.IGNORECASE,
)


def _extract_github_key(url: str) -> str | None:
    """Extract 'owner/repo' from a GitHub URL, or None if not GitHub."""
    m = _GITHUB_URL_RE.match(url)
    return f"{m.group(1)}/{m.group(2)}".lower() if m else None


def _sort_key(server: RegistryServer) -> int:
    """Sorting rank: ``both`` < ``official`` < ``smithery``."""
    order = {"both": 0, "official": 1, "smithery": 2}
    return order.get(server.source, 3)


@dataclass
class AggregatedRegistry:
    """Queries MCP Registry and Smithery in parallel, deduplicates, and merges signals.

    Implements ``RegistryClientPort`` so it's a drop-in replacement for
    ``RegistryClient`` in the AppContext.

    Args:
        official: The MCP Registry client adapter.
        smithery: The Smithery client adapter.
    """

    official: RegistryClientPort
    smithery: RegistryClientPort

    async def search(self, query: str, *, limit: int = 30) -> list[RegistryServer]:
        """Search both registries in parallel, deduplicate, and merge signals.

        Args:
            query: Free-text search term.
            limit: Maximum number of results to return.

        Returns:
            Deduplicated list of ``RegistryServer`` ordered by provenance
            (``both`` first, then ``official``, then ``smithery``).
        """
        official_task = self.official.search(query, limit=limit)
        smithery_task = self.smithery.search(query, limit=limit)

        results = await asyncio.gather(official_task, smithery_task, return_exceptions=True)

        official_results: list[RegistryServer] = []
        smithery_results: list[RegistryServer] = []

        if isinstance(results[0], BaseException):
            logger.warning("Official registry search failed: %s", results[0])
        else:
            official_results = results[0]

        if isinstance(results[1], BaseException):
            logger.warning("Smithery registry search failed: %s", results[1])
        else:
            smithery_results = results[1]

        merged = _merge_results(official_results, smithery_results)
        merged.sort(key=_sort_key)
        return merged[:limit]

    async def get_server(self, name: str) -> RegistryServer | None:
        """Fetch a server by name, trying official registry first.

        Args:
            name: Server identifier (registry name or Smithery qualifiedName).

        Returns:
            The ``RegistryServer`` if found in either source, or ``None``.
        """
        server = await self.official.get_server(name)
        if server is not None:
            return server
        return await self.smithery.get_server(name)


def _merge_results(
    official: list[RegistryServer],
    smithery: list[RegistryServer],
) -> list[RegistryServer]:
    """Deduplicate and merge servers from both sources.

    Deduplication keys (checked in order):
    1. GitHub URL (``owner/repo``) -- two servers sharing a repo are the same.
    2. Smithery ID match -- an official server whose ``name`` starts with
       ``ai.smithery/`` and matches a Smithery ``smithery_id``.

    When a server appears in both sources the official entry is kept as
    the base (it has installable ``packages``) and Smithery signals
    (``use_count``, ``verified``, ``smithery_id``) are merged in.
    """
    # Index official servers by GitHub key and by name.
    gh_to_official: dict[str, int] = {}
    name_to_official: dict[str, int] = {}

    for idx, server in enumerate(official):
        gh_key = _extract_github_key(server.repository_url)
        if gh_key:
            gh_to_official[gh_key] = idx
        name_to_official[server.name] = idx

    merged_indices: set[int] = set()  # official indices already merged
    result: list[RegistryServer] = []

    for sm_server in smithery:
        matched_idx: int | None = None

        # Match by GitHub URL
        sm_gh = _extract_github_key(sm_server.repository_url)
        if sm_gh and sm_gh in gh_to_official:
            matched_idx = gh_to_official[sm_gh]

        # Match by smithery_id in official name
        if matched_idx is None and sm_server.smithery_id:
            for off_name, off_idx in name_to_official.items():
                if off_name.startswith("ai.smithery/") and sm_server.smithery_id in off_name:
                    matched_idx = off_idx
                    break

        if matched_idx is not None and matched_idx not in merged_indices:
            # Merge: official base + Smithery signals
            off_server = official[matched_idx]
            result.append(
                replace(
                    off_server,
                    use_count=sm_server.use_count,
                    verified=sm_server.verified,
                    smithery_id=sm_server.smithery_id,
                    source="both",
                )
            )
            merged_indices.add(matched_idx)
        elif matched_idx is None:
            # Smithery-only server
            result.append(replace(sm_server, source="smithery"))

    # Add official-only servers (not merged)
    for idx, server in enumerate(official):
        if idx not in merged_indices:
            result.append(replace(server, source="official"))

    return result
