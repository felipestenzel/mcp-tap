"""Credential detection and mapping for MCP server recommendations."""

from __future__ import annotations

from mcp_tap.models import CredentialMapping, ServerRecommendation

# ─── Compatibility mapping ───────────────────────────────────
# Required env var → list of compatible alternatives that projects commonly use.

COMPATIBLE_VARS: dict[str, list[str]] = {
    "POSTGRES_CONNECTION_STRING": [
        "DATABASE_URL",
        "POSTGRES_URL",
        "PG_URL",
        "PG_CONNECTION_STRING",
        "POSTGRESQL_URL",
    ],
    "GITHUB_TOKEN": ["GH_TOKEN", "GITHUB_PERSONAL_ACCESS_TOKEN", "GITHUB_PAT"],
    "SLACK_BOT_TOKEN": ["SLACK_TOKEN", "SLACK_API_TOKEN"],
    "REDIS_URL": ["REDIS_CONNECTION_STRING", "REDIS_HOST"],
    "MONGODB_URI": ["MONGO_URL", "MONGODB_URL", "MONGO_URI"],
    "MYSQL_CONNECTION_STRING": ["MYSQL_URL", "DATABASE_URL"],
    "OPENAI_API_KEY": ["OPENAI_KEY"],
    "ANTHROPIC_API_KEY": ["ANTHROPIC_KEY", "CLAUDE_API_KEY"],
    "GITLAB_TOKEN": ["GITLAB_PERSONAL_ACCESS_TOKEN", "GL_TOKEN"],
    "LINEAR_API_KEY": ["LINEAR_TOKEN"],
}

# ─── Help URL mapping ────────────────────────────────────────
# Env var pattern → URL where the user can create/find the credential.

CREDENTIAL_HELP: dict[str, str] = {
    "GITHUB_TOKEN": "https://github.com/settings/tokens/new",
    "GITLAB_TOKEN": "https://gitlab.com/-/user_settings/personal_access_tokens",
    "SLACK_BOT_TOKEN": "https://api.slack.com/apps",
    "OPENAI_API_KEY": "https://platform.openai.com/api-keys",
    "ANTHROPIC_API_KEY": "https://console.anthropic.com/settings/keys",
    "LINEAR_API_KEY": "https://linear.app/settings/api",
    "SENTRY_AUTH_TOKEN": "https://sentry.io/settings/auth-tokens/",
}

# ─── Server → required env vars ──────────────────────────────
# Static mapping of known MCP server packages to their required env vars.
# This supplements (not replaces) registry data.

SERVER_ENV_VARS: dict[str, list[str]] = {
    "@modelcontextprotocol/server-postgres": ["POSTGRES_CONNECTION_STRING"],
    "@modelcontextprotocol/server-github": ["GITHUB_TOKEN"],
    "@modelcontextprotocol/server-gitlab": ["GITLAB_TOKEN"],
    "@modelcontextprotocol/server-slack": ["SLACK_BOT_TOKEN"],
    "mcp-server-redis": ["REDIS_URL"],
    "mcp-server-mongodb": ["MONGODB_URI"],
}


def _find_help_url(env_var: str) -> str:
    """Find a help URL for a given env var name."""
    if env_var in CREDENTIAL_HELP:
        return CREDENTIAL_HELP[env_var]
    # Check if any key is a prefix match (e.g. GITHUB_TOKEN matches GITHUB_*)
    for key, url in CREDENTIAL_HELP.items():
        if env_var.startswith(key.split("_")[0]):
            return url
    return ""


def _match_env_var(
    required: str,
    available_vars: list[str],
) -> tuple[str | None, str]:
    """Match a required env var against available project env vars.

    Returns (matched_var, status) where status is one of:
    "exact_match", "compatible_match", "missing".
    """
    # Exact match
    if required in available_vars:
        return required, "exact_match"

    # Compatible match via lookup table
    compatible = COMPATIBLE_VARS.get(required, [])
    for alt in compatible:
        if alt in available_vars:
            return alt, "compatible_match"

    # Reverse lookup: maybe 'required' is itself a compatible name for something
    for canonical, alternatives in COMPATIBLE_VARS.items():
        if required in alternatives and canonical in available_vars:
            return canonical, "compatible_match"

    return None, "missing"


def map_credentials(
    recommendations: list[ServerRecommendation],
    available_env_vars: list[str],
    registry_env_vars: dict[str, list[str]] | None = None,
) -> list[CredentialMapping]:
    """Map server recommendations to available project credentials.

    For each recommended server, check which required env vars are available
    in the project (exact match or compatible match) and which are missing.

    Args:
        recommendations: Server recommendations from scan_project.
        available_env_vars: Env var names found in the project (.env files).
        registry_env_vars: Optional mapping of package_identifier → required
            env var names from the registry. Supplements SERVER_ENV_VARS.

    Returns:
        List of CredentialMapping, one per required env var per server.
    """
    reg_vars = registry_env_vars or {}
    mappings: list[CredentialMapping] = []

    for rec in recommendations:
        # Determine required env vars from static map or registry data
        required_vars = (
            reg_vars.get(rec.package_identifier)
            or SERVER_ENV_VARS.get(rec.package_identifier, [])
        )

        for required in required_vars:
            matched_var, status = _match_env_var(required, available_env_vars)
            source = ".env" if matched_var else "not found"
            mappings.append(
                CredentialMapping(
                    server_name=rec.server_name,
                    required_env_var=required,
                    available_env_var=matched_var,
                    source=source,
                    status=status,
                    help_url=_find_help_url(required),
                )
            )

    return mappings
