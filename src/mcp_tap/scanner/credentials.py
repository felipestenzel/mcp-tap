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
    "STRIPE_API_KEY": ["STRIPE_SECRET_KEY", "STRIPE_KEY"],
    "SENTRY_AUTH_TOKEN": ["SENTRY_TOKEN", "SENTRY_API_KEY"],
    "SUPABASE_URL": ["SUPABASE_API_URL"],
    "SUPABASE_KEY": ["SUPABASE_ANON_KEY", "SUPABASE_SERVICE_ROLE_KEY"],
    "FIREBASE_TOKEN": ["FIREBASE_API_KEY"],
    "NOTION_API_KEY": ["NOTION_TOKEN", "NOTION_INTEGRATION_TOKEN"],
    "DATADOG_API_KEY": ["DD_API_KEY", "DATADOG_KEY"],
    "CLOUDFLARE_API_TOKEN": ["CF_API_TOKEN", "CLOUDFLARE_TOKEN"],
    "TWILIO_AUTH_TOKEN": ["TWILIO_TOKEN"],
    "SENDGRID_API_KEY": ["SENDGRID_KEY"],
    "FIGMA_API_KEY": ["FIGMA_TOKEN", "FIGMA_ACCESS_TOKEN"],
    "JIRA_API_TOKEN": ["JIRA_TOKEN", "JIRA_PAT"],
    "CONFLUENCE_API_TOKEN": ["CONFLUENCE_TOKEN", "CONFLUENCE_PAT"],
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
    "STRIPE_API_KEY": "https://dashboard.stripe.com/apikeys",
    "SUPABASE_URL": "https://supabase.com/dashboard/project/_/settings/api",
    "SUPABASE_KEY": "https://supabase.com/dashboard/project/_/settings/api",
    "FIREBASE_TOKEN": "https://console.firebase.google.com/project/_/settings/serviceaccounts/adminsdk",
    "NOTION_API_KEY": "https://www.notion.so/my-integrations",
    "DATADOG_API_KEY": "https://app.datadoghq.com/organization-settings/api-keys",
    "CLOUDFLARE_API_TOKEN": "https://dash.cloudflare.com/profile/api-tokens",
    "TWILIO_AUTH_TOKEN": "https://console.twilio.com/",
    "SENDGRID_API_KEY": "https://app.sendgrid.com/settings/api_keys",
    "FIGMA_API_KEY": "https://www.figma.com/settings#personal-access-tokens",
    "JIRA_API_TOKEN": "https://id.atlassian.com/manage-profile/security/api-tokens",
    "CONFLUENCE_API_TOKEN": "https://id.atlassian.com/manage-profile/security/api-tokens",
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
    "@sentry/mcp-server-sentry": ["SENTRY_AUTH_TOKEN"],
    "@stripe/mcp": ["STRIPE_API_KEY"],
    "@supabase/mcp-server-supabase": ["SUPABASE_URL", "SUPABASE_KEY"],
    "@notionhq/notion-mcp-server": ["NOTION_API_KEY"],
    "mcp-linear": ["LINEAR_API_KEY"],
    "firebase-mcp-server": ["FIREBASE_TOKEN"],
    "datadog-mcp-server": ["DATADOG_API_KEY"],
    "@cloudflare/mcp-server-cloudflare": ["CLOUDFLARE_API_TOKEN"],
    "figma-developer-mcp": ["FIGMA_API_KEY"],
    "@atlassian-dc-mcp/jira": ["JIRA_HOST", "JIRA_API_TOKEN"],
    "@atlassian-dc-mcp/confluence": ["CONFLUENCE_HOST", "CONFLUENCE_API_TOKEN"],
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
        required_vars = reg_vars.get(rec.package_identifier) or SERVER_ENV_VARS.get(
            rec.package_identifier, []
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
