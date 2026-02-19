"""Context-aware scoring for search results based on a project's technology profile.

Compares MCP server search results against detected project technologies to
determine relevance. Used by tools/search.py when a project_path is provided.
"""

from __future__ import annotations

from mcp_tap.models import ProjectProfile, TechnologyCategory

# Relevance levels (used for sorting: lower value = higher priority)
_RELEVANCE_ORDER: dict[str, int] = {"high": 0, "medium": 1, "low": 2}

# Map technology categories to keywords that might appear in server descriptions
_CATEGORY_KEYWORDS: dict[TechnologyCategory, list[str]] = {
    TechnologyCategory.DATABASE: [
        "database", "sql", "query", "db", "data", "storage", "cache",
    ],
    TechnologyCategory.FRAMEWORK: [
        "framework", "web", "api", "server", "backend", "frontend",
    ],
    TechnologyCategory.SERVICE: [
        "integration", "api", "service", "webhook", "notification",
    ],
    TechnologyCategory.PLATFORM: [
        "deploy", "cloud", "container", "hosting", "ci", "cd",
    ],
    TechnologyCategory.LANGUAGE: [
        "sdk", "runtime", "compiler", "interpreter",
    ],
}


def score_result(
    result_name: str,
    result_description: str,
    profile: ProjectProfile,
) -> tuple[str, str]:
    """Score a search result's relevance to a project profile.

    Checks for exact technology name matches first, then category-level
    matches. Returns the best (highest relevance) match found.

    Args:
        result_name: Name of the MCP server from the registry.
        result_description: Description of the MCP server.
        profile: The scanned project profile with detected technologies.

    Returns:
        Tuple of (relevance, reason) where relevance is "high", "medium",
        or "low", and reason explains why.
    """
    if not profile.technologies:
        return "low", ""

    name_lower = result_name.lower()
    desc_lower = result_description.lower()
    searchable = f"{name_lower} {desc_lower}"

    # Pass 1: Exact technology name match (highest relevance)
    for tech in profile.technologies:
        tech_name = tech.name.lower()
        if tech_name in name_lower or tech_name in desc_lower:
            return "high", f"Project uses {tech.name} ({tech.category.value})"

    # Pass 2: Category-level keyword match (medium relevance)
    project_categories = {tech.category for tech in profile.technologies}
    for category in project_categories:
        keywords = _CATEGORY_KEYWORDS.get(category, [])
        for keyword in keywords:
            if keyword in searchable:
                return (
                    "medium",
                    f"Related to project's {category.value} stack",
                )

    return "low", ""


def relevance_sort_key(relevance: str) -> int:
    """Return a sort key for relevance level (lower = more relevant)."""
    return _RELEVANCE_ORDER.get(relevance, 99)
