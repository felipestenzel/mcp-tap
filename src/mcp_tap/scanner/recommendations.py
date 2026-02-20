"""Technology-to-server recommendations: static map + dynamic registry bridge."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from mcp_tap.models import (
    MCPClient,
    ProjectProfile,
    RecommendationSource,
    RegistryType,
    ServerRecommendation,
)

if TYPE_CHECKING:
    from mcp_tap.registry.base import RegistryClientPort

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
    "sentry": [
        ServerRecommendation(
            server_name="sentry-mcp",
            package_identifier="@sentry/mcp-server-sentry",
            registry_type=RegistryType.PYPI,
            reason="Query Sentry issues, events, and project data",
            priority="medium",
        ),
    ],
    "docker": [
        ServerRecommendation(
            server_name="docker-mcp",
            package_identifier="@modelcontextprotocol/server-docker",
            registry_type=RegistryType.NPM,
            reason="Manage Docker containers and images",
            priority="medium",
        ),
    ],
    "terraform": [
        ServerRecommendation(
            server_name="terraform-mcp",
            package_identifier="terraform-mcp-server",
            registry_type=RegistryType.NPM,
            reason="Infrastructure as Code with Terraform — plan and apply changes",
            priority="medium",
        ),
    ],
    "notion": [
        ServerRecommendation(
            server_name="notion-mcp",
            package_identifier="@notionhq/notion-mcp-server",
            registry_type=RegistryType.NPM,
            reason="Access Notion databases, pages, and workspaces",
            priority="medium",
        ),
    ],
    "linear": [
        ServerRecommendation(
            server_name="linear-mcp",
            package_identifier="mcp-linear",
            registry_type=RegistryType.NPM,
            reason="Manage Linear issues, projects, and cycles",
            priority="medium",
        ),
    ],
    "supabase": [
        ServerRecommendation(
            server_name="supabase-mcp",
            package_identifier="@supabase/mcp-server-supabase",
            registry_type=RegistryType.NPM,
            reason="Query Supabase database and manage project resources",
            priority="high",
        ),
    ],
    "stripe": [
        ServerRecommendation(
            server_name="stripe-mcp",
            package_identifier="@stripe/mcp",
            registry_type=RegistryType.NPM,
            reason="Manage Stripe payments, customers, and subscriptions",
            priority="high",
        ),
    ],
    "gcp": [
        ServerRecommendation(
            server_name="gcp-mcp",
            package_identifier="@google-cloud/mcp-server",
            registry_type=RegistryType.NPM,
            reason="Google Cloud Platform services detected — manage cloud resources",
            priority="medium",
        ),
    ],
    "azure": [
        ServerRecommendation(
            server_name="azure-mcp",
            package_identifier="azure-mcp-server",
            registry_type=RegistryType.NPM,
            reason="Microsoft Azure services detected — manage cloud resources",
            priority="medium",
        ),
    ],
    "cloudflare": [
        ServerRecommendation(
            server_name="cloudflare-mcp",
            package_identifier="@cloudflare/mcp-server-cloudflare",
            registry_type=RegistryType.NPM,
            reason="Manage Cloudflare Workers, DNS, and infrastructure",
            priority="medium",
        ),
    ],
    "firebase": [
        ServerRecommendation(
            server_name="firebase-mcp",
            package_identifier="firebase-mcp-server",
            registry_type=RegistryType.NPM,
            reason="Manage Firebase projects, auth, and Firestore",
            priority="medium",
        ),
    ],
    "datadog": [
        ServerRecommendation(
            server_name="datadog-mcp",
            package_identifier="datadog-mcp-server",
            registry_type=RegistryType.NPM,
            reason="Query Datadog metrics, monitors, and dashboards",
            priority="medium",
        ),
    ],
    "grafana": [
        ServerRecommendation(
            server_name="grafana-mcp",
            package_identifier="grafana-mcp-server",
            registry_type=RegistryType.NPM,
            reason="Query Grafana dashboards and data sources",
            priority="low",
        ),
    ],
    "kafka": [
        ServerRecommendation(
            server_name="kafka-mcp",
            package_identifier="kafka-mcp-server",
            registry_type=RegistryType.NPM,
            reason="Manage Kafka topics, consumers, and messages",
            priority="medium",
        ),
    ],
    "clickhouse": [
        ServerRecommendation(
            server_name="clickhouse-mcp",
            package_identifier="clickhouse-mcp-server",
            registry_type=RegistryType.NPM,
            reason="Query ClickHouse analytics database",
            priority="medium",
        ),
    ],
    "openai": [
        ServerRecommendation(
            server_name="openai-mcp",
            package_identifier="mcp-openai",
            registry_type=RegistryType.NPM,
            reason="OpenAI API integration detected — manage models and completions",
            priority="low",
        ),
    ],
    "anthropic": [
        ServerRecommendation(
            server_name="anthropic-mcp",
            package_identifier="mcp-anthropic",
            registry_type=RegistryType.NPM,
            reason="Anthropic API integration detected",
            priority="low",
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


async def recommend_servers(
    profile: ProjectProfile,
    *,
    client: MCPClient | None = None,
    registry: RegistryClientPort | None = None,
) -> list[ServerRecommendation]:
    """Map detected technologies to MCP server recommendations.

    First builds recommendations from the curated TECHNOLOGY_SERVER_MAP.
    Then, for any technologies that have no curated mapping, queries the
    MCP Registry API (if a registry client is provided) to discover
    dynamic recommendations.

    When client is provided, filters out servers that are redundant with
    the client's native capabilities. For example, Claude Code already
    has filesystem and GitHub access, so those MCPs are skipped.

    Args:
        profile: A partially-built ProjectProfile with technologies populated.
        client: The MCP client where servers will be installed. When set,
            recommendations redundant with native capabilities are removed.
        registry: Optional registry client for dynamic server discovery.
            When provided, unmapped technologies trigger a registry search.
            On any error or timeout, silently falls back to static-only.

    Returns:
        Deduplicated list of ServerRecommendation sorted by priority (high first).
    """
    capabilities = CLIENT_NATIVE_CAPABILITIES.get(client, []) if client else []
    seen_packages: set[str] = set()
    results: list[ServerRecommendation] = []

    # Collect technology names (lowered) for lookup
    tech_names = {t.name.lower() for t in profile.technologies}
    unmapped_techs: list[str] = []

    for tech_name in tech_names:
        recommendations = TECHNOLOGY_SERVER_MAP.get(tech_name, [])
        if not recommendations:
            unmapped_techs.append(tech_name)
            continue
        for rec in recommendations:
            if rec.package_identifier in seen_packages:
                continue
            seen_packages.add(rec.package_identifier)
            reason = _is_redundant(rec.server_name, rec.package_identifier, capabilities)
            if reason:
                logger.debug("Skipping %s: %s", rec.server_name, reason)
                continue
            results.append(rec)

    # Dynamic registry lookup for unmapped technologies
    if registry and unmapped_techs:
        dynamic = await _search_registry(registry, unmapped_techs, seen_packages, capabilities)
        results.extend(dynamic)

    # Always recommend filesystem server for any project — unless native
    _add_filesystem_recommendation(results, seen_packages, capabilities)

    # Sort by priority: high → medium → low
    results.sort(key=lambda r: _PRIORITY_ORDER.get(r.priority, 99))

    return results


_REGISTRY_TIMEOUT_SECONDS = 5
# Skip technologies that are too generic for meaningful registry search
_SKIP_REGISTRY_SEARCH = {"python", "node.js", "ruby", "go", "rust", "make"}


async def _search_registry(
    registry: RegistryClientPort,
    tech_names: list[str],
    seen_packages: set[str],
    capabilities: list[_NativeCapability],
) -> list[ServerRecommendation]:
    """Search the MCP Registry for servers matching unmapped technologies.

    Each search has a per-technology timeout. On any error or timeout,
    that technology is silently skipped — the scan still returns useful
    static results.
    """
    results: list[ServerRecommendation] = []

    for tech_name in tech_names:
        if tech_name in _SKIP_REGISTRY_SEARCH:
            continue

        try:
            servers = await asyncio.wait_for(
                registry.search(tech_name, limit=3),
                timeout=_REGISTRY_TIMEOUT_SECONDS,
            )
        except (TimeoutError, Exception):
            logger.debug("Registry search for '%s' failed or timed out", tech_name)
            continue

        for server in servers:
            if not server.packages:
                continue
            pkg = server.packages[0]
            if pkg.identifier in seen_packages:
                continue
            seen_packages.add(pkg.identifier)

            rec = ServerRecommendation(
                server_name=server.name.replace("/", "-").replace(".", "-"),
                package_identifier=pkg.identifier,
                registry_type=pkg.registry_type,
                reason=f"Found in MCP Registry for '{tech_name}': {server.description[:100]}",
                priority="low",
                source=RecommendationSource.REGISTRY,
                confidence=0.6,
            )

            if _is_redundant(rec.server_name, rec.package_identifier, capabilities):
                continue
            results.append(rec)

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
