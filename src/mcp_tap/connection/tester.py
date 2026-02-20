"""Test MCP server connections by spawning and probing via the MCP protocol."""

from __future__ import annotations

import asyncio
import logging

from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from mcp_tap.models import ConnectionTestResult, ServerConfig

logger = logging.getLogger(__name__)


async def test_server_connection(
    server_name: str,
    config: ServerConfig,
    *,
    timeout_seconds: int = 15,
) -> ConnectionTestResult:
    """Spawn an MCP server, connect, call list_tools(), and shut down.

    This is the definitive test: if this passes, the server will work
    when the real MCP client runs it.

    Uses ``asyncio.wait_for`` so that on timeout the inner coroutine
    receives ``CancelledError``, triggering ``stdio_client.__aexit__``
    cleanup of the spawned server process.
    """
    params = StdioServerParameters(
        command=config.command,
        args=config.args,
        env=config.env or None,
    )

    try:
        return await asyncio.wait_for(
            _run_connection_test(server_name, params),
            timeout=timeout_seconds,
        )
    except TimeoutError:
        logger.warning(
            "Connection test for '%s' timed out after %ds; process cleanup was attempted",
            server_name,
            timeout_seconds,
        )
        return ConnectionTestResult(
            success=False,
            server_name=server_name,
            error=(
                f"Server did not respond within {timeout_seconds}s "
                "(process cleanup was attempted). "
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


async def _run_connection_test(
    server_name: str,
    params: StdioServerParameters,
) -> ConnectionTestResult:
    """Run the actual connection test inside ``stdio_client`` context.

    Separated so that ``asyncio.wait_for`` can cancel this coroutine on
    timeout, which triggers the async context managers' cleanup paths.
    """
    async with (
        stdio_client(params) as (read_stream, write_stream),
        ClientSession(read_stream, write_stream) as session,
    ):
        await session.initialize()
        tools_result = await session.list_tools()
        tool_names = [t.name for t in tools_result.tools]
        return ConnectionTestResult(
            success=True,
            server_name=server_name,
            tools_discovered=tool_names,
        )
