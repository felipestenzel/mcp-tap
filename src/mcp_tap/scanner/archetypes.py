"""Detect project stack archetypes from detected technologies.

Pure function, no I/O. Maps technology combinations to known project
patterns (SaaS, Data Pipeline, DevOps, AI/ML, etc.) and suggests
additional search queries relevant to each archetype.
"""

from __future__ import annotations

from mcp_tap.models import DetectedTechnology, StackArchetype

# ─── Archetype Definitions ────────────────────────────────────
# Each archetype has "groups" of related technologies. When a project
# matches technologies from >= min_groups, the archetype is triggered.

_ARCHETYPE_DEFS: dict[str, dict] = {
    "saas_app": {
        "label": "SaaS Application",
        "groups": [
            {"next.js", "react", "vue", "angular", "svelte"},
            {"supabase", "firebase", "auth0", "clerk"},
            {"stripe", "paddle"},
        ],
        "min_groups": 2,
        # Specific service names validated against the MCP Registry.
        # Do NOT add abstract category queries (e.g. "monitoring") — they return zero results.
        "extra_queries": ["vercel", "sendgrid", "analytics"],
    },
    "data_pipeline": {
        "label": "Data Pipeline",
        "groups": [
            {"postgresql", "mongodb", "clickhouse"},
            {"redis", "rabbitmq", "kafka", "celery"},
            {"python"},
        ],
        "min_groups": 2,
        # No validated specific-service queries for this archetype yet.
        # LLM handles Tier 3 reasoning for data pipeline needs.
        "extra_queries": [],
    },
    "devops_infra": {
        "label": "DevOps / Infrastructure",
        "groups": [
            {"docker", "kubernetes"},
            {"terraform", "pulumi", "ansible"},
            {"aws", "gcp", "azure"},
        ],
        "min_groups": 2,
        # "datadog" and "grafana" are in TECHNOLOGY_SERVER_MAP (direct Tier 1 mapping).
        # Listed here as fallback for archetype-triggered Tier 3 searches.
        "extra_queries": ["datadog", "grafana"],
    },
    "ai_ml_app": {
        "label": "AI/ML Application",
        "groups": [
            {"openai", "anthropic", "langchain", "huggingface"},
            {"python"},
            {"postgresql", "redis"},
        ],
        "min_groups": 2,
        # No validated specific-service queries. LLM handles Tier 3 (vector DBs, observability).
        "extra_queries": [],
    },
    "fullstack_monorepo": {
        "label": "Full-Stack Monorepo",
        "groups": [
            {"turborepo", "nx", "lerna"},
            {"next.js", "react", "vue"},
            {"node.js", "python"},
        ],
        "min_groups": 2,
        "extra_queries": ["vercel"],
    },
    "ecommerce": {
        "label": "E-Commerce",
        "groups": [
            {"stripe", "shopify"},
            {"next.js", "react"},
            {"postgresql", "mongodb"},
        ],
        "min_groups": 2,
        "extra_queries": ["shopify", "sendgrid"],
    },
    "python_library": {
        "label": "Python Library / CLI Tool",
        "groups": [
            {"python"},
            {"hatchling", "setuptools", "poetry", "flit", "pdm", "maturin", "build"},
            {"pytest", "unittest", "nox", "tox"},
        ],
        "min_groups": 2,
        "extra_queries": ["notifications", "pypi", "documentation", "testing"],
    },
}


def detect_archetypes(technologies: list[DetectedTechnology]) -> list[StackArchetype]:
    """Detect stack archetypes from a list of detected technologies.

    Returns a list of matching StackArchetype instances, sorted by number
    of matched groups (most matches first).

    Args:
        technologies: Technologies detected from scanning a project.

    Returns:
        List of StackArchetype with matched technologies and extra queries.
    """
    tech_names = {t.name.lower() for t in technologies}
    results: list[tuple[int, StackArchetype]] = []

    for archetype_name, definition in _ARCHETYPE_DEFS.items():
        matched_groups = 0
        matched_techs: list[str] = []

        for group in definition["groups"]:
            overlap = tech_names & group
            if overlap:
                matched_groups += 1
                matched_techs.extend(sorted(overlap))

        if matched_groups >= definition["min_groups"]:
            results.append(
                (
                    matched_groups,
                    StackArchetype(
                        name=archetype_name,
                        label=definition["label"],
                        matched_technologies=matched_techs,
                        extra_search_queries=list(definition["extra_queries"]),
                    ),
                )
            )

    # Sort by match strength (most matched groups first)
    results.sort(key=lambda x: x[0], reverse=True)
    return [archetype for _, archetype in results]
