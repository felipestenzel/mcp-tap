"""configure_server tool -- add an MCP server to your client's config."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from mcp.server.fastmcp import Context

from mcp_tap.config.detection import detect_clients, resolve_config_path
from mcp_tap.config.writer import write_server_config
from mcp_tap.errors import McpTapError
from mcp_tap.installer.resolver import resolve_installer
from mcp_tap.models import ConfigureResult, MCPClient, RegistryType, ServerConfig


async def configure_server(
    server_name: str,
    package_identifier: str,
    ctx: Context,
    client: str = "",
    registry_type: str = "npm",
    env_vars: str = "",
) -> dict[str, object]:
    """Add an MCP server to your AI client's configuration file.

    Generates the correct JSON config and injects it into the config file
    for your MCP client (Claude Desktop, Cursor, Claude Code, Windsurf).

    Args:
        server_name: Name for this server in the config (e.g. "postgres").
        package_identifier: The package to run
            (e.g. "@modelcontextprotocol/server-postgres").
        client: Target MCP client. One of "claude_desktop", "claude_code",
            "cursor", "windsurf". If empty, auto-detects.
        registry_type: Package source -- "npm", "pypi", or "oci".
        env_vars: KEY=VALUE pairs separated by commas for environment
            variables the server needs
            (e.g. "POSTGRES_URL=postgresql://localhost/mydb,API_KEY=sk-...").

    Returns:
        Configuration result showing what was written and where.
    """
    try:
        # Resolve client config path
        if client:
            location = resolve_config_path(MCPClient(client))
        else:
            clients = detect_clients()
            if not clients:
                return asdict(
                    ConfigureResult(
                        success=False,
                        server_name=server_name,
                        config_file="",
                        message=(
                            "No MCP client detected. Install Claude Desktop, "
                            "Cursor, or Claude Code first."
                        ),
                    )
                )
            location = clients[0]

        # Build server config
        rt = RegistryType(registry_type)
        installer = await resolve_installer(rt)
        command, args = installer.build_server_command(package_identifier)

        # Parse env vars
        env: dict[str, str] = {}
        if env_vars:
            for pair in env_vars.split(","):
                pair = pair.strip()
                if "=" in pair:
                    key, value = pair.split("=", 1)
                    env[key.strip()] = value.strip()

        server_config = ServerConfig(command=command, args=args, env=env)

        # Write to config
        write_server_config(
            Path(location.path),
            server_name,
            server_config,
        )

        return asdict(
            ConfigureResult(
                success=True,
                server_name=server_name,
                config_file=location.path,
                message=(
                    f"Server '{server_name}' added to {location.client.value} "
                    f"config at {location.path}. Restart your MCP client to load it."
                ),
                config_written=server_config.to_dict(),
            )
        )
    except McpTapError as exc:
        return asdict(
            ConfigureResult(
                success=False,
                server_name=server_name,
                config_file="",
                message=str(exc),
            )
        )
    except Exception as exc:
        await ctx.error(f"Unexpected error in configure_server: {exc}")
        return asdict(
            ConfigureResult(
                success=False,
                server_name=server_name,
                config_file="",
                message=f"Internal error: {type(exc).__name__}",
            )
        )
