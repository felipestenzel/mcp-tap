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
        "### CRITICAL: Native capability awareness\n"
        "NEVER recommend an MCP server whose functionality the client already has "
        "natively. The scan tool filters these automatically, but when you search "
        "the registry yourself, YOU must apply the same judgment:\n"
        "- **Claude Code** already has: filesystem (Read/Write/Edit/Glob/Grep), "
        "git (Bash + git CLI), GitHub (Bash + gh CLI), GitLab (Bash + glab CLI), "
        "web fetch (WebFetch/WebSearch tools). Do NOT recommend any MCP server "
        "that duplicates these — regardless of its package name or publisher.\n"
        "- **Cursor** already has: filesystem editing.\n"
        "- **Windsurf** already has: filesystem editing.\n"
        "- **Claude Desktop** has NO native tools — recommend everything.\n"
        "If you're unsure whether a capability is native, err on the side of "
        "NOT recommending. The user can always search explicitly."
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
