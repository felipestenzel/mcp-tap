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
        "## Recommended workflow\n"
        "1. **scan_project** — Start here. Scans the user's project to detect their "
        "tech stack (languages, frameworks, databases, services) and recommends "
        "MCP servers they should install. Shows what's already installed vs missing.\n"
        "2. **search_servers** — Search the MCP Registry by keyword. Pass "
        "project_path to rank results by relevance to the project's stack.\n"
        "3. **configure_server** — Install a package and add it to the client "
        "config. Handles npm/pip/docker install, config write, and connection "
        "validation in one step. Use clients='all' to configure all clients at once, "
        "or scope='project' for project-scoped config.\n"
        "4. **check_health** — Verify all configured servers are working. "
        "Tests each one concurrently and reports healthy/unhealthy/timeout.\n"
        "\n"
        "## Other tools\n"
        "- **inspect_server** — Fetch a server's README and extract config hints "
        "(env vars, transport, install commands). Use when search_servers data is "
        "incomplete or for servers not in the registry.\n"
        "- **list_installed** — Show all configured servers (secrets are masked).\n"
        "- **test_connection** — Test a single server by name.\n"
        "- **remove_server** — Remove a server from config. Supports multi-client.\n"
        "\n"
        "## Tips\n"
        "- If configure_server validation fails, the config is still written. "
        "The user may need to set environment variables or restart their client.\n"
        "- If a server fails health check, try remove_server then configure_server "
        "again to reinstall.\n"
        "- Supported clients: claude_desktop, claude_code, cursor, windsurf."
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
