"""search_servers tool -- query the MCP Registry for servers."""

from __future__ import annotations

import asyncio
import logging
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
        env_vars_required, and repository_url. When project_path is set,
        also includes relevance, match_reason, and credential_status.
        When evaluate is True, also includes maturity.
    """
    try:
        app = get_context(ctx)
        registry = app.registry

        servers = await registry.search(query, limit=min(limit, 50))

        results: list[dict[str, object]] = []
        for server in servers:
            for pkg in server.packages:
                results.append(
                    asdict(
                        SearchResult(
                            name=server.name,
                            description=server.description,
                            version=server.version,
                            registry_type=pkg.registry_type.value,
                            package_identifier=pkg.identifier,
                            transport=pkg.transport.value,
                            is_official=server.is_official,
                            updated_at=server.updated_at,
                            env_vars_required=[
                                ev.name for ev in pkg.environment_variables if ev.is_required
                            ],
                            repository_url=server.repository_url,
                        )
                    )
                )
                if len(results) >= limit:
                    break
            if len(results) >= limit:
                break

        # Apply context-aware scoring when a project path is provided
        profile: ProjectProfile | None = None
        if project_path is not None:
            profile = await _scan_project_safe(project_path)
            results = _apply_project_scoring(results, profile)
            results = _apply_credential_status(results, profile)

        # Fetch maturity signals from GitHub
        if evaluate:
            results = await _apply_maturity(results, app.github_metadata)

        return results
    except McpTapError as exc:
        return [{"success": False, "error": str(exc)}]
    except Exception as exc:
        await ctx.error(f"Unexpected error in search_servers: {exc}")
        return [{"success": False, "error": f"Internal error: {type(exc).__name__}"}]


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
