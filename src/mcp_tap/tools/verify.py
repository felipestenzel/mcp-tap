"""verify tool -- compare lockfile against actual installed state."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from mcp.server.fastmcp import Context

from mcp_tap.config.detection import detect_clients, resolve_config_path
from mcp_tap.config.reader import parse_servers, read_config
from mcp_tap.errors import McpTapError
from mcp_tap.lockfile.differ import diff_lockfile
from mcp_tap.lockfile.reader import read_lockfile
from mcp_tap.models import MCPClient, VerifyResult

_LOCKFILE_NAME = "mcp-tap.lock"


async def verify(
    project_path: str,
    ctx: Context,
    client: str | None = None,
) -> dict[str, object]:
    """Compare the lockfile against the actual installed MCP server state.

    Reads ``mcp-tap.lock`` from the project directory and compares it against
    the servers configured in the target MCP client. Reports drift entries for
    any differences found.

    Args:
        project_path: Root directory of the project containing ``mcp-tap.lock``.
        client: Which MCP client's config to compare against. One of
            ``"claude_desktop"``, ``"claude_code"``, ``"cursor"``, ``"windsurf"``.
            Auto-detects if not specified.

    Returns:
        Verification result with drift entries. ``clean=True`` means no drift
        was detected.
    """
    try:
        path = Path(project_path)
        lockfile_path = path / _LOCKFILE_NAME

        # Read the lockfile
        lockfile = read_lockfile(path)
        if lockfile is None:
            return {
                "success": False,
                "error": f"No lockfile found at {lockfile_path}.",
                "hint": (
                    "Run configure_server with project_path to create one, "
                    "or check that the path is correct."
                ),
            }

        # Resolve the client config
        if client:
            location = resolve_config_path(MCPClient(client))
        else:
            clients = detect_clients()
            if not clients:
                return {
                    "success": False,
                    "error": "No MCP client detected on this machine.",
                }
            location = clients[0]

        # Read installed servers from client config
        raw = read_config(Path(location.path))
        installed = parse_servers(raw, source_file=location.path)

        # Compare lockfile vs installed
        drift = diff_lockfile(lockfile, installed)

        result = VerifyResult(
            lockfile_path=str(lockfile_path),
            total_locked=len(lockfile.servers),
            total_installed=len(installed),
            drift=drift,
            clean=len(drift) == 0,
        )

        output = asdict(result)
        output["client"] = location.client.value
        output["config_file"] = location.path
        return output

    except McpTapError as exc:
        return {"success": False, "error": str(exc)}
    except Exception as exc:
        await ctx.error(f"Unexpected error in verify: {exc}")
        return {"success": False, "error": f"Internal error: {type(exc).__name__}"}
