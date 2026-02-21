"""Generate discovery hints from project signals.

Pure function, no I/O. Analyzes detected technologies, env vars,
and archetypes to suggest additional MCP server searches the user
might benefit from.
"""

from __future__ import annotations

import re

from mcp_tap.models import (
    DetectedTechnology,
    DiscoveryHint,
    HintType,
    StackArchetype,
)

# ─── Complement Pairs ────────────────────────────────────────
# If the project has technology X, it might also want a server for Y.

_COMPLEMENT_PAIRS: dict[str, list[str]] = {
    "postgresql": ["redis"],
    "next.js": ["vercel"],
    "docker": ["kubernetes"],
    "sentry": ["datadog"],
    "stripe": ["sendgrid"],
}

# ─── Env var → search query mapping ──────────────────────────
# Env var prefixes that suggest a service even when no dependency is detected.

_ENV_SEARCH_HINTS: list[tuple[re.Pattern[str], str, str]] = [
    (re.compile(r"^OPENAI_", re.IGNORECASE), "openai", "OpenAI API key detected"),
    (re.compile(r"^ANTHROPIC_", re.IGNORECASE), "anthropic", "Anthropic API key detected"),
    (re.compile(r"^SENTRY_", re.IGNORECASE), "sentry", "Sentry credentials detected"),
    (re.compile(r"^STRIPE_", re.IGNORECASE), "stripe", "Stripe credentials detected"),
    (re.compile(r"^TWILIO_", re.IGNORECASE), "twilio", "Twilio credentials detected"),
    (re.compile(r"^SENDGRID_", re.IGNORECASE), "sendgrid", "SendGrid credentials detected"),
    (re.compile(r"^DATADOG_", re.IGNORECASE), "datadog", "Datadog credentials detected"),
    (re.compile(r"^LINEAR_", re.IGNORECASE), "linear", "Linear credentials detected"),
    (re.compile(r"^NOTION_", re.IGNORECASE), "notion", "Notion credentials detected"),
    (re.compile(r"^FIGMA_", re.IGNORECASE), "figma", "Figma API key detected"),
    (re.compile(r"^JIRA_", re.IGNORECASE), "jira", "Jira credentials detected"),
    (re.compile(r"^CONFLUENCE_", re.IGNORECASE), "confluence", "Confluence credentials detected"),
]


def generate_hints(
    technologies: list[DetectedTechnology],
    env_var_names: list[str],
    mapped_tech_names: set[str],
    archetypes: list[StackArchetype],
) -> list[DiscoveryHint]:
    """Generate discovery hints from project signals.

    Produces hints from four sources:
    1. Unmapped technologies (detected but no curated recommendation)
    2. Env var patterns suggesting services
    3. Archetype-based suggestions
    4. Missing complement pairs

    Args:
        technologies: Technologies detected from the project scan.
        env_var_names: Env var names found in the project.
        mapped_tech_names: Set of technology names that already have
            curated recommendations in TECHNOLOGY_SERVER_MAP.
        archetypes: Stack archetypes detected for this project.

    Returns:
        Deduplicated list of DiscoveryHint sorted by confidence.
    """
    hints: list[DiscoveryHint] = []
    seen_queries: set[str] = set()

    tech_names = {t.name.lower() for t in technologies}

    # 1. Unmapped technologies → suggest registry search
    hints.extend(_unmapped_tech_hints(technologies, mapped_tech_names, seen_queries))

    # 2. Env var hints
    hints.extend(_env_var_hints(env_var_names, mapped_tech_names, seen_queries))

    # 3. Archetype-based hints
    hints.extend(_archetype_hints(archetypes, seen_queries))

    # 4. Missing complements
    hints.extend(_complement_hints(tech_names, seen_queries))

    # Sort by confidence descending
    hints.sort(key=lambda h: h.confidence, reverse=True)
    return hints


def _unmapped_tech_hints(
    technologies: list[DetectedTechnology],
    mapped_tech_names: set[str],
    seen_queries: set[str],
) -> list[DiscoveryHint]:
    """Generate hints for detected technologies with no curated recommendation."""
    hints: list[DiscoveryHint] = []
    # Lowered mapped names for comparison
    mapped_lower = {n.lower() for n in mapped_tech_names}
    # Skip generic entries (languages, build tools) that rarely have MCP servers
    skip_names = {"python", "node.js", "ruby", "go", "rust", "make"}

    seen_tech_names: set[str] = set()
    for tech in technologies:
        name_lower = tech.name.lower()
        if (
            name_lower not in mapped_lower
            and name_lower not in skip_names
            and name_lower not in seen_tech_names
        ):
            seen_tech_names.add(name_lower)
            query = f"{tech.name} mcp server"
            if query not in seen_queries:
                seen_queries.add(query)
                hints.append(
                    DiscoveryHint(
                        hint_type=HintType.UNMAPPED_TECHNOLOGY,
                        trigger=f"Detected '{tech.name}' from {tech.source_file}",
                        suggestion=f"Search the MCP Registry for '{tech.name}' servers",
                        search_queries=[tech.name],
                        confidence=0.5,
                    )
                )
    return hints


def _env_var_hints(
    env_var_names: list[str],
    mapped_tech_names: set[str],
    seen_queries: set[str],
) -> list[DiscoveryHint]:
    """Generate hints from env var patterns suggesting services."""
    hints: list[DiscoveryHint] = []
    mapped_lower = {n.lower() for n in mapped_tech_names}
    seen_services: set[str] = set()

    for var_name in env_var_names:
        for pattern, service_name, description in _ENV_SEARCH_HINTS:
            if (
                pattern.search(var_name)
                and service_name not in seen_services
                and service_name not in mapped_lower
            ):
                seen_services.add(service_name)
                if service_name not in seen_queries:
                    seen_queries.add(service_name)
                    hints.append(
                        DiscoveryHint(
                            hint_type=HintType.ENV_VAR_HINT,
                            trigger=f"Env var '{var_name}' found",
                            suggestion=f"{description} — search for MCP servers",
                            search_queries=[service_name],
                            confidence=0.6,
                        )
                    )
    return hints


def _archetype_hints(
    archetypes: list[StackArchetype],
    seen_queries: set[str],
) -> list[DiscoveryHint]:
    """Generate hints from detected stack archetypes."""
    hints: list[DiscoveryHint] = []

    for archetype in archetypes:
        new_queries = [q for q in archetype.extra_search_queries if q not in seen_queries]
        if new_queries:
            seen_queries.update(new_queries)
            hints.append(
                DiscoveryHint(
                    hint_type=HintType.STACK_ARCHETYPE,
                    trigger=f"Project matches '{archetype.label}' archetype",
                    suggestion=(
                        f"Your {archetype.label} stack may benefit from additional MCP servers"
                    ),
                    search_queries=new_queries,
                    confidence=0.7,
                )
            )

    return hints


def _complement_hints(
    tech_names: set[str],
    seen_queries: set[str],
) -> list[DiscoveryHint]:
    """Generate hints for missing complement technologies."""
    hints: list[DiscoveryHint] = []

    for tech, complements in _COMPLEMENT_PAIRS.items():
        if tech in tech_names:
            for complement in complements:
                if complement not in tech_names and complement not in seen_queries:
                    seen_queries.add(complement)
                    hints.append(
                        DiscoveryHint(
                            hint_type=HintType.MISSING_COMPLEMENT,
                            trigger=f"'{tech}' detected without '{complement}'",
                            suggestion=(
                                f"Projects using {tech} often also use {complement} "
                                f"— consider adding an MCP server for it"
                            ),
                            search_queries=[complement],
                            confidence=0.4,
                        )
                    )

    return hints
