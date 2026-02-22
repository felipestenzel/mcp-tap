"""list_installed tool -- show configured MCP servers."""

from __future__ import annotations

import re
from pathlib import Path

from mcp.server.fastmcp import Context

from mcp_tap.config.detection import detect_clients, resolve_config_path
from mcp_tap.config.reader import parse_servers, read_config
from mcp_tap.errors import McpTapError
from mcp_tap.models import HttpServerConfig, MCPClient

# Key names that indicate secrets (case-insensitive substring match)
_SECRET_KEY_HINTS: frozenset[str] = frozenset(
    {
        "key",
        "secret",
        "token",
        "password",
        "passwd",
        "credential",
        "api_key",
        "apikey",
        "auth",
        "private",
    }
)

# Value prefixes known to be secrets (provider-specific API key prefixes)
_SECRET_VALUE_PREFIXES: tuple[str, ...] = (
    "sk-",  # OpenAI, Stripe, Anthropic
    "ghp_",  # GitHub personal access token
    "ghs_",  # GitHub server-to-server token
    "gho_",  # GitHub OAuth token
    "github_pat_",  # GitHub fine-grained PAT
    "xoxb-",  # Slack bot token
    "xoxp-",  # Slack user token
    "xapp-",  # Slack app-level token
    "glpat-",  # GitLab personal access token
    "AKIA",  # AWS access key ID
    "eyJ",  # JWT (base64 of {"...)
    "bearer ",  # Bearer token
)

# Fallback: high-entropy strings (base64-like, 40+ chars, no spaces or common path chars)
_HIGH_ENTROPY_PATTERN = re.compile(r"^[A-Za-z0-9+/=_\-]{40,}$")


def _looks_like_secret(key: str, value: str) -> bool:
    """Determine if an env var value is likely a secret.

    Uses a layered approach to reduce false positives:
    1. Known secret key name patterns (KEY, TOKEN, SECRET, etc.)
    2. Known provider-specific value prefixes (sk-, ghp_, xoxb-, etc.)
    3. High-entropy fallback for very long base64-like strings (40+ chars)
    """
    # Layer 1: key name contains secret-like hint
    key_lower = key.lower()
    for hint in _SECRET_KEY_HINTS:
        if hint in key_lower:
            return True

    # Layer 2: value starts with known secret prefix
    for prefix in _SECRET_VALUE_PREFIXES:
        if value.startswith(prefix):
            return True

    # Layer 3: high-entropy fallback (40+ chars, stricter than before)
    return bool(_HIGH_ENTROPY_PATTERN.match(value))


def _mask_env(env: dict[str, str]) -> dict[str, str]:
    """Mask environment variable values that look like secrets."""
    masked: dict[str, str] = {}
    for key, value in env.items():
        if _looks_like_secret(key, value):
            masked[key] = "***"
        else:
            masked[key] = value
    return masked


async def list_installed(
    ctx: Context,
    client: str = "",
) -> list[dict[str, object]]:
    """List all MCP servers currently configured in your AI client.

    Use this to see what servers are already set up before adding new ones
    with configure_server, or to find the exact server name needed for
    test_connection or remove_server.

    Secret-looking environment variable values (API keys, tokens) are
    automatically masked as "***" in the output.

    Args:
        client: Which MCP client's config to read. One of "claude_desktop",
            "claude_code", "cursor", "windsurf". Auto-detects if empty.

    Returns:
        List of configured servers, each with: name, command, args,
        env (masked), and config_file path.
    """
    try:
        if client:
            location = resolve_config_path(MCPClient(client))
        else:
            clients = detect_clients()
            if not clients:
                return [{"message": "No MCP client detected on this machine."}]
            location = clients[0]

        raw = read_config(Path(location.path))
        servers = parse_servers(raw, source_file=location.path)

        result: list[dict[str, object]] = []
        for s in servers:
            if isinstance(s.config, HttpServerConfig):
                result.append(
                    {
                        "name": s.name,
                        "type": s.config.transport_type,
                        "url": s.config.url,
                        "env": _mask_env(dict(s.config.env)),
                        "config_file": s.source_file,
                    }
                )
            else:
                result.append(
                    {
                        "name": s.name,
                        "command": s.config.command,
                        "args": s.config.args,
                        "env": _mask_env(s.config.env),
                        "config_file": s.source_file,
                    }
                )
        return result
    except McpTapError as exc:
        return [{"success": False, "error": str(exc)}]
    except Exception as exc:
        await ctx.error(f"Unexpected error in list_installed: {exc}")
        return [{"success": False, "error": f"Internal error: {type(exc).__name__}"}]
