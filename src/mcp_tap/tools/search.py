"""search_servers tool -- query the MCP Registry for servers."""

from __future__ import annotations

import logging
from dataclasses import asdict

from mcp.server.fastmcp import Context

from mcp_tap.errors import McpTapError
from mcp_tap.models import ProjectProfile, SearchResult
from mcp_tap.scanner.scoring import relevance_sort_key, score_result

logger = logging.getLogger(__name__)


async def search_servers(
    query: str,
    ctx: Context,
    limit: int = 10,
    project_path: str | None = None,
) -> list[dict[str, object]]:
    """Search the MCP Registry for servers matching a keyword.

    When project_path is provided, results are scored and sorted by relevance
    to the project's detected technology stack. Each result is tagged with a
    ``relevance`` field ("high", "medium", or "low") and a ``match_reason``
    explaining the score.

    Args:
        query: Search term (e.g. "postgres", "github", "slack").
        limit: Maximum number of results to return (1-50, default 10).
        project_path: Optional path to a project directory. When provided,
            the project is scanned and results are ranked by relevance to
            the detected tech stack.

    Returns:
        List of matching servers with name, description, package info,
        required environment variables, and repository URL.
    """
    try:
        app_ctx = ctx.request_context.lifespan_context
        registry = app_ctx.registry

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
                                ev.name
                                for ev in pkg.environment_variables
                                if ev.is_required
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
        if project_path is not None:
            profile = await _scan_project_safe(project_path)
            results = _apply_project_scoring(results, profile)

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
    """Score and sort results based on a project's technology profile.

    Falls back gracefully if the profile is None -- results are returned
    with default "low" relevance.
    """
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

    # Stable sort: high first, then medium, then low
    # Within each group, original order is preserved (stable sort guarantee)
    scored.sort(key=lambda item: relevance_sort_key(item[1]))

    return [item[0] for item in scored]


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
