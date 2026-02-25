"""Tests for the search_servers MCP tool (tools/search.py) -- context-aware features."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from mcp_tap.errors import RegistryError
from mcp_tap.models import (
    DetectedTechnology,
    EnvVarSpec,
    PackageInfo,
    ProjectProfile,
    RegistryServer,
    RegistryType,
    TechnologyCategory,
    Transport,
)
from mcp_tap.server import AppContext
from mcp_tap.tools.search import (
    _apply_composite_scoring,
    _apply_project_scoring,
    _build_search_queries,
    _scan_project_safe,
    search_servers,
)

# --- Fixture paths ---------------------------------------------------------

FIXTURES_DIR = Path(__file__).parent / "fixtures"
PYTHON_FASTAPI = FIXTURES_DIR / "python_fastapi_project"
EMPTY = FIXTURES_DIR / "empty_project"

# --- Helpers ---------------------------------------------------------------


def _make_ctx() -> MagicMock:
    """Build a mock Context with AppContext-shaped lifespan_context."""
    ctx = MagicMock()
    ctx.info = AsyncMock()
    ctx.error = AsyncMock()
    # Create an AppContext-like mock with all expected ports
    app = MagicMock(spec=AppContext)
    app.registry = MagicMock()
    app.github_metadata = MagicMock()
    # Default: fetch_repo_metadata returns None (no maturity data)
    app.github_metadata.fetch_repo_metadata = AsyncMock(return_value=None)
    ctx.request_context.lifespan_context = app
    return ctx


def _make_registry_server(
    name: str,
    description: str,
    identifier: str = "test-pkg",
    registry_type: RegistryType = RegistryType.NPM,
    transport: Transport = Transport.STDIO,
    is_official: bool = False,
) -> RegistryServer:
    return RegistryServer(
        name=name,
        description=description,
        version="1.0.0",
        repository_url="https://example.com",
        packages=[
            PackageInfo(
                registry_type=registry_type,
                identifier=identifier,
                version="1.0.0",
                transport=transport,
                environment_variables=[],
            ),
        ],
        is_official=is_official,
    )


def _profile_with_postgres() -> ProjectProfile:
    return ProjectProfile(
        path="/tmp/project",
        technologies=[
            DetectedTechnology(
                name="postgresql",
                category=TechnologyCategory.DATABASE,
                source_file="pyproject.toml",
            ),
            DetectedTechnology(
                name="python",
                category=TechnologyCategory.LANGUAGE,
                source_file="pyproject.toml",
            ),
        ],
    )


def _profile_empty() -> ProjectProfile:
    return ProjectProfile(path="/tmp/empty")


# ===================================================================
# search_servers -- Semantic Intent Routing
# ===================================================================


class TestSemanticIntentRouting:
    """Tests for semantic query expansion and intent-aware reranking."""

    def test_expands_error_monitoring_query_with_provider_hints(self):
        queries = _build_search_queries("error monitoring")

        assert queries[0] == "error monitoring"
        assert "error" in queries
        assert "sentry" in queries
        assert "datadog" in queries
        assert len(queries) <= 5

    async def test_reranks_provider_match_above_generic_candidate(self):
        ctx = _make_ctx()

        generic = RegistryServer(
            name="generic-monitoring-hub",
            description="General monitoring dashboards for teams.",
            version="1.0.0",
            repository_url="https://example.com/generic",
            packages=[
                PackageInfo(
                    registry_type=RegistryType.NPM,
                    identifier="generic-monitoring-hub",
                    version="1.0.0",
                    transport=Transport.STDIO,
                    environment_variables=[],
                )
            ],
            use_count=40,
            verified=True,
            source="smithery",
        )
        sentry = RegistryServer(
            name="sentry-mcp",
            description="Error tracking and alerting for production systems.",
            version="1.0.0",
            repository_url="https://example.com/sentry",
            packages=[
                PackageInfo(
                    registry_type=RegistryType.NPM,
                    identifier="sentry-mcp",
                    version="1.0.0",
                    transport=Transport.STDIO,
                    environment_variables=[],
                )
            ],
            use_count=2,
            verified=False,
            source="smithery",
        )

        async def _search_side_effect(query: str, *, limit: int = 30) -> list[RegistryServer]:
            if query in {"error monitoring", "error"}:
                return [generic]
            if query == "sentry":
                return [sentry]
            return []

        ctx.request_context.lifespan_context.registry.search = AsyncMock(
            side_effect=_search_side_effect
        )

        results = await search_servers("error monitoring", ctx, evaluate=False, limit=5)

        assert len(results) >= 2
        assert results[0]["name"] == "sentry-mcp"
        assert results[0]["intent_match_score"] > results[1]["intent_match_score"]
        assert "Provider hint match" in results[0]["intent_match_reason"]

    async def test_demotes_off_intent_candidates_for_error_monitoring(self):
        ctx = _make_ctx()

        off_intent = RegistryServer(
            name="supabase-tooling",
            description="Monitoring dashboards and database utilities for Supabase.",
            version="1.0.0",
            repository_url="https://example.com/supabase",
            packages=[
                PackageInfo(
                    registry_type=RegistryType.NPM,
                    identifier="supabase-tooling",
                    version="1.0.0",
                    transport=Transport.STDIO,
                    environment_variables=[],
                )
            ],
            use_count=9000,
            verified=True,
            source="smithery",
        )
        sentry = RegistryServer(
            name="sentry-mcp",
            description="Error tracking and alerting for production systems.",
            version="1.0.0",
            repository_url="https://example.com/sentry",
            packages=[
                PackageInfo(
                    registry_type=RegistryType.NPM,
                    identifier="sentry-mcp",
                    version="1.0.0",
                    transport=Transport.STDIO,
                    environment_variables=[],
                )
            ],
            use_count=3,
            verified=False,
            source="smithery",
        )
        datadog = RegistryServer(
            name="datadog-mcp",
            description="Error monitoring and incident alerting integrations.",
            version="1.0.0",
            repository_url="https://example.com/datadog",
            packages=[
                PackageInfo(
                    registry_type=RegistryType.NPM,
                    identifier="datadog-mcp",
                    version="1.0.0",
                    transport=Transport.STDIO,
                    environment_variables=[],
                )
            ],
            use_count=2,
            verified=False,
            source="smithery",
        )

        async def _search_side_effect(query: str, *, limit: int = 30) -> list[RegistryServer]:
            if query in {"error monitoring", "error"}:
                return [off_intent]
            if query == "sentry":
                return [sentry]
            if query == "datadog":
                return [datadog]
            return []

        ctx.request_context.lifespan_context.registry.search = AsyncMock(
            side_effect=_search_side_effect
        )

        results = await search_servers("error monitoring", ctx, evaluate=False, limit=5)
        names = [r["name"] for r in results]

        assert "sentry-mcp" in names[:2]
        assert "datadog-mcp" in names[:3]
        assert names.index("supabase-tooling") > names.index("sentry-mcp")
        supabase_result = next(r for r in results if r["name"] == "supabase-tooling")
        assert supabase_result["intent_gate_applied"] is True
        assert "Off-intent candidate" in supabase_result["intent_match_reason"]


# ===================================================================
# search_servers -- Backward Compatibility (no project_path)
# ===================================================================


class TestSearchBackwardCompatible:
    """Tests that search_servers still works without project_path."""

    async def test_returns_results_without_project_path(self):
        """Should return results without relevance fields when no project_path."""
        ctx = _make_ctx()
        ctx.request_context.lifespan_context.registry.search = AsyncMock(
            return_value=[
                _make_registry_server("pg-server", "PostgreSQL MCP server"),
                _make_registry_server("redis-server", "Redis cache MCP server"),
            ]
        )

        results = await search_servers("database", ctx)

        assert len(results) == 2
        assert results[0]["name"] == "pg-server"
        # No relevance field when project_path is not given
        assert "relevance" not in results[0]

    async def test_limit_parameter_works(self):
        """Should respect the limit parameter."""
        ctx = _make_ctx()
        ctx.request_context.lifespan_context.registry.search = AsyncMock(
            return_value=[
                _make_registry_server(f"server-{i}", f"Description {i}") for i in range(5)
            ]
        )

        results = await search_servers("test", ctx, limit=3)

        assert len(results) == 3

    async def test_empty_results(self):
        """Should return empty list when registry returns no results."""
        ctx = _make_ctx()
        ctx.request_context.lifespan_context.registry.search = AsyncMock(return_value=[])

        results = await search_servers("nonexistent", ctx)

        assert results == []

    async def test_marks_stale_cache_metadata_when_registry_used_fallback(self):
        """Should expose cache metadata when results come from offline fallback."""
        ctx = _make_ctx()
        registry = MagicMock()
        registry.search = AsyncMock(
            return_value=[_make_registry_server("pg-server", "PostgreSQL MCP server")]
        )
        registry.last_search_used_cache = True
        registry.last_search_cache_age_seconds = 42
        ctx.request_context.lifespan_context.registry = registry

        results = await search_servers("postgres", ctx, evaluate=False)

        assert len(results) == 1
        assert results[0]["cache_status"] == "stale_fallback"
        assert results[0]["cache_age_seconds"] == 42


# ===================================================================
# search_servers -- With project_path
# ===================================================================


class TestSearchWithProjectPath:
    """Tests for context-aware search when project_path is provided."""

    @patch("mcp_tap.tools.search._scan_project_safe")
    async def test_adds_relevance_field(self, mock_scan: AsyncMock):
        """Should add 'relevance' and 'match_reason' fields to results."""
        mock_scan.return_value = _profile_with_postgres()

        ctx = _make_ctx()
        ctx.request_context.lifespan_context.registry.search = AsyncMock(
            return_value=[
                _make_registry_server("pg-mcp", "PostgreSQL MCP server"),
            ]
        )

        results = await search_servers("database", ctx, project_path="/tmp/project")

        assert len(results) == 1
        assert "relevance" in results[0]
        assert "match_reason" in results[0]

    @patch("mcp_tap.tools.search._scan_project_safe")
    async def test_high_relevance_for_exact_match(self, mock_scan: AsyncMock):
        """Should tag exact tech match with 'high' relevance."""
        mock_scan.return_value = _profile_with_postgres()

        ctx = _make_ctx()
        ctx.request_context.lifespan_context.registry.search = AsyncMock(
            return_value=[
                _make_registry_server("postgresql-admin", "PostgreSQL admin tool"),
            ]
        )

        results = await search_servers("database", ctx, project_path="/tmp/project")

        assert results[0]["relevance"] == "high"
        assert "postgresql" in results[0]["match_reason"].lower()

    @patch("mcp_tap.tools.search._scan_project_safe")
    async def test_low_relevance_for_no_match(self, mock_scan: AsyncMock):
        """Should tag unrelated results with 'low' relevance."""
        mock_scan.return_value = _profile_with_postgres()

        ctx = _make_ctx()
        ctx.request_context.lifespan_context.registry.search = AsyncMock(
            return_value=[
                _make_registry_server("slack-bot", "Slack messaging integration"),
            ]
        )

        results = await search_servers("slack", ctx, project_path="/tmp/project")

        assert results[0]["relevance"] == "low"

    @patch("mcp_tap.tools.search._scan_project_safe")
    async def test_sorts_by_relevance(self, mock_scan: AsyncMock):
        """Should sort results: high first, then medium, then low."""
        mock_scan.return_value = _profile_with_postgres()

        ctx = _make_ctx()
        ctx.request_context.lifespan_context.registry.search = AsyncMock(
            return_value=[
                _make_registry_server("slack-notifier", "Send Slack messages"),
                _make_registry_server("db-backup", "A universal database backup tool"),
                _make_registry_server("postgresql-mcp", "PostgreSQL MCP server"),
            ]
        )

        results = await search_servers("all", ctx, project_path="/tmp/project")

        relevances = [r["relevance"] for r in results]
        # pg-mcp should be high, db-backup should be medium, slack should be low
        assert relevances[0] == "high"
        assert relevances[-1] == "low"

    @patch("mcp_tap.tools.search._scan_project_safe")
    async def test_scan_failure_still_returns_results(self, mock_scan: AsyncMock):
        """Should return results with 'low' relevance when scan fails."""
        mock_scan.return_value = None  # scan failed

        ctx = _make_ctx()
        ctx.request_context.lifespan_context.registry.search = AsyncMock(
            return_value=[
                _make_registry_server("pg-mcp", "PostgreSQL MCP server"),
            ]
        )

        results = await search_servers("pg", ctx, project_path="/bad/path")

        assert len(results) == 1
        assert results[0]["relevance"] == "low"
        assert results[0]["match_reason"] == ""


# ===================================================================
# _apply_project_scoring -- Unit Tests
# ===================================================================


class TestApplyProjectScoring:
    """Tests for the _apply_project_scoring helper."""

    def test_none_profile_adds_low_relevance(self):
        """Should add 'low' relevance to all results when profile is None."""
        results = [
            {"name": "server-a", "description": "Some server"},
            {"name": "server-b", "description": "Another server"},
        ]

        scored = _apply_project_scoring(results, None)

        assert all(r["relevance"] == "low" for r in scored)
        assert all(r["match_reason"] == "" for r in scored)

    def test_preserves_original_fields(self):
        """Should preserve all original dict fields in scored results."""
        results = [
            {
                "name": "pg-mcp",
                "description": "PostgreSQL",
                "version": "1.0",
                "is_official": True,
            },
        ]
        profile = _profile_with_postgres()

        scored = _apply_project_scoring(results, profile)

        assert scored[0]["version"] == "1.0"
        assert scored[0]["is_official"] is True
        assert "relevance" in scored[0]

    def test_stable_sort_within_same_relevance(self):
        """Should preserve original order within same relevance group."""
        results = [
            {"name": "first-pg", "description": "PostgreSQL tool 1"},
            {"name": "second-pg", "description": "PostgreSQL tool 2"},
        ]
        profile = _profile_with_postgres()

        scored = _apply_project_scoring(results, profile)

        # Both should be "high" relevance; original order preserved
        assert scored[0]["name"] == "first-pg"
        assert scored[1]["name"] == "second-pg"

    def test_empty_results_returns_empty(self):
        """Should return empty list when results list is empty."""
        scored = _apply_project_scoring([], _profile_with_postgres())
        assert scored == []


# ===================================================================
# _apply_composite_scoring -- Unit Tests
# ===================================================================


class TestApplyCompositeScoring:
    """Tests for deterministic ranking based on combined quality signals."""

    def test_adds_composite_fields(self):
        """Should annotate each result with composite score and breakdown."""
        results = [
            {
                "name": "postgres-mcp",
                "intent_match_score": 0.9,
                "intent_match_reason": "Provider hint match: sentry",
                "relevance": "high",
                "credential_status": "available",
                "maturity": {"score": 0.8},
                "verified": True,
                "use_count": 220,
            }
        ]

        ranked = _apply_composite_scoring(results)

        assert len(ranked) == 1
        assert "composite_score" in ranked[0]
        assert "composite_breakdown" in ranked[0]
        assert "intent" in ranked[0]["composite_breakdown"]["weights"]
        assert "intent_match_score" in ranked[0]["composite_breakdown"]["signals"]
        assert "intent_gate_applied" in ranked[0]["composite_breakdown"]["signals"]
        assert ranked[0]["composite_score"] > 0.0

    def test_sorts_by_composite_score(self):
        """Should rank stronger multi-signal candidates first."""
        results = [
            {
                "name": "candidate-low",
                "intent_match_score": 0.1,
                "relevance": "low",
                "credential_status": "missing",
                "maturity": {"score": 0.1},
                "verified": False,
                "use_count": 0,
            },
            {
                "name": "candidate-best",
                "intent_match_score": 0.95,
                "relevance": "high",
                "credential_status": "available",
                "maturity": {"score": 0.9},
                "verified": True,
                "use_count": 500,
            },
            {
                "name": "candidate-mid",
                "intent_match_score": 0.5,
                "relevance": "medium",
                "credential_status": "partial",
                "maturity": {"score": 0.6},
                "verified": False,
                "use_count": 20,
            },
        ]

        ranked = _apply_composite_scoring(results)
        names = [r["name"] for r in ranked]

        assert names == ["candidate-best", "candidate-mid", "candidate-low"]

    def test_intent_signal_can_outweigh_popularity_noise(self):
        """Should prioritize high intent match over generic but popular results."""
        results = [
            {
                "name": "generic-popular",
                "intent_match_score": 0.2,
                "relevance": "low",
                "credential_status": "none_required",
                "maturity": {"score": 0.2},
                "verified": True,
                "use_count": 5000,
            },
            {
                "name": "intent-specific",
                "intent_match_score": 0.95,
                "relevance": "low",
                "credential_status": "none_required",
                "maturity": {"score": 0.2},
                "verified": False,
                "use_count": 5,
            },
        ]

        ranked = _apply_composite_scoring(results)
        names = [r["name"] for r in ranked]

        assert names[0] == "intent-specific"

    def test_relevance_still_drives_order_when_other_signals_absent(self):
        """Should preserve high > medium > low when only relevance is present."""
        results = [
            {"name": "low-candidate", "relevance": "low"},
            {"name": "high-candidate", "relevance": "high"},
            {"name": "medium-candidate", "relevance": "medium"},
        ]

        ranked = _apply_composite_scoring(results)
        names = [r["name"] for r in ranked]

        assert names == ["high-candidate", "medium-candidate", "low-candidate"]


# ===================================================================
# search_servers -- Medium Relevance
# ===================================================================


class TestSearchMediumRelevance:
    """Tests for medium relevance scoring when project has a category match."""

    @patch("mcp_tap.tools.search._scan_project_safe")
    async def test_category_match_gives_medium(self, mock_scan: AsyncMock):
        """Should return 'medium' when project has DB tech and result mentions 'database'."""
        profile = ProjectProfile(
            path="/tmp/project",
            technologies=[
                DetectedTechnology(
                    name="mysql",
                    category=TechnologyCategory.DATABASE,
                    source_file="docker-compose.yml",
                ),
            ],
        )
        mock_scan.return_value = profile

        ctx = _make_ctx()
        ctx.request_context.lifespan_context.registry.search = AsyncMock(
            return_value=[
                # "mysql" is NOT in name or description, but "database" keyword IS
                _make_registry_server("data-browser", "Universal database management tool"),
            ]
        )

        results = await search_servers("data", ctx, project_path="/tmp/project")

        assert results[0]["relevance"] == "medium"
        assert "database" in results[0]["match_reason"].lower()


# ===================================================================
# search_servers -- Result Structure
# ===================================================================


class TestSearchResultStructure:
    """Tests for complete field-level result structure."""

    async def test_all_expected_fields_present(self):
        """Should include all SearchResult fields in each result dict."""
        ctx = _make_ctx()
        ctx.request_context.lifespan_context.registry.search = AsyncMock(
            return_value=[
                RegistryServer(
                    name="full-server",
                    description="Complete test server",
                    version="2.3.1",
                    repository_url="https://github.com/test/server",
                    packages=[
                        PackageInfo(
                            registry_type=RegistryType.PYPI,
                            identifier="full-server",
                            version="2.3.1",
                            transport=Transport.SSE,
                            environment_variables=[
                                EnvVarSpec(
                                    name="API_KEY",
                                    description="API key",
                                    is_required=True,
                                ),
                                EnvVarSpec(
                                    name="OPTIONAL_VAR",
                                    description="Optional",
                                    is_required=False,
                                ),
                            ],
                        ),
                    ],
                    is_official=True,
                    updated_at="2025-06-15",
                ),
            ]
        )

        results = await search_servers("full", ctx)

        assert len(results) == 1
        r = results[0]
        assert r["name"] == "full-server"
        assert r["description"] == "Complete test server"
        assert r["version"] == "2.3.1"
        assert r["registry_type"] == "pypi"
        assert r["package_identifier"] == "full-server"
        assert r["transport"] == "sse"
        assert r["is_official"] is True
        assert r["updated_at"] == "2025-06-15"
        assert r["repository_url"] == "https://github.com/test/server"
        # Only required env vars
        assert r["env_vars_required"] == ["API_KEY"]
        assert "composite_score" in r
        assert "composite_breakdown" in r

    async def test_remote_url_uses_transport_as_registry_type(self):
        """Should serialize URL-based remotes as streamable-http/sse instead of npm."""
        ctx = _make_ctx()
        ctx.request_context.lifespan_context.registry.search = AsyncMock(
            return_value=[
                _make_registry_server(
                    name="com.vercel/vercel-mcp",
                    description="Vercel MCP",
                    identifier="https://mcp.vercel.com",
                    registry_type=RegistryType.NPM,
                    transport=Transport.STREAMABLE_HTTP,
                    is_official=True,
                )
            ]
        )

        results = await search_servers("vercel", ctx)

        assert len(results) == 1
        assert results[0]["transport"] == "streamable-http"
        assert results[0]["registry_type"] == "streamable-http"


# ===================================================================
# _scan_project_safe -- Unit Tests
# ===================================================================


class TestScanProjectSafe:
    """Tests for the _scan_project_safe internal helper."""

    @patch("mcp_tap.scanner.detector.scan_project")
    async def test_returns_profile_on_success(self, mock_scan: AsyncMock):
        """Should return ProjectProfile when scan succeeds."""
        expected = _profile_with_postgres()
        mock_scan.return_value = expected

        result = await _scan_project_safe("/tmp/project")

        assert result == expected
        mock_scan.assert_awaited_once_with("/tmp/project")

    @patch(
        "mcp_tap.scanner.detector.scan_project",
        side_effect=Exception("scan failed"),
    )
    async def test_returns_none_on_failure(self, _mock_scan: AsyncMock):
        """Should return None when scan raises any exception."""
        result = await _scan_project_safe("/nonexistent")

        assert result is None


# ===================================================================
# search_servers -- Error Handling
# ===================================================================


class TestSearchErrorHandling:
    """Tests for error handling in search_servers."""

    async def test_unexpected_error_returns_error_dict(self):
        """Should return error dict for unexpected exceptions."""
        ctx = _make_ctx()
        ctx.request_context.lifespan_context.registry.search = AsyncMock(
            side_effect=RuntimeError("boom"),
        )

        results = await search_servers("test", ctx)

        assert len(results) == 1
        assert results[0]["success"] is False
        assert "Internal error" in results[0]["error"]
        ctx.error.assert_awaited_once()

    async def test_registry_error_returns_error_dict(self):
        """Should return error dict for RegistryError."""
        ctx = _make_ctx()
        ctx.request_context.lifespan_context.registry.search = AsyncMock(
            side_effect=RegistryError("API unreachable"),
        )

        results = await search_servers("test", ctx)

        assert len(results) == 1
        assert results[0]["success"] is False
        assert "API unreachable" in results[0]["error"]
