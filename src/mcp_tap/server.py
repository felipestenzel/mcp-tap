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
        "This server helps you discover, install, and configure MCP servers. "
        "Use scan_project to detect your tech stack and get recommendations, "
        "search_servers to find servers, configure_server to install and add them "
        "to your MCP client config, test_connection to verify they work, "
        "list_installed to see what's configured, and remove_server to clean up."
    ),
    lifespan=app_lifespan,
)

# ─── Read-only tools ──────────────────────────────────────────
mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))(scan_project)
mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))(search_servers)
mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))(list_installed)
mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))(test_connection)

# ─── Destructive tools ────────────────────────────────────────
mcp.tool(annotations=ToolAnnotations(destructiveHint=True))(configure_server)
mcp.tool(annotations=ToolAnnotations(destructiveHint=True))(remove_server)
