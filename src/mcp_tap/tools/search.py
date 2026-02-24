"""search_servers tool -- query the MCP Registry for servers."""

from __future__ import annotations

import asyncio
import logging
import math
import re
from dataclasses import asdict

from mcp.server.fastmcp import Context

from mcp_tap.errors import McpTapError
from mcp_tap.evaluation.base import GitHubMetadataPort
from mcp_tap.evaluation.scorer import score_maturity
from mcp_tap.models import (
    MaturitySignals,
    ProjectProfile,
    RegistryType,
    SearchResult,
    ServerRecommendation,
)
from mcp_tap.scanner.credentials import map_credentials
from mcp_tap.scanner.scoring import relevance_sort_key, score_result
from mcp_tap.tools._helpers import get_context

logger = logging.getLogger(__name__)

_RELEVANCE_SCORE: dict[str, float] = {
    "high": 1.0,
    "medium": 0.6,
    "low": 0.2,
}

_CREDENTIAL_SCORE: dict[str, float] = {
    "available": 1.0,
    "none_required": 1.0,
    "partial": 0.6,
    "unknown": 0.4,
    "missing": 0.0,
}

_DEFAULT_RELEVANCE_SCORE = 0.4
_DEFAULT_CREDENTIAL_SCORE = 0.4
_DEFAULT_INTENT_SCORE = 0.4

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_STOPWORDS: frozenset[str] = frozenset(
    {
        "a",
        "an",
        "and",
        "any",
        "for",
        "in",
        "is",
        "of",
        "on",
        "or",
        "the",
        "to",
        "with",
    }
)

_MAX_EXPANDED_QUERIES = 5
_MAX_TOKEN_QUERIES = 2
_MAX_PROVIDER_QUERIES = 3

_INTENT_PROVIDER_HINTS: dict[str, tuple[str, ...]] = {
    "error_monitoring": ("sentry", "datadog", "newrelic", "rollbar", "bugsnag"),
    "incident_management": ("pagerduty", "opsgenie", "victorops"),
}

_INTENT_TERM_GROUPS: dict[str, tuple[frozenset[str], ...]] = {
    "error_monitoring": (
        frozenset(
            {"error", "errors", "exception", "exceptions", "bug", "bugs", "crash", "crashes"}
        ),
        frozenset(
            {
                "monitoring",
                "monitor",
                "observability",
                "tracking",
                "alerting",
                "alerts",
                "alert",
            }
        ),
    ),
    "incident_management": (
        frozenset(
            {
                "incident",
                "incidents",
                "oncall",
                "on-call",
                "pager",
                "escalation",
                "response",
            }
        ),
    ),
}

_COMPOSITE_WEIGHTS: dict[str, float] = {
    "intent": 0.35,
    "relevance": 0.25,
    "maturity": 0.20,
    "verified": 0.08,
    "use_count": 0.07,
    "credential": 0.05,
}


async def search_servers(
    query: str,
    ctx: Context,
    limit: int = 10,
    project_path: str | None = None,
    evaluate: bool = True,
) -> list[dict[str, object]]:
    """Search the MCP Registry for servers matching a keyword.

    Use this when the user asks for a specific server or technology.
    Pass project_path to automatically rank results by relevance to the
    project's detected tech stack — each result gets a "relevance" field
    ("high", "medium", "low") and a "match_reason" explaining the score.

    When evaluate is True (default), each result also gets a "maturity"
    field with GitHub-based quality signals (stars, last commit, tier).
    Set evaluate=False for faster results without GitHub API calls.

    After finding the right server, use configure_server with the
    package_identifier and registry_type from the results to install it.

    Args:
        query: Search term (e.g. "postgres", "github", "slack", "docker").
        limit: Maximum results to return (1-50, default 10).
        project_path: Optional project directory path. When provided,
            results are ranked by relevance to the detected tech stack
            and include credential_status for each result.
        evaluate: Whether to fetch GitHub maturity signals for each
            result (default True). Set to False for faster searches.

    Returns:
        List of servers, each with: name, description, version,
        registry_type, package_identifier, transport, is_official,
        env_vars_required, repository_url, and source ("official" |
        "smithery" | "both"). When project_path is set, also includes
        relevance, match_reason, and credential_status. When evaluate is
        True, also includes maturity. All results include deterministic
        ranking metadata: intent_match_score, intent_match_reason,
        composite_score, and composite_breakdown.
        Smithery results also include
        use_count (popularity) and verified (quality badge).
    """
    try:
        app = get_context(ctx)
        registry = app.registry

        servers = await _search_with_query_expansion(registry, query, limit)

        results: list[dict[str, object]] = []
        seen_entries: set[tuple[str, str, str]] = set()
        for server in servers:
            for pkg in server.packages:
                entry_key = (server.name.lower(), pkg.identifier, pkg.transport.value)
                if entry_key in seen_entries:
                    continue
                seen_entries.add(entry_key)

                transport = pkg.transport.value
                result: dict[str, object] = asdict(
                    SearchResult(
                        name=server.name,
                        description=server.description,
                        version=server.version,
                        registry_type=_serialize_registry_type(
                            package_identifier=pkg.identifier,
                            registry_type=pkg.registry_type,
                            transport=transport,
                        ),
                        package_identifier=pkg.identifier,
                        transport=transport,
                        is_official=server.is_official,
                        updated_at=server.updated_at,
                        env_vars_required=[
                            ev.name for ev in pkg.environment_variables if ev.is_required
                        ],
                        repository_url=server.repository_url,
                    )
                )
                # Smithery provenance signals (present when source is "smithery" or "both")
                result["source"] = server.source
                if server.use_count is not None:
                    result["use_count"] = server.use_count
                if server.verified is not None:
                    result["verified"] = server.verified
                results.append(result)

        # Apply context-aware scoring when a project path is provided
        profile: ProjectProfile | None = None
        if project_path is not None:
            profile = await _scan_project_safe(project_path)
            results = _apply_project_scoring(results, profile)
            results = _apply_credential_status(results, profile)

        # Fetch maturity signals from GitHub
        if evaluate:
            results = await _apply_maturity(results, app.github_metadata)

        # Apply query intent routing score to reduce semantic noise.
        results = _apply_intent_scoring(results, query)

        # Deterministic composite ranking (relevance + maturity + provenance + credentials)
        results = _apply_composite_scoring(results)

        return results[:limit]
    except McpTapError as exc:
        return [{"success": False, "error": str(exc)}]
    except Exception as exc:
        await ctx.error(f"Unexpected error in search_servers: {exc}")
        return [{"success": False, "error": f"Internal error: {type(exc).__name__}"}]


def _serialize_registry_type(
    *,
    package_identifier: str,
    registry_type: RegistryType,
    transport: str,
) -> str:
    """Return output registry_type, preserving remote transport semantics for URL servers."""
    if package_identifier.startswith(("https://", "http://")) and transport in (
        "streamable-http",
        "sse",
    ):
        return transport
    return registry_type.value


def _query_tokens(query: str) -> list[str]:
    """Normalize and tokenize a query into meaningful lowercase terms."""
    tokens = _TOKEN_RE.findall(query.lower())
    return [t for t in tokens if len(t) >= 3 and t not in _STOPWORDS]


def _compact_text(value: str) -> str:
    """Normalize text for loose provider matching (space/punctuation insensitive)."""
    return "".join(_TOKEN_RE.findall(value.lower()))


def _infer_intent_keys(query: str) -> list[str]:
    """Infer high-level intent classes from a free-text search query."""
    normalized = " ".join(query.lower().split())
    tokens = set(_query_tokens(normalized))
    intents: list[str] = []

    has_error = "error" in tokens or "exception" in tokens or "bug" in tokens
    has_monitoring = (
        "monitoring" in tokens
        or "observability" in tokens
        or "tracking" in tokens
        or "alerting" in tokens
        or "incident" in tokens
        or "error monitoring" in normalized
        or "error tracking" in normalized
    )
    if has_error and has_monitoring:
        intents.append("error_monitoring")

    has_incident = (
        "incident" in tokens or "oncall" in tokens or "on-call" in normalized or "pager" in tokens
    )
    if has_incident:
        intents.append("incident_management")

    return intents


def _build_search_queries(query: str) -> list[str]:
    """Build a small set of query expansions for better semantic coverage."""
    original = query.strip()
    if not original:
        return [query]

    queries: list[str] = [original]
    tokens = _query_tokens(original)

    low_signal_tokens = {"monitoring", "management", "server", "service", "tool", "tools", "mcp"}
    token_queries = [t for t in tokens if t not in low_signal_tokens][:_MAX_TOKEN_QUERIES]
    queries.extend(token_queries)

    provider_queries: list[str] = []
    for intent in _infer_intent_keys(original):
        provider_queries.extend(_INTENT_PROVIDER_HINTS.get(intent, ()))
    queries.extend(provider_queries[:_MAX_PROVIDER_QUERIES])

    deduped: list[str] = []
    seen: set[str] = set()
    for candidate in queries:
        key = candidate.lower().strip()
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(candidate)
        if len(deduped) >= _MAX_EXPANDED_QUERIES:
            break

    return deduped


async def _search_with_query_expansion(
    registry: object,
    query: str,
    limit: int,
) -> list[object]:
    """Run primary + expanded searches and merge unique servers."""
    queries = _build_search_queries(query)
    per_query_limit = min(max(limit, 5), 50)

    tasks = [registry.search(q, limit=per_query_limit) for q in queries]
    fetched = await asyncio.gather(*tasks, return_exceptions=True)

    primary_error: Exception | None = None
    merged: list[object] = []
    for index, item in enumerate(fetched):
        if isinstance(item, Exception):
            if index == 0:
                primary_error = item
            continue
        merged.extend(item)

    if not merged and primary_error is not None:
        raise primary_error

    deduped: list[object] = []
    seen_keys: set[tuple[str, str]] = set()
    for server in merged:
        name = str(getattr(server, "name", "")).lower()
        repository_url = str(getattr(server, "repository_url", "")).lower()
        key = (name, repository_url)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        deduped.append(server)

    return deduped


def _score_intent_match(
    result: dict[str, object],
    query: str,
    tokens: list[str],
    provider_hints: set[str],
    intent_keys: list[str],
) -> tuple[float, str, bool, list[str], list[str]]:
    """Score how well a result matches the semantic intent of the query."""
    searchable = f"{result.get('name', '')} {result.get('description', '')}".lower()
    normalized_query = " ".join(query.lower().split())
    searchable_tokens = set(_TOKEN_RE.findall(searchable))
    positive_signals: list[str] = []
    negative_signals: list[str] = []

    if normalized_query and normalized_query in searchable:
        positive_signals.append("direct_query_phrase_match")
        return 1.0, "Direct query phrase match", False, positive_signals, negative_signals

    if not tokens:
        negative_signals.append("no_semantic_tokens")
        return (
            _DEFAULT_INTENT_SCORE,
            "No semantic tokens extracted",
            False,
            positive_signals,
            negative_signals,
        )

    matched = [token for token in tokens if token in searchable]
    coverage = len(matched) / len(tokens)

    searchable_compact = _compact_text(searchable)
    matched_provider = next(
        (
            hint
            for hint in provider_hints
            if hint in searchable or _compact_text(hint) in searchable_compact
        ),
        "",
    )
    if matched_provider:
        positive_signals.append(f"provider_hint:{matched_provider}")
    if matched_provider and coverage >= 0.5:
        positive_signals.append("keyword_coverage:medium_or_higher")
        return (
            0.95,
            f"Provider hint match: {matched_provider}",
            False,
            positive_signals,
            negative_signals,
        )
    if matched_provider:
        return (
            0.90,
            f"Provider hint match: {matched_provider}",
            False,
            positive_signals,
            negative_signals,
        )

    # Intent gate: broad intent queries need semantic pair/group coverage.
    for intent in intent_keys:
        term_groups = _INTENT_TERM_GROUPS.get(intent, ())
        if not term_groups:
            continue
        missing_groups = 0
        for group in term_groups:
            if any(term in searchable_tokens for term in group):
                positive_signals.append(f"intent_group_match:{intent}")
                continue
            missing_groups += 1
        if missing_groups > 0:
            negative_signals.append(f"missing_intent_groups:{intent}")
            return (
                0.05,
                f"Off-intent candidate for {intent.replace('_', ' ')}",
                True,
                positive_signals,
                negative_signals,
            )

    if coverage >= 0.75:
        positive_signals.append("keyword_coverage:strong")
        return 0.80, "Strong keyword coverage", False, positive_signals, negative_signals
    if coverage >= 0.50:
        positive_signals.append("keyword_coverage:partial")
        return 0.60, "Partial keyword coverage", False, positive_signals, negative_signals
    if coverage > 0:
        negative_signals.append("keyword_coverage:weak")
        return 0.35, "Weak keyword coverage", False, positive_signals, negative_signals
    negative_signals.append("no_intent_keywords")
    return 0.0, "No intent keyword match", False, positive_signals, negative_signals


def _apply_intent_scoring(results: list[dict[str, object]], query: str) -> list[dict[str, object]]:
    """Attach intent-match score and reason for deterministic semantic rerank."""
    tokens = _query_tokens(query)
    intent_keys = _infer_intent_keys(query)
    provider_hints = {
        hint for intent in intent_keys for hint in _INTENT_PROVIDER_HINTS.get(intent, ())
    }

    for result in results:
        score, reason, gate_applied, positive_signals, negative_signals = _score_intent_match(
            result=result,
            query=query,
            tokens=tokens,
            provider_hints=provider_hints,
            intent_keys=intent_keys,
        )
        result["intent_match_score"] = round(score, 4)
        result["intent_match_reason"] = reason
        result["intent_confidence"] = round(score, 4)
        result["intent_gate_applied"] = gate_applied
        result["intent_positive_signals"] = positive_signals
        result["intent_negative_signals"] = negative_signals

    return results


def _apply_project_scoring(
    results: list[dict[str, object]],
    profile: ProjectProfile | None,
) -> list[dict[str, object]]:
    """Score and sort results based on a project's technology profile."""
    if profile is None:
        for result in results:
            result["relevance"] = "low"
            result["match_reason"] = ""
        return results

    scored: list[tuple[dict[str, object], str]] = []
    for result in results:
        name = str(result.get("name", ""))
        description = str(result.get("description", ""))
        relevance, reason = score_result(name, description, profile)
        enriched = {**result, "relevance": relevance, "match_reason": reason}
        scored.append((enriched, relevance))

    scored.sort(key=lambda item: relevance_sort_key(item[1]))
    return [item[0] for item in scored]


def _apply_credential_status(
    results: list[dict[str, object]],
    profile: ProjectProfile | None,
) -> list[dict[str, object]]:
    """Add credential_status to each result based on project env vars."""
    if profile is None:
        return results

    for result in results:
        env_vars_required = result.get("env_vars_required", [])
        if not env_vars_required:
            result["credential_status"] = "none_required"
            continue

        # Build registry env vars dict for this result
        pkg_id = str(result.get("package_identifier", ""))
        reg_vars = {pkg_id: list(env_vars_required)} if pkg_id else {}

        # Create a minimal recommendation for mapping
        rec = ServerRecommendation(
            server_name=str(result.get("name", "")),
            package_identifier=pkg_id,
            registry_type=RegistryType.NPM,
            reason="",
            priority="low",
        )
        mappings = map_credentials([rec], profile.env_var_names, reg_vars)

        if not mappings:
            result["credential_status"] = "unknown"
        elif all(m.status != "missing" for m in mappings):
            result["credential_status"] = "available"
        elif any(m.status != "missing" for m in mappings):
            result["credential_status"] = "partial"
        else:
            result["credential_status"] = "missing"

        result["credential_details"] = [
            {
                "required": m.required_env_var,
                "available_as": m.available_env_var,
                "source": m.source,
                "status": m.status,
            }
            for m in mappings
        ]

    return results


async def _apply_maturity(
    results: list[dict[str, object]],
    github_metadata: GitHubMetadataPort,
) -> list[dict[str, object]]:
    """Fetch GitHub maturity signals and add scores to results."""
    # Deduplicate repos to avoid duplicate API calls
    repo_urls: dict[str, int] = {}
    for i, result in enumerate(results):
        url = str(result.get("repository_url", ""))
        if url and "github.com" in url and url not in repo_urls:
            repo_urls[url] = i

    if not repo_urls:
        return results

    # Fetch signals concurrently
    async def _fetch_one(url: str) -> tuple[str, MaturitySignals | None]:
        signals = await github_metadata.fetch_repo_metadata(url)
        return url, signals

    tasks = [_fetch_one(url) for url in repo_urls]
    fetched = await asyncio.gather(*tasks, return_exceptions=True)

    signals_map: dict[str, MaturitySignals | None] = {}
    for item in fetched:
        if isinstance(item, tuple):
            url, signals = item
            signals_map[url] = signals

    # Apply scores to results
    for result in results:
        url = str(result.get("repository_url", ""))
        signals = signals_map.get(url)
        if signals is None:
            continue

        # Override is_official from registry data
        is_official = bool(result.get("is_official", False))
        if is_official and not signals.is_official:
            signals = MaturitySignals(
                stars=signals.stars,
                forks=signals.forks,
                open_issues=signals.open_issues,
                last_commit_date=signals.last_commit_date,
                last_release_date=signals.last_release_date,
                is_official=True,
                is_archived=signals.is_archived,
                license=signals.license,
            )

        maturity = score_maturity(signals)
        result["maturity"] = {
            "score": maturity.score,
            "tier": maturity.tier,
            "stars": signals.stars,
            "last_commit": signals.last_commit_date,
            "reasons": maturity.reasons,
            "warning": maturity.warning,
        }

    return results


async def _scan_project_safe(project_path: str) -> ProjectProfile | None:
    """Attempt to scan a project directory, returning None on failure."""
    try:
        from mcp_tap.scanner.detector import scan_project as _scan_project

        return await _scan_project(project_path)
    except Exception:
        logger.warning(
            "Failed to scan project at %s for context-aware search",
            project_path,
        )
        return None


def _extract_maturity_score(result: dict[str, object]) -> float:
    """Extract maturity score from a result dict (0.0 when absent/invalid)."""
    maturity = result.get("maturity")
    if not isinstance(maturity, dict):
        return 0.0
    raw = maturity.get("score")
    if not isinstance(raw, int | float):
        return 0.0
    return max(0.0, min(1.0, float(raw)))


def _extract_intent_score(result: dict[str, object]) -> float:
    """Extract intent match score from a result dict (fallback to default)."""
    raw = result.get("intent_match_score")
    if not isinstance(raw, int | float):
        return _DEFAULT_INTENT_SCORE
    return max(0.0, min(1.0, float(raw)))


def _normalize_use_count(use_count: object) -> float:
    """Normalize Smithery use_count into 0..1 using a log scale."""
    if not isinstance(use_count, int) or use_count <= 0:
        return 0.0
    # 1000 use_count ~= 1.0; lower counts scale smoothly.
    return max(0.0, min(1.0, math.log10(use_count + 1) / 3.0))


def _compute_composite(result: dict[str, object]) -> tuple[float, dict[str, object]]:
    """Compute deterministic ranking score and detailed breakdown for one result."""
    intent_score = _extract_intent_score(result)
    relevance_label = str(result.get("relevance", "")).lower()
    relevance_score = _RELEVANCE_SCORE.get(relevance_label, _DEFAULT_RELEVANCE_SCORE)

    maturity_score = _extract_maturity_score(result)

    verified_score = 1.0 if result.get("verified") is True else 0.0

    use_count = result.get("use_count")
    use_count_score = _normalize_use_count(use_count)

    credential_label = str(result.get("credential_status", "")).lower()
    credential_score = _CREDENTIAL_SCORE.get(credential_label, _DEFAULT_CREDENTIAL_SCORE)

    contributions = {
        "intent": round(_COMPOSITE_WEIGHTS["intent"] * intent_score, 4),
        "relevance": round(_COMPOSITE_WEIGHTS["relevance"] * relevance_score, 4),
        "maturity": round(_COMPOSITE_WEIGHTS["maturity"] * maturity_score, 4),
        "verified": round(_COMPOSITE_WEIGHTS["verified"] * verified_score, 4),
        "use_count": round(_COMPOSITE_WEIGHTS["use_count"] * use_count_score, 4),
        "credential": round(_COMPOSITE_WEIGHTS["credential"] * credential_score, 4),
    }
    total = round(sum(contributions.values()), 4)

    breakdown: dict[str, object] = {
        "weights": dict(_COMPOSITE_WEIGHTS),
        "signals": {
            "intent_match_reason": str(result.get("intent_match_reason", "")),
            "intent_match_score": round(intent_score, 4),
            "intent_gate_applied": bool(result.get("intent_gate_applied") is True),
            "relevance": relevance_label or "unknown",
            "maturity_score": round(maturity_score, 4),
            "verified": bool(result.get("verified") is True),
            "use_count": use_count if isinstance(use_count, int) else 0,
            "credential_status": credential_label or "unknown",
        },
        "normalized": {
            "intent": round(intent_score, 4),
            "relevance": round(relevance_score, 4),
            "maturity": round(maturity_score, 4),
            "verified": round(verified_score, 4),
            "use_count": round(use_count_score, 4),
            "credential": round(credential_score, 4),
        },
        "contributions": contributions,
    }
    return total, breakdown


def _apply_composite_scoring(results: list[dict[str, object]]) -> list[dict[str, object]]:
    """Attach deterministic composite ranking fields and sort results."""
    indexed: list[tuple[int, dict[str, object]]] = []

    for index, result in enumerate(results):
        score, breakdown = _compute_composite(result)
        result["composite_score"] = score
        result["composite_breakdown"] = breakdown
        indexed.append((index, result))

    def _sort_key(
        item: tuple[int, dict[str, object]],
    ) -> tuple[float, float, int, float, int, str, int]:
        idx, result = item
        return (
            -float(result.get("composite_score", 0.0)),
            -_extract_intent_score(result),
            relevance_sort_key(str(result.get("relevance", ""))),
            -_extract_maturity_score(result),
            -int(result.get("use_count", 0) if isinstance(result.get("use_count"), int) else 0),
            str(result.get("name", "")).lower(),
            idx,
        )

    indexed.sort(key=_sort_key)
    return [item[1] for item in indexed]
