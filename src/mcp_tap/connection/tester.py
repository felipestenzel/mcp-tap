"""Test MCP server connections by spawning and probing via the MCP protocol."""

from __future__ import annotations

import asyncio

from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from mcp_tap.models import ConnectionTestResult, ServerConfig


async def test_server_connection(
    server_name: str,
    config: ServerConfig,
    *,
    timeout_seconds: int = 15,
) -> ConnectionTestResult:
    """Spawn an MCP server, connect, call list_tools(), and shut down.

    This is the definitive test: if this passes, the server will work
    when the real MCP client runs it.
    """
    params = StdioServerParameters(
        command=config.command,
        args=config.args,
        env=config.env or None,
    )

    try:
        async with asyncio.timeout(timeout_seconds):
            async with stdio_client(params) as (read_stream, write_stream):
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    tools_result = await session.list_tools()
                    tool_names = [t.name for t in tools_result.tools]
                    return ConnectionTestResult(
                        success=True,
                        server_name=server_name,
                        tools_discovered=tool_names,
                    )
    except TimeoutError:
        return ConnectionTestResult(
            success=False,
            server_name=server_name,
            error=(
                f"Server did not respond within {timeout_seconds}s. "
                "Check that the command exists, required env vars are set, "
                "and the server supports stdio transport."
            ),
        )
    except FileNotFoundError as exc:
        return ConnectionTestResult(
            success=False,
            server_name=server_name,
            error=f"Command not found: {exc.filename}. Is the package installed?",
        )
    except Exception as exc:
        return ConnectionTestResult(
            success=False,
            server_name=server_name,
            error=f"{type(exc).__name__}: {exc}",
        )
