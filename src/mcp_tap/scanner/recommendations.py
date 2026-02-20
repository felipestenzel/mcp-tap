"""Static mapping from detected technologies to MCP server recommendations."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from mcp_tap.models import (
    MCPClient,
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
    "aws": [
        ServerRecommendation(
            server_name="aws-mcp",
            package_identifier="@modelcontextprotocol/server-aws-kb-retrieval",
            registry_type=RegistryType.NPM,
            reason="AWS services detected in CI/CD pipeline",
            priority="medium",
        ),
    ],
    "kubernetes": [
        ServerRecommendation(
            server_name="kubernetes-mcp",
            package_identifier="mcp-server-kubernetes",
            registry_type=RegistryType.NPM,
            reason="Kubernetes detected in CI/CD pipeline — manage clusters and deployments",
            priority="medium",
        ),
    ],
}


# ─── Native capabilities per client ──────────────────────────
# Keywords that identify redundant MCP servers for each client.
# If a server's name or package_identifier contains any of these keywords,
# it is filtered out with the given reason.
# This approach catches ALL variants of a capability (e.g. multiple
# GitHub MCP servers from different publishers).


@dataclass(frozen=True, slots=True)
class _NativeCapability:
    keywords: list[str]
    reason: str


CLIENT_NATIVE_CAPABILITIES: dict[MCPClient, list[_NativeCapability]] = {
    MCPClient.CLAUDE_CODE: [
        _NativeCapability(
            keywords=["filesystem", "file-system"],
            reason="Claude Code has native Read/Write/Edit/Glob/Grep tools",
        ),
        _NativeCapability(
            keywords=["github"],
            reason="Claude Code has native Bash access to the gh CLI for full GitHub API access",
        ),
        _NativeCapability(
            keywords=["gitlab"],
            reason="Claude Code has native Bash access to the glab CLI for GitLab",
        ),
        _NativeCapability(
            keywords=["-git", "server-git", "mcp-git"],
            reason="Claude Code has native Bash access to git",
        ),
        _NativeCapability(
            keywords=["fetch", "web-fetch"],
            reason="Claude Code has native WebFetch and WebSearch tools",
        ),
    ],
    MCPClient.CURSOR: [
        _NativeCapability(
            keywords=["filesystem", "file-system"],
            reason="Cursor has built-in file editing capabilities",
        ),
    ],
    MCPClient.WINDSURF: [
        _NativeCapability(
            keywords=["filesystem", "file-system"],
            reason="Windsurf has built-in file editing capabilities",
        ),
    ],
    # Claude Desktop has no native tools — needs MCP for everything
    MCPClient.CLAUDE_DESKTOP: [],
}


def _is_redundant(
    server_name: str,
    package_identifier: str,
    capabilities: list[_NativeCapability],
) -> str | None:
    """Check if a server is redundant with native client capabilities.

    Returns the reason string if redundant, None if not.
    """
    name_lower = server_name.lower()
    pkg_lower = package_identifier.lower()
    for cap in capabilities:
        for keyword in cap.keywords:
            if keyword in name_lower or keyword in pkg_lower:
                return cap.reason
    return None


def recommend_servers(
    profile: ProjectProfile,
    *,
    client: MCPClient | None = None,
) -> list[ServerRecommendation]:
    """Map detected technologies to MCP server recommendations.

    When client is provided, filters out servers that are redundant with
    the client's native capabilities. For example, Claude Code already
    has filesystem and GitHub access, so those MCPs are skipped.

    Args:
        profile: A partially-built ProjectProfile with technologies populated.
        client: The MCP client where servers will be installed. When set,
            recommendations redundant with native capabilities are removed.

    Returns:
        Deduplicated list of ServerRecommendation sorted by priority (high first).
    """
    capabilities = CLIENT_NATIVE_CAPABILITIES.get(client, []) if client else []
    seen_packages: set[str] = set()
    results: list[ServerRecommendation] = []

    # Collect technology names (lowered) for lookup
    tech_names = {t.name.lower() for t in profile.technologies}

    for tech_name in tech_names:
        recommendations = TECHNOLOGY_SERVER_MAP.get(tech_name, [])
        for rec in recommendations:
            if rec.package_identifier in seen_packages:
                continue
            seen_packages.add(rec.package_identifier)
            reason = _is_redundant(rec.server_name, rec.package_identifier, capabilities)
            if reason:
                logger.debug("Skipping %s: %s", rec.server_name, reason)
                continue
            results.append(rec)

    # Always recommend filesystem server for any project — unless native
    _add_filesystem_recommendation(results, seen_packages, capabilities)

    # Sort by priority: high → medium → low
    results.sort(key=lambda r: _PRIORITY_ORDER.get(r.priority, 99))

    return results


def _add_filesystem_recommendation(
    results: list[ServerRecommendation],
    seen_packages: set[str],
    capabilities: list[_NativeCapability],
) -> None:
    """Ensure the filesystem server is recommended (unless client has native access)."""
    fs_recs = TECHNOLOGY_SERVER_MAP.get("filesystem", [])
    for rec in fs_recs:
        if rec.package_identifier not in seen_packages:
            seen_packages.add(rec.package_identifier)
            if not _is_redundant(rec.server_name, rec.package_identifier, capabilities):
                results.append(rec)
