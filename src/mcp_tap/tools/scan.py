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

        summary = _build_summary(
            project_path=profile.path,
            tech_count=len(profile.technologies),
            rec_count=len(profile.recommendations),
            installed_count=len(already_installed),
            env_var_count=len(profile.env_var_names),
        )

        # Collect unique search queries from all hints
        suggested_searches = sorted({q for h in hints for q in h.search_queries})

        return {
            "path": profile.path,
            "client": resolved_client.value if resolved_client else "unknown",
            "self_check": (
                "BEFORE recommending any server, compare it against YOUR OWN "
                "native tools. If you already have a tool that does the same thing, "
                "only recommend the MCP if it adds significant NEW capability. "
                "Explain what it adds that you cannot do natively. "
                "Also check 'suggested_searches' for additional MCP servers "
                "to explore via search_servers."
            ),
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


def _build_summary(
    *,
    project_path: str,
    tech_count: int,
    rec_count: int,
    installed_count: int,
    env_var_count: int,
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
        parts.append("No MCP server recommendations for this stack.")
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
