"""Tests for scanner/credentials.py -- credential detection and mapping."""

from __future__ import annotations

from mcp_tap.models import CredentialMapping, RegistryType, ServerRecommendation
from mcp_tap.scanner.credentials import (
    COMPATIBLE_VARS,
    CREDENTIAL_HELP,
    SERVER_ENV_VARS,
    map_credentials,
)


def _rec(name: str, pkg: str) -> ServerRecommendation:
    """Shorthand to build a ServerRecommendation."""
    return ServerRecommendation(
        server_name=name,
        package_identifier=pkg,
        registry_type=RegistryType.NPM,
        reason="test",
        priority="high",
    )


# ─── Exact match ─────────────────────────────────────────────


class TestExactMatch:
    def test_exact_match_slack_token(self) -> None:
        rec = _rec("slack-mcp", "@modelcontextprotocol/server-slack")
        mappings = map_credentials([rec], ["SLACK_BOT_TOKEN"])
        assert len(mappings) == 1
        assert mappings[0].status == "exact_match"
        assert mappings[0].available_env_var == "SLACK_BOT_TOKEN"
        assert mappings[0].source == ".env"

    def test_exact_match_github_token(self) -> None:
        rec = _rec("github-mcp", "@modelcontextprotocol/server-github")
        mappings = map_credentials([rec], ["GITHUB_TOKEN"])
        assert len(mappings) == 1
        assert mappings[0].status == "exact_match"
        assert mappings[0].available_env_var == "GITHUB_TOKEN"

    def test_exact_match_postgres(self) -> None:
        rec = _rec("postgres-mcp", "@modelcontextprotocol/server-postgres")
        mappings = map_credentials([rec], ["POSTGRES_CONNECTION_STRING"])
        assert len(mappings) == 1
        assert mappings[0].status == "exact_match"


# ─── Compatible match ────────────────────────────────────────


class TestCompatibleMatch:
    def test_database_url_matches_postgres(self) -> None:
        rec = _rec("postgres-mcp", "@modelcontextprotocol/server-postgres")
        mappings = map_credentials([rec], ["DATABASE_URL"])
        assert len(mappings) == 1
        assert mappings[0].status == "compatible_match"
        assert mappings[0].available_env_var == "DATABASE_URL"

    def test_gh_token_matches_github(self) -> None:
        rec = _rec("github-mcp", "@modelcontextprotocol/server-github")
        mappings = map_credentials([rec], ["GH_TOKEN"])
        assert len(mappings) == 1
        assert mappings[0].status == "compatible_match"
        assert mappings[0].available_env_var == "GH_TOKEN"

    def test_mongo_url_matches_mongodb(self) -> None:
        rec = _rec("mongo-mcp", "mcp-server-mongodb")
        mappings = map_credentials([rec], ["MONGO_URL"])
        assert len(mappings) == 1
        assert mappings[0].status == "compatible_match"
        assert mappings[0].available_env_var == "MONGO_URL"


# ─── Missing ─────────────────────────────────────────────────


class TestMissing:
    def test_missing_no_env_vars(self) -> None:
        rec = _rec("github-mcp", "@modelcontextprotocol/server-github")
        mappings = map_credentials([rec], [])
        assert len(mappings) == 1
        assert mappings[0].status == "missing"
        assert mappings[0].available_env_var is None
        assert mappings[0].source == "not found"

    def test_missing_with_unrelated_vars(self) -> None:
        rec = _rec("slack-mcp", "@modelcontextprotocol/server-slack")
        mappings = map_credentials([rec], ["DATABASE_URL", "REDIS_URL"])
        assert len(mappings) == 1
        assert mappings[0].status == "missing"

    def test_missing_has_help_url(self) -> None:
        rec = _rec("github-mcp", "@modelcontextprotocol/server-github")
        mappings = map_credentials([rec], [])
        assert mappings[0].help_url == "https://github.com/settings/tokens/new"


# ─── Help URLs ───────────────────────────────────────────────


class TestHelpUrls:
    def test_github_help_url(self) -> None:
        rec = _rec("github-mcp", "@modelcontextprotocol/server-github")
        mappings = map_credentials([rec], [])
        assert mappings[0].help_url != ""

    def test_slack_help_url(self) -> None:
        rec = _rec("slack-mcp", "@modelcontextprotocol/server-slack")
        mappings = map_credentials([rec], [])
        assert mappings[0].help_url == "https://api.slack.com/apps"


# ─── Registry env vars override ──────────────────────────────


class TestRegistryOverride:
    def test_registry_env_vars_take_precedence(self) -> None:
        rec = _rec("custom-server", "custom-pkg")
        reg_vars = {"custom-pkg": ["MY_CUSTOM_KEY"]}
        mappings = map_credentials([rec], ["MY_CUSTOM_KEY"], reg_vars)
        assert len(mappings) == 1
        assert mappings[0].status == "exact_match"
        assert mappings[0].required_env_var == "MY_CUSTOM_KEY"

    def test_unknown_server_no_env_vars(self) -> None:
        rec = _rec("unknown-server", "unknown-pkg")
        mappings = map_credentials([rec], ["FOO"])
        assert len(mappings) == 0  # No required vars known


# ─── Multiple servers ────────────────────────────────────────


class TestMultipleServers:
    def test_multiple_recommendations(self) -> None:
        recs = [
            _rec("postgres-mcp", "@modelcontextprotocol/server-postgres"),
            _rec("github-mcp", "@modelcontextprotocol/server-github"),
        ]
        mappings = map_credentials(recs, ["DATABASE_URL", "GITHUB_TOKEN"])
        assert len(mappings) == 2
        pg = next(m for m in mappings if m.server_name == "postgres-mcp")
        gh = next(m for m in mappings if m.server_name == "github-mcp")
        assert pg.status == "compatible_match"
        assert gh.status == "exact_match"


# ─── Static data validation ──────────────────────────────────


class TestStaticData:
    def test_compatible_vars_has_entries(self) -> None:
        assert len(COMPATIBLE_VARS) >= 6

    def test_credential_help_has_entries(self) -> None:
        assert len(CREDENTIAL_HELP) >= 4

    def test_server_env_vars_has_entries(self) -> None:
        assert len(SERVER_ENV_VARS) >= 3

    def test_credential_mapping_is_frozen(self) -> None:
        m = CredentialMapping(
            server_name="test",
            required_env_var="FOO",
        )
        try:
            m.server_name = "changed"  # type: ignore[misc]
            raise AssertionError("Should have raised FrozenInstanceError")
        except AttributeError:
            pass
