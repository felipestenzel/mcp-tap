"""Tests for the AggregatedRegistry (registry/aggregator.py)."""

from __future__ import annotations

from unittest.mock import AsyncMock

from mcp_tap.models import PackageInfo, RegistryServer, RegistryType
from mcp_tap.registry.aggregator import AggregatedRegistry, _extract_github_key

# ── Helpers ───────────────────────────────────────────────────────


def make_official_server(
    name: str = "official/server",
    github_url: str = "https://github.com/org/repo",
    description: str = "Official server",
) -> RegistryServer:
    return RegistryServer(
        name=name,
        description=description,
        packages=[PackageInfo(registry_type=RegistryType.NPM, identifier="@org/server")],
        repository_url=github_url,
        source="official",
    )


def make_smithery_server(
    smithery_id: str = "org/server",
    github_url: str = "https://github.com/org/repo",
    description: str = "Smithery server",
    use_count: int = 42,
    verified: bool = True,
) -> RegistryServer:
    return RegistryServer(
        name=smithery_id,
        description=description,
        packages=[
            PackageInfo(registry_type=RegistryType.SMITHERY, identifier=smithery_id)
        ],
        repository_url=github_url,
        use_count=use_count,
        verified=verified,
        smithery_id=smithery_id,
        source="smithery",
    )


def _make_registry(
    official_results: list[RegistryServer] | Exception | None = None,
    smithery_results: list[RegistryServer] | Exception | None = None,
    official_get: RegistryServer | None = None,
    smithery_get: RegistryServer | None = None,
) -> AggregatedRegistry:
    """Build an AggregatedRegistry with mocked official and smithery ports."""
    official = AsyncMock()
    smithery = AsyncMock()

    if isinstance(official_results, Exception):
        official.search = AsyncMock(side_effect=official_results)
    else:
        official.search = AsyncMock(return_value=official_results or [])

    if isinstance(smithery_results, Exception):
        smithery.search = AsyncMock(side_effect=smithery_results)
    else:
        smithery.search = AsyncMock(return_value=smithery_results or [])

    official.get_server = AsyncMock(return_value=official_get)
    smithery.get_server = AsyncMock(return_value=smithery_get)

    return AggregatedRegistry(official=official, smithery=smithery)


# ═══════════════════════════════════════════════════════════════════
# TestAggregatedRegistrySearch
# ═══════════════════════════════════════════════════════════════════


class TestAggregatedRegistrySearch:
    """Tests for AggregatedRegistry.search."""

    async def test_searches_both_sources_in_parallel(self):
        """Should call both official.search and smithery.search with the same params."""
        agg = _make_registry(
            official_results=[make_official_server()],
            smithery_results=[make_smithery_server(github_url="https://smithery.ai/x")],
        )

        await agg.search("postgres", limit=15)

        agg.official.search.assert_awaited_once_with("postgres", limit=15)
        agg.smithery.search.assert_awaited_once_with("postgres", limit=15)

    async def test_respects_limit(self):
        """Should return at most `limit` results total."""
        officials = [
            make_official_server(name=f"off/{i}", github_url=f"https://github.com/org/off-{i}")
            for i in range(5)
        ]
        smitheries = [
            make_smithery_server(
                smithery_id=f"sm/{i}",
                github_url=f"https://smithery.ai/sm-{i}",
            )
            for i in range(5)
        ]
        agg = _make_registry(official_results=officials, smithery_results=smitheries)

        results = await agg.search("test", limit=3)

        assert len(results) <= 3

    async def test_official_failure_returns_smithery_results(self):
        """Should return Smithery results when official search raises exception."""
        sm = make_smithery_server(github_url="https://smithery.ai/neon")
        agg = _make_registry(
            official_results=RuntimeError("API down"),
            smithery_results=[sm],
        )

        results = await agg.search("postgres")

        assert len(results) == 1
        assert results[0].source == "smithery"

    async def test_smithery_failure_returns_official_results(self):
        """Should return official results when Smithery search raises exception."""
        off = make_official_server(github_url="https://github.com/org/pg")
        agg = _make_registry(
            official_results=[off],
            smithery_results=RuntimeError("Smithery down"),
        )

        results = await agg.search("postgres")

        assert len(results) == 1
        assert results[0].source == "official"

    async def test_both_fail_returns_empty_list(self):
        """Should return empty list when both registries fail."""
        agg = _make_registry(
            official_results=RuntimeError("official down"),
            smithery_results=RuntimeError("smithery down"),
        )

        results = await agg.search("postgres")

        assert results == []


# ═══════════════════════════════════════════════════════════════════
# TestAggregatedRegistryDeduplication
# ═══════════════════════════════════════════════════════════════════


class TestAggregatedRegistryDeduplication:
    """Tests for deduplication and merge logic in AggregatedRegistry.search."""

    async def test_deduplicates_by_github_url(self):
        """Should merge servers with the same GitHub repo URL into one result with source='both'."""
        off = make_official_server(
            name="io.github.org/pg-server",
            github_url="https://github.com/org/repo",
        )
        sm = make_smithery_server(
            smithery_id="org/pg-server",
            github_url="https://github.com/org/repo",
        )
        agg = _make_registry(official_results=[off], smithery_results=[sm])

        results = await agg.search("postgres")

        assert len(results) == 1
        assert results[0].source == "both"

    async def test_merges_smithery_signals_on_match(self):
        """Should keep official packages but merge Smithery use_count/verified/smithery_id."""
        off = make_official_server(
            name="io.github.org/pg-server",
            github_url="https://github.com/org/repo",
        )
        sm = make_smithery_server(
            smithery_id="org/pg-server",
            github_url="https://github.com/org/repo",
            use_count=999,
            verified=True,
        )
        agg = _make_registry(official_results=[off], smithery_results=[sm])

        results = await agg.search("postgres")

        merged = results[0]
        assert merged.source == "both"
        # Smithery signals merged
        assert merged.use_count == 999
        assert merged.verified is True
        assert merged.smithery_id == "org/pg-server"
        # Official packages preserved
        assert merged.packages[0].registry_type == RegistryType.NPM
        assert merged.packages[0].identifier == "@org/server"

    async def test_smithery_only_server_in_result(self):
        """Should include Smithery-only servers with source='smithery'."""
        sm = make_smithery_server(
            smithery_id="unique/server",
            github_url="https://smithery.ai/unique",
        )
        agg = _make_registry(official_results=[], smithery_results=[sm])

        results = await agg.search("test")

        assert len(results) == 1
        assert results[0].source == "smithery"

    async def test_official_only_server_in_result(self):
        """Should include official-only servers with source='official'."""
        off = make_official_server(
            name="official-only",
            github_url="https://github.com/org/only-official",
        )
        agg = _make_registry(official_results=[off], smithery_results=[])

        results = await agg.search("test")

        assert len(results) == 1
        assert results[0].source == "official"

    async def test_sort_order_both_before_official_before_smithery(self):
        """Should sort: source='both' first, then 'official', then 'smithery'."""
        off1 = make_official_server(
            name="off-only",
            github_url="https://github.com/org/off-only",
        )
        off2 = make_official_server(
            name="shared",
            github_url="https://github.com/org/shared",
        )
        sm_shared = make_smithery_server(
            smithery_id="shared",
            github_url="https://github.com/org/shared",
        )
        sm_only = make_smithery_server(
            smithery_id="sm-only",
            github_url="https://smithery.ai/sm-only",
        )
        agg = _make_registry(
            official_results=[off1, off2],
            smithery_results=[sm_shared, sm_only],
        )

        results = await agg.search("test")

        sources = [r.source for r in results]
        # "both" (merged shared), then "official" (off-only), then "smithery" (sm-only)
        assert sources == ["both", "official", "smithery"]

    async def test_no_duplicate_when_github_urls_differ(self):
        """Should NOT merge when GitHub URLs are different."""
        off = make_official_server(
            name="off/server",
            github_url="https://github.com/org/repo-a",
        )
        sm = make_smithery_server(
            smithery_id="sm/server",
            github_url="https://github.com/org/repo-b",
        )
        agg = _make_registry(official_results=[off], smithery_results=[sm])

        results = await agg.search("test")

        assert len(results) == 2
        sources = {r.source for r in results}
        assert "official" in sources
        assert "smithery" in sources


# ═══════════════════════════════════════════════════════════════════
# TestAggregatedRegistryGetServer
# ═══════════════════════════════════════════════════════════════════


class TestAggregatedRegistryGetServer:
    """Tests for AggregatedRegistry.get_server."""

    async def test_get_server_tries_official_first(self):
        """Should return official result and NOT call Smithery if official succeeds."""
        off = make_official_server(name="found")
        agg = _make_registry(official_get=off)

        result = await agg.get_server("found")

        assert result is not None
        assert result.name == "found"
        agg.official.get_server.assert_awaited_once_with("found")
        agg.smithery.get_server.assert_not_awaited()

    async def test_get_server_falls_back_to_smithery(self):
        """Should try Smithery when official returns None."""
        sm = make_smithery_server(smithery_id="neon", github_url="https://smithery.ai/neon")
        agg = _make_registry(official_get=None, smithery_get=sm)

        result = await agg.get_server("neon")

        assert result is not None
        assert result.name == "neon"
        agg.official.get_server.assert_awaited_once_with("neon")
        agg.smithery.get_server.assert_awaited_once_with("neon")

    async def test_get_server_returns_none_when_both_miss(self):
        """Should return None when both registries have no match."""
        agg = _make_registry(official_get=None, smithery_get=None)

        result = await agg.get_server("nonexistent")

        assert result is None
        agg.official.get_server.assert_awaited_once()
        agg.smithery.get_server.assert_awaited_once()


# ═══════════════════════════════════════════════════════════════════
# TestExtractGithubKey
# ═══════════════════════════════════════════════════════════════════


class TestExtractGithubKey:
    """Tests for the _extract_github_key pure function."""

    def test_extracts_owner_repo(self):
        """Should extract 'owner/repo' from a standard GitHub URL."""
        assert _extract_github_key("https://github.com/org/repo") == "org/repo"

    def test_handles_git_suffix(self):
        """Should strip .git suffix from URL."""
        assert _extract_github_key("https://github.com/org/repo.git") == "org/repo"

    def test_returns_none_for_non_github(self):
        """Should return None for non-GitHub URLs."""
        assert _extract_github_key("https://smithery.ai/servers/neon") is None

    def test_case_insensitive(self):
        """Should normalize result to lowercase."""
        assert _extract_github_key("https://github.com/ORG/Repo") == "org/repo"

    def test_handles_trailing_slash(self):
        """Should handle trailing path segments after owner/repo."""
        assert _extract_github_key("https://github.com/org/repo/tree/main") == "org/repo"

    def test_returns_none_for_empty_string(self):
        """Should return None for empty string."""
        assert _extract_github_key("") is None

    def test_handles_http_scheme(self):
        """Should work with http:// as well as https://."""
        assert _extract_github_key("http://github.com/org/repo") == "org/repo"
