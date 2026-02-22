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


class HttpReachabilityPort(Protocol):
    """Port for checking HTTP MCP server reachability without spawning a process."""

    async def check_reachability(
        self,
        server_name: str,
        url: str,
        *,
        timeout_seconds: int = 10,
    ) -> ConnectionTestResult: ...
