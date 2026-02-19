"""scan_project tool -- detect project technologies and recommend MCP servers."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from mcp.server.fastmcp import Context

from mcp_tap.config.detection import detect_clients, resolve_config_path
from mcp_tap.config.reader import parse_servers, read_config
from mcp_tap.errors import McpTapError
from mcp_tap.models import MCPClient
from mcp_tap.scanner.detector import scan_project as _scan_project


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
        profile = await _scan_project(path)
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
                    "already_installed": is_installed,
                }
            )

        technologies = [
            asdict(tech) | {"category": tech.category.value} for tech in profile.technologies
        ]

        summary = _build_summary(
            project_path=profile.path,
            tech_count=len(profile.technologies),
            rec_count=len(profile.recommendations),
            installed_count=len(already_installed),
            env_var_count=len(profile.env_var_names),
        )

        return {
            "path": profile.path,
            "detected_technologies": technologies,
            "env_vars_found": profile.env_var_names,
            "recommendations": recommendations,
            "already_installed": already_installed,
            "summary": summary,
        }

    except McpTapError as exc:
        return {"success": False, "error": str(exc)}
    except Exception as exc:
        await ctx.error(f"Unexpected error in scan_project: {exc}")
        return {"success": False, "error": f"Internal error: {type(exc).__name__}"}


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
