"""Static mapping from detected technologies to MCP server recommendations."""

from __future__ import annotations

import logging

from mcp_tap.models import (
    ProjectProfile,
    RegistryType,
    ServerRecommendation,
)

logger = logging.getLogger(__name__)

# ─── Priority ordering for sort stability ────────────────────

_PRIORITY_ORDER: dict[str, int] = {"high": 0, "medium": 1, "low": 2}

# ─── Technology → Server mapping ─────────────────────────────

TECHNOLOGY_SERVER_MAP: dict[str, list[ServerRecommendation]] = {
    "postgresql": [
        ServerRecommendation(
            server_name="postgres-mcp",
            package_identifier="@modelcontextprotocol/server-postgres",
            registry_type=RegistryType.NPM,
            reason="Direct SQL queries on your PostgreSQL database",
            priority="high",
        ),
    ],
    "redis": [
        ServerRecommendation(
            server_name="redis-mcp",
            package_identifier="@modelcontextprotocol/server-redis",
            registry_type=RegistryType.NPM,
            reason="Interact with your Redis cache/store",
            priority="medium",
        ),
    ],
    "github": [
        ServerRecommendation(
            server_name="github-mcp",
            package_identifier="@modelcontextprotocol/server-github",
            registry_type=RegistryType.NPM,
            reason="GitHub issues, PRs, and repository management",
            priority="high",
        ),
    ],
    "gitlab": [
        ServerRecommendation(
            server_name="gitlab-mcp",
            package_identifier="@modelcontextprotocol/server-gitlab",
            registry_type=RegistryType.NPM,
            reason="GitLab issues, merge requests, and project management",
            priority="high",
        ),
    ],
    "slack": [
        ServerRecommendation(
            server_name="slack-mcp",
            package_identifier="@modelcontextprotocol/server-slack",
            registry_type=RegistryType.NPM,
            reason="Send and read Slack messages",
            priority="medium",
        ),
    ],
    "mongodb": [
        ServerRecommendation(
            server_name="mongodb-mcp",
            package_identifier="@modelcontextprotocol/server-mongodb",
            registry_type=RegistryType.NPM,
            reason="Query and manage your MongoDB collections",
            priority="high",
        ),
    ],
    "sqlite": [
        ServerRecommendation(
            server_name="sqlite-mcp",
            package_identifier="@modelcontextprotocol/server-sqlite",
            registry_type=RegistryType.NPM,
            reason="Read and query your SQLite databases",
            priority="medium",
        ),
    ],
    "mysql": [
        ServerRecommendation(
            server_name="mysql-mcp",
            package_identifier="@benborla29/mcp-server-mysql",
            registry_type=RegistryType.NPM,
            reason="Query your MySQL database",
            priority="high",
        ),
    ],
    "elasticsearch": [
        ServerRecommendation(
            server_name="elasticsearch-mcp",
            package_identifier="@modelcontextprotocol/server-elasticsearch",
            registry_type=RegistryType.NPM,
            reason="Search and query your Elasticsearch indices",
            priority="medium",
        ),
    ],
    "rabbitmq": [
        ServerRecommendation(
            server_name="rabbitmq-mcp",
            package_identifier="@modelcontextprotocol/server-rabbitmq",
            registry_type=RegistryType.NPM,
            reason="Manage your RabbitMQ queues and messages",
            priority="medium",
        ),
    ],
    "filesystem": [
        ServerRecommendation(
            server_name="filesystem-mcp",
            package_identifier="@modelcontextprotocol/server-filesystem",
            registry_type=RegistryType.NPM,
            reason="Read and write project files with controlled access",
            priority="low",
        ),
    ],
}


def recommend_servers(profile: ProjectProfile) -> list[ServerRecommendation]:
    """Map detected technologies to MCP server recommendations.

    Args:
        profile: A partially-built ProjectProfile with technologies populated.

    Returns:
        Deduplicated list of ServerRecommendation sorted by priority (high first).
    """
    seen_packages: set[str] = set()
    results: list[ServerRecommendation] = []

    # Collect technology names (lowered) for lookup
    tech_names = {t.name.lower() for t in profile.technologies}

    for tech_name in tech_names:
        recommendations = TECHNOLOGY_SERVER_MAP.get(tech_name, [])
        for rec in recommendations:
            if rec.package_identifier not in seen_packages:
                seen_packages.add(rec.package_identifier)
                results.append(rec)

    # Always recommend filesystem server for any project
    _add_filesystem_recommendation(results, seen_packages)

    # Sort by priority: high → medium → low
    results.sort(key=lambda r: _PRIORITY_ORDER.get(r.priority, 99))

    return results


def _add_filesystem_recommendation(
    results: list[ServerRecommendation],
    seen_packages: set[str],
) -> None:
    """Ensure the filesystem server is always recommended."""
    fs_recs = TECHNOLOGY_SERVER_MAP.get("filesystem", [])
    for rec in fs_recs:
        if rec.package_identifier not in seen_packages:
            seen_packages.add(rec.package_identifier)
            results.append(rec)
