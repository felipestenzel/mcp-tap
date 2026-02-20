"""Port: MCP server connection testing."""

from __future__ import annotations

from typing import Protocol

from mcp_tap.models import ConnectionTestResult, ServerConfig


class ConnectionTesterPort(Protocol):
    """Port for testing MCP server connections."""

    async def test_server_connection(
        self,
        server_name: str,
        config: ServerConfig,
        *,
        timeout_seconds: int = 15,
    ) -> ConnectionTestResult:
        """Spawn an MCP server, connect via stdio, and call list_tools()."""
        ...
