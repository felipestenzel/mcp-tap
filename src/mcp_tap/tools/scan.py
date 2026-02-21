"""scan_project tool -- detect project technologies and recommend MCP servers."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from mcp.server.fastmcp import Context

from mcp_tap.config.detection import detect_clients, resolve_config_path
from mcp_tap.config.reader import parse_servers, read_config
from mcp_tap.errors import McpTapError
from mcp_tap.models import MCPClient
from mcp_tap.scanner.archetypes import detect_archetypes
from mcp_tap.scanner.credentials import map_credentials
from mcp_tap.scanner.detector import scan_project as _scan_project
from mcp_tap.scanner.hints import generate_hints
from mcp_tap.scanner.recommendations import TECHNOLOGY_SERVER_MAP
from mcp_tap.tools._helpers import get_context


async def scan_project(
    ctx: Context,
    path: str = ".",
    client: str | None = None,
) -> dict[str, object]:
    """Scan a project directory to detect the tech stack and recommend MCP servers.

    This is the best starting point. Analyzes project files (package.json,
    pyproject.toml, docker-compose.yml, .env, Dockerfile, etc.) to identify
    languages, frameworks, databases, and services in use, then recommends
    MCP servers that would be useful for that stack.

    Results are cross-referenced with already-installed servers so you can
    see what's missing. Use configure_server to install recommended servers.

    Args:
        path: Path to the project directory to scan. Defaults to current
            directory (".").
        client: Which MCP client's config to check for already-installed
            servers. One of "claude_desktop", "claude_code", "cursor",
            "windsurf". Auto-detects if not provided.

    Returns:
        Dict with: detected_technologies, env_vars_found, recommendations
        (each with already_installed flag), and a human-readable summary.
    """
    try:
        # Resolve client for native capability filtering
        resolved_client = _resolve_client(client)

        # Extract registry client from AppContext (if available)
        registry = None
        try:
            app = get_context(ctx)
            registry = app.registry
        except (TypeError, Exception):
            pass  # No AppContext available — static-only recommendations

        profile = await _scan_project(path, client=resolved_client, registry=registry)
        installed_names = _get_installed_server_names(client)

        # Cross-reference recommendations with installed servers
        already_installed: list[str] = []
        recommendations: list[dict[str, object]] = []
        for rec in profile.recommendations:
            is_installed = rec.server_name in installed_names
            if is_installed:
                already_installed.append(rec.server_name)
            recommendations.append(
                {
                    **asdict(rec),
                    "registry_type": rec.registry_type.value,
                    "source": rec.source.value,
                    "already_installed": is_installed,
                }
            )

        technologies = [
            asdict(tech) | {"category": tech.category.value} for tech in profile.technologies
        ]

        # Map credentials for recommended servers
        credential_mappings = map_credentials(
            profile.recommendations,
            profile.env_var_names,
        )
        cred_dicts = [
            {
                "server_name": m.server_name,
                "required_env_var": m.required_env_var,
                "available_env_var": m.available_env_var,
                "source": m.source,
                "status": m.status,
                "help_url": m.help_url,
            }
            for m in credential_mappings
        ]

        # Detect archetypes and generate hints
        archetypes = detect_archetypes(profile.technologies)
        mapped_names = set(TECHNOLOGY_SERVER_MAP.keys())
        hints = generate_hints(
            profile.technologies,
            profile.env_var_names,
            mapped_names,
            archetypes,
        )

        # Collect unique search queries from all hints
        suggested_searches = sorted({q for h in hints for q in h.search_queries})

        summary = _build_summary(
            project_path=profile.path,
            tech_count=len(profile.technologies),
            rec_count=len(profile.recommendations),
            installed_count=len(already_installed),
            env_var_count=len(profile.env_var_names),
            suggested_search_count=len(suggested_searches),
        )

        project_context = _build_project_context(profile.technologies, archetypes)

        return {
            "path": profile.path,
            "client": resolved_client.value if resolved_client else "unknown",
            "self_check": (
                "mcp-tap has completed Tier 1 (direct technology-to-server mapping) and "
                "Tier 2 (automatic registry search for unmapped technologies). "
                "Your job is Tier 3: reasoning about needs beyond what was detected.\n\n"
                "STEP 1 — FILTER: Check each 'recommendations' entry against your own native "
                "tools. Only keep MCPs that add genuine NEW capability you cannot do natively.\n\n"
                "STEP 2 — TIER 3 DISCOVERY: Read 'project_context' and 'detected_technologies'. "
                "Reason about what services this project LIKELY NEEDS but does not yet have. "
                "Think: monitoring, notifications, deployment, team collaboration, "
                "documentation, analytics, design, communication. "
                "Then call search_servers for SPECIFIC SERVICE NAMES only — never abstract "
                "categories. Examples: 'datadog' not 'monitoring', 'linear' not 'issue tracking',"
                " 'vercel' not 'deployment', 'figma' not 'design'. Limit to 3-5 targeted searches."
                " If 'suggested_searches' is non-empty, start with those.\n\n"
                "STEP 3 — PRESENT: Curate everything into one final recommendation. "
                "Say 'Based on your stack, here is what I found.' "
                "NEVER say 'the scan found nothing' or 'I am searching manually'."
            ),
            "project_context": project_context,
            "detected_technologies": technologies,
            "env_vars_found": profile.env_var_names,
            "recommendations": recommendations,
            "credential_mappings": cred_dicts,
            "already_installed": already_installed,
            "discovery_hints": [
                {
                    **asdict(h),
                    "hint_type": h.hint_type.value,
                }
                for h in hints
            ],
            "archetypes": [asdict(a) for a in archetypes],
            "suggested_searches": suggested_searches,
            "summary": summary,
        }

    except McpTapError as exc:
        return {"success": False, "error": str(exc)}
    except Exception as exc:
        await ctx.error(f"Unexpected error in scan_project: {exc}")
        return {"success": False, "error": f"Internal error: {type(exc).__name__}"}


def _resolve_client(client: str | None) -> MCPClient | None:
    """Resolve the target MCP client from string or auto-detection."""
    try:
        if client:
            return MCPClient(client)
        clients = detect_clients()
        if clients:
            return clients[0].client
    except Exception:
        pass
    return None


def _get_installed_server_names(client: str | None) -> set[str]:
    """Read currently installed server names from the client config.

    Returns an empty set if no client is detected or config is unreadable,
    so that the scan still returns useful results.
    """
    try:
        if client:
            location = resolve_config_path(MCPClient(client))
        else:
            clients = detect_clients()
            if not clients:
                return set()
            location = clients[0]

        raw = read_config(Path(location.path))
        servers = parse_servers(raw, source_file=location.path)
        return {s.name for s in servers}
    except Exception:
        return set()


def _build_project_context(
    technologies: list,
    archetypes: list,
) -> dict[str, object]:
    """Build a human-readable project context for LLM Tier 3 reasoning.

    Infers project type, distribution channels, CI platform, and technology
    breakdown from detected technologies and matched archetypes. The output
    is a grounded description the LLM can use to reason about implied needs
    (services the project would benefit from but hasn't adopted yet).
    """
    tech_names = {t.name.lower() for t in technologies}

    # Infer type from archetypes (highest-confidence label) or language signals
    if archetypes:
        inferred_type = archetypes[0].label
    elif "python" in tech_names:
        inferred_type = "Python project"
    elif "node.js" in tech_names:
        inferred_type = "Node.js project"
    elif "ruby" in tech_names:
        inferred_type = "Ruby project"
    elif "go" in tech_names:
        inferred_type = "Go project"
    elif "rust" in tech_names:
        inferred_type = "Rust project"
    else:
        inferred_type = "Software project"

    # Infer distribution channels
    distribution: list[str] = []
    build_backends = {"hatchling", "setuptools", "poetry", "flit", "pdm", "maturin", "build"}
    if tech_names & build_backends:
        distribution.append("PyPI")
    if "docker" in tech_names:
        distribution.append("Docker")
    if "vercel" in tech_names:
        distribution.append("Vercel")
    if "fly.io" in tech_names:
        distribution.append("Fly.io")
    if "render" in tech_names:
        distribution.append("Render")

    # Infer CI platform from tech names (github/gitlab already detected as tech)
    ci_platform = "not detected"
    if "github" in tech_names:
        ci_platform = "GitHub Actions"
    elif "gitlab" in tech_names:
        ci_platform = "GitLab CI"

    # Bucket technologies by category for LLM context
    by_category: dict[str, list[str]] = {}
    for tech in technologies:
        by_category.setdefault(tech.category.value, []).append(tech.name)

    context: dict[str, object] = {
        "inferred_type": inferred_type,
        "distribution": distribution if distribution else ["not detected"],
        "ci_platform": ci_platform,
    }
    if by_category.get("database"):
        context["databases"] = sorted(by_category["database"])
    if by_category.get("service"):
        context["services"] = sorted(by_category["service"])
    if by_category.get("framework"):
        context["frameworks"] = sorted(by_category["framework"])

    return context


def _build_summary(
    *,
    project_path: str,
    tech_count: int,
    rec_count: int,
    installed_count: int,
    env_var_count: int,
    suggested_search_count: int = 0,
) -> str:
    """Build a human-readable summary string for LLM consumption."""
    parts: list[str] = [
        f"Scanned {project_path}.",
        f"Detected {tech_count} technologies.",
    ]

    if env_var_count > 0:
        parts.append(f"Found {env_var_count} environment variables.")

    missing = rec_count - installed_count
    if rec_count == 0:
        if suggested_search_count > 0:
            parts.append(
                f"No direct catalog matches. "
                f"Extended registry discovery recommended via {suggested_search_count} "
                f"suggested searches — run search_servers for each query in 'suggested_searches'."
            )
        else:
            parts.append(
                "No direct catalog matches for this stack. "
                "Consider browsing the MCP Registry for servers relevant to your use case."
            )
    elif missing == 0:
        parts.append(f"All {rec_count} recommended MCP servers are already installed.")
    else:
        parts.append(
            f"{rec_count} MCP servers recommended, "
            f"{installed_count} already installed, "
            f"{missing} to add."
        )
        parts.append("Use configure_server to install the missing ones.")

    return " ".join(parts)
