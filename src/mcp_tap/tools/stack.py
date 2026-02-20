"""apply_stack tool -- install a group of MCP servers from a stack definition."""

from __future__ import annotations

import logging

from mcp.server.fastmcp import Context

from mcp_tap.errors import McpTapError
from mcp_tap.stacks.loader import list_builtin_stacks, load_stack
from mcp_tap.tools.configure import configure_server

logger = logging.getLogger(__name__)


async def apply_stack(
    stack: str,
    ctx: Context,
    clients: str = "",
    scope: str = "user",
    project_path: str = "",
    dry_run: bool = False,
) -> dict[str, object]:
    """Install a group of MCP servers from a stack definition.

    Stacks are shareable profiles that bundle multiple MCP servers together.
    Use a built-in stack name or a path to a .yaml file.

    Built-in stacks: data-science, web-dev, devops.
    Use dry_run=True to preview what would be installed without making changes.

    Args:
        stack: Built-in stack name (e.g. "data-science") or path to .yaml file.
        clients: Target MCP client(s). Same as configure_server.
        scope: "user" or "project". Same as configure_server.
        project_path: Project directory path. Required when scope="project".
        dry_run: If True, only show what would be installed without installing.

    Returns:
        Result with: stack_name, servers_total, servers_installed, servers_failed,
        per_server_results, and any env_vars_needed.
    """
    try:
        stack_def = load_stack(stack)
    except McpTapError as exc:
        return {
            "success": False,
            "error": str(exc),
            "available_stacks": list_builtin_stacks(),
        }

    if not stack_def.servers:
        return {
            "success": False,
            "error": f"Stack '{stack_def.name}' has no servers defined.",
        }

    # Collect env vars needed across all servers
    env_vars_needed: list[str] = []
    for srv in stack_def.servers:
        env_vars_needed.extend(srv.env_vars)

    if dry_run:
        return {
            "success": True,
            "dry_run": True,
            "stack_name": stack_def.name,
            "description": stack_def.description,
            "servers_total": len(stack_def.servers),
            "servers": [
                {
                    "name": s.name,
                    "package": s.package_identifier,
                    "registry": s.registry_type,
                    "env_vars_needed": s.env_vars,
                }
                for s in stack_def.servers
            ],
            "env_vars_needed": sorted(set(env_vars_needed)),
        }

    # Install each server sequentially
    await ctx.info(f"Applying stack '{stack_def.name}' ({len(stack_def.servers)} servers)...")

    results: list[dict[str, object]] = []
    installed = 0
    failed = 0

    for srv in stack_def.servers:
        await ctx.info(f"Installing {srv.name} ({srv.package_identifier})...")
        try:
            result = await configure_server(
                server_name=srv.name,
                package_identifier=srv.package_identifier,
                ctx=ctx,
                clients=clients,
                registry_type=srv.registry_type,
                version=srv.version,
                scope=scope,
                project_path=project_path,
            )
            results.append({"server": srv.name, **result})
            if result.get("success"):
                installed += 1
            else:
                failed += 1
        except Exception as exc:
            results.append(
                {
                    "server": srv.name,
                    "success": False,
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
            failed += 1

    return {
        "success": installed > 0,
        "stack_name": stack_def.name,
        "description": stack_def.description,
        "servers_total": len(stack_def.servers),
        "servers_installed": installed,
        "servers_failed": failed,
        "per_server_results": results,
        "env_vars_needed": sorted(set(env_vars_needed)),
    }
