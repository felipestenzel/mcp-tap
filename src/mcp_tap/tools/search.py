"""search_servers tool -- query the MCP Registry for servers."""

from __future__ import annotations

from dataclasses import asdict

from mcp.server.fastmcp import Context

from mcp_tap.errors import McpTapError
from mcp_tap.models import SearchResult


async def search_servers(
    query: str,
    ctx: Context,
    limit: int = 10,
) -> list[dict[str, object]]:
    """Search the MCP Registry for servers matching a keyword.

    Args:
        query: Search term (e.g. "postgres", "github", "slack").
        limit: Maximum number of results to return (1-50, default 10).

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

        return results
    except McpTapError as exc:
        return [{"success": False, "error": str(exc)}]
    except Exception as exc:
        await ctx.error(f"Unexpected error in search_servers: {exc}")
        return [{"success": False, "error": f"Internal error: {type(exc).__name__}"}]
