"""inspect_server tool -- fetch and extract config hints from server documentation."""

from __future__ import annotations

from dataclasses import asdict

from mcp.server.fastmcp import Context

from mcp_tap.inspector.extractor import extract_config_hints
from mcp_tap.inspector.fetcher import fetch_readme

# Max chars of raw README to return (enough for LLM context)
_MAX_README_CHARS = 5000


async def inspect_server(
    repository_url: str,
    ctx: Context,
) -> dict[str, object]:
    """Fetch an MCP server's documentation and extract configuration details.

    Use this when search_servers returns incomplete data (missing env vars,
    unclear transport) or when you have a GitHub URL for a server not in the
    registry.

    Fetches the README.md from the repository URL and extracts:
    - Install commands (npm, pip, docker)
    - Transport type (stdio, http, sse)
    - Required environment variables with descriptions
    - Command and args patterns
    - Usage examples

    The extracted data may be incomplete or ambiguous — use your judgment
    to fill gaps based on the raw README content also returned.

    Args:
        repository_url: GitHub/GitLab repository URL
            (e.g. "https://github.com/modelcontextprotocol/servers").

    Returns:
        Dict with: extracted_config (structured hints), raw_readme
        (first 5000 chars of README for LLM reasoning), and
        confidence (how much structured data was found).
    """
    try:
        app_ctx = ctx.request_context.lifespan_context
        http_client = app_ctx.http_client

        readme = await fetch_readme(repository_url, http_client)
        if readme is None:
            return {
                "success": False,
                "error": (
                    f"Could not fetch README from {repository_url}. "
                    "Check that the URL is a valid GitHub or GitLab repository."
                ),
            }

        hints = extract_config_hints(readme)

        return {
            "success": True,
            "repository_url": repository_url,
            "extracted_config": {
                "install_commands": hints.install_commands,
                "transport_hints": hints.transport_hints,
                "env_vars": [asdict(ev) for ev in hints.env_vars_mentioned],
                "command_patterns": hints.command_patterns,
                "json_config_blocks": hints.json_config_blocks,
            },
            "confidence": hints.confidence,
            "raw_readme": readme[:_MAX_README_CHARS],
        }

    except Exception as exc:
        await ctx.error(f"Unexpected error in inspect_server: {exc}")
        return {"success": False, "error": f"Internal error: {type(exc).__name__}"}
