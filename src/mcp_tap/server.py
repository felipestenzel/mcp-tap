"""MCP server that discovers, installs, and configures other MCP servers."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

import httpx
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from mcp_tap.registry.client import RegistryClient
from mcp_tap.tools.configure import configure_server
from mcp_tap.tools.health import check_health
from mcp_tap.tools.inspect import inspect_server
from mcp_tap.tools.list import list_installed
from mcp_tap.tools.remove import remove_server
from mcp_tap.tools.scan import scan_project
from mcp_tap.tools.search import search_servers
from mcp_tap.tools.test import test_connection


@dataclass
class AppContext:
    """Shared state across all tool invocations."""

    http_client: httpx.AsyncClient
    registry: RegistryClient


@asynccontextmanager
async def app_lifespan(server: FastMCP) -> AsyncIterator[AppContext]:
    """Manage httpx client lifecycle."""
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(30.0, connect=10.0),
        follow_redirects=True,
        transport=httpx.AsyncHTTPTransport(retries=3),
    ) as http_client:
        registry = RegistryClient(http_client)
        yield AppContext(http_client=http_client, registry=registry)


mcp = FastMCP(
    "mcp-tap",
    instructions=(
        "mcp-tap discovers, installs, and configures MCP servers for the user. "
        "\n\n"
        "## How to use mcp-tap\n\n"
        "**Be autonomous.** Do NOT just list raw results to the user. Instead, "
        "use the tools iteratively behind the scenes: scan, search, evaluate, "
        "inspect — then present only your curated recommendation with reasoning.\n\n"
        "### Recommended workflow\n"
        "1. **scan_project** — Always start here. Detects the tech stack and "
        "recommends servers. The scan already filters out servers redundant with "
        "the current client's native capabilities (e.g. filesystem MCP is skipped "
        "for Claude Code which has native Read/Write/Edit).\n"
        "2. **Evaluate internally** — For each recommendation, consider:\n"
        "   - Is this server truly useful, or is it redundant with native tools?\n"
        "   - Does the user already have equivalent capability via CLI tools?\n"
        "   - Use search_servers with evaluate=True to check maturity scores.\n"
        "   - Use inspect_server if registry data is incomplete.\n"
        "3. **Present your curated opinion** — Tell the user which servers you "
        "recommend and WHY, which ones you considered but rejected (with reason), "
        "and what credentials they'll need. Be opinionated, not a raw list.\n"
        "4. **configure_server** — Only after user approves, install and configure. "
        "Handles npm/pip/docker install, config write, and validation in one step. "
        "Use clients='all' for all clients, scope='project' for project-scoped.\n"
        "5. **check_health** — After installing, verify everything works.\n"
        "\n"
        "### Other tools\n"
        "- **inspect_server** — Fetch a server's README and extract config hints. "
        "Use when search data is incomplete or for servers not in the registry.\n"
        "- **list_installed** — Show all configured servers (secrets masked).\n"
        "- **test_connection** — Test a single server by name.\n"
        "- **remove_server** — Remove a server from config.\n"
        "\n"
        "### Key principles\n"
        "- **Think before showing.** Run multiple tools internally to build "
        "a complete picture before presenting to the user.\n"
        "- **Quality over quantity.** One great recommendation beats five mediocre ones.\n"
        "- **Explain rejections.** 'I considered X but skipped it because Y' builds trust.\n"
        "- **Check credential_mappings.** Tell the user which env vars are available "
        "vs missing, and where to get them (help_url).\n"
        "- Supported clients: claude_desktop, claude_code, cursor, windsurf.\n"
        "\n"
        "### CRITICAL: Self-awareness before recommending\n"
        "Before recommending ANY MCP server, you MUST compare it against your "
        "own native capabilities. You know what tools you have — use that knowledge.\n\n"
        "For EACH candidate MCP server, ask yourself:\n"
        "1. Do I already have a native tool that does this? (Check your tool list)\n"
        "2. If yes: does the MCP add significant capability BEYOND what I can "
        "already do? Be specific about what it adds.\n"
        "3. If the MCP only duplicates what you can already do natively, "
        "skip it and explain why: 'I already have [native tool] which covers this.'\n"
        "4. If the MCP adds real value beyond native tools, recommend it AND "
        "explain specifically what it adds that you can't do natively.\n\n"
        "Examples of good reasoning:\n"
        "- 'I already have Read/Write/Edit tools, so filesystem MCP adds nothing.'\n"
        "- 'I can run git commands via Bash, so basic git MCP is redundant.'\n"
        "- 'I can use gh CLI for PRs and issues, but GitHub MCP also gives me "
        "Dependabot alerts and code search across repos — that is new value.'\n"
        "- 'I have no way to query PostgreSQL natively — this MCP is essential.'"
    ),
    lifespan=app_lifespan,
)

# ─── Read-only tools ──────────────────────────────────────────
mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))(scan_project)
mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))(search_servers)
mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))(list_installed)
mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))(test_connection)
mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))(check_health)
mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))(inspect_server)

# ─── Destructive tools ────────────────────────────────────────
mcp.tool(annotations=ToolAnnotations(destructiveHint=True))(configure_server)
mcp.tool(annotations=ToolAnnotations(destructiveHint=True))(remove_server)
