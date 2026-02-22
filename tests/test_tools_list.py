"""Tests for the list_installed MCP tool (tools/list.py)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from mcp_tap.errors import McpTapError
from mcp_tap.models import (
    ConfigLocation,
    HttpServerConfig,
    InstalledServer,
    MCPClient,
    ServerConfig,
)
from mcp_tap.tools.list import _looks_like_secret, _mask_env, list_installed

# --- Helpers ---------------------------------------------------------------


def _make_ctx() -> MagicMock:
    ctx = MagicMock()
    ctx.info = AsyncMock()
    ctx.error = AsyncMock()
    return ctx


def _fake_location(
    client: MCPClient = MCPClient.CLAUDE_CODE,
    path: str = "/tmp/fake_config.json",
) -> ConfigLocation:
    return ConfigLocation(client=client, path=path, scope="user", exists=True)


def _installed_server(
    name: str = "test-server",
    env: dict[str, str] | None = None,
) -> InstalledServer:
    return InstalledServer(
        name=name,
        config=ServerConfig(command="npx", args=["-y", name], env=env or {}),
        source_file="/tmp/fake_config.json",
    )


# --- _mask_env tests -------------------------------------------------------


class TestMaskEnv:
    def test_short_values_not_masked(self):
        env = {"PORT": "3000", "HOST": "localhost"}
        assert _mask_env(env) == {"PORT": "3000", "HOST": "localhost"}

    def test_long_alphanumeric_values_masked(self):
        env = {"API_KEY": "sk_abcdefghijklmnopqrstuvwxyz1234"}
        result = _mask_env(env)
        assert result["API_KEY"] == "***"

    def test_base64_token_masked(self):
        env = {"TOKEN": "eyJhbGciOiJIUzI1NiIs"}
        result = _mask_env(env)
        assert result["TOKEN"] == "***"

    def test_mixed_env(self):
        env = {
            "DEBUG": "true",
            "SECRET": "AAAAAAAAAAAAAAAAAAAAAA",
            "NAME": "my-app",
        }
        result = _mask_env(env)
        assert result["DEBUG"] == "true"
        assert result["SECRET"] == "***"
        assert result["NAME"] == "my-app"

    def test_empty_dict(self):
        assert _mask_env({}) == {}


# --- _looks_like_secret tests (L1 false positive fix) ---------------------


class TestLooksLikeSecret:
    """Test the layered secret detection heuristics."""

    # Layer 1: key name hints
    def test_key_with_token_hint(self):
        assert _looks_like_secret("SLACK_TOKEN", "xoxb-123") is True

    def test_key_with_secret_hint(self):
        assert _looks_like_secret("MY_SECRET", "anyvalue") is True

    def test_key_with_password_hint(self):
        assert _looks_like_secret("DB_PASSWORD", "short") is True

    def test_key_with_api_key_hint(self):
        assert _looks_like_secret("OPENAI_API_KEY", "sk-abc") is True

    def test_key_with_auth_hint(self):
        assert _looks_like_secret("AUTH_HEADER", "value") is True

    def test_key_with_credential_hint(self):
        assert _looks_like_secret("GCP_CREDENTIAL", "json") is True

    def test_key_with_private_hint(self):
        assert _looks_like_secret("PRIVATE_KEY", "pem") is True

    # Layer 2: value prefixes
    def test_openai_prefix(self):
        assert _looks_like_secret("SOME_VAR", "sk-abc123") is True

    def test_github_pat_prefix(self):
        assert _looks_like_secret("GH", "ghp_abcdefg123456") is True

    def test_github_server_token_prefix(self):
        assert _looks_like_secret("GH", "ghs_abcdefg123456") is True

    def test_github_fine_grained_prefix(self):
        assert _looks_like_secret("GH", "github_pat_abc123") is True

    def test_slack_bot_prefix(self):
        assert _looks_like_secret("SLACK", "xoxb-123-456") is True

    def test_slack_user_prefix(self):
        assert _looks_like_secret("SLACK", "xoxp-123-456") is True

    def test_gitlab_pat_prefix(self):
        assert _looks_like_secret("GL", "glpat-abcdef123") is True

    def test_aws_access_key_prefix(self):
        assert _looks_like_secret("AWS", "AKIAIOSFODNN7EXAMPLE") is True

    def test_jwt_prefix(self):
        assert _looks_like_secret("DATA", "eyJhbGciOiJIUzI1NiIs") is True

    def test_bearer_prefix(self):
        assert _looks_like_secret("HEADER", "bearer mytoken123") is True

    # Layer 3: high-entropy fallback (40+ chars)
    def test_long_base64_string(self):
        long_val = "A" * 40
        assert _looks_like_secret("UNKNOWN", long_val) is True

    def test_39_chars_not_masked(self):
        """39 chars is under the 40-char threshold."""
        val = "A" * 39
        assert _looks_like_secret("UNKNOWN", val) is False

    # False positive prevention
    def test_normal_path_not_masked(self):
        """Paths with slashes are not caught by high-entropy pattern."""
        assert _looks_like_secret("NODE_PATH", "/usr/local/bin/node") is False

    def test_normal_url_not_masked(self):
        assert _looks_like_secret("DATABASE_HOST", "postgresql://localhost:5432/mydb") is False

    def test_short_normal_value_not_masked(self):
        assert _looks_like_secret("PORT", "3000") is False

    def test_normal_string_value_not_masked(self):
        assert _looks_like_secret("APP_NAME", "my-cool-application") is False

    def test_medium_length_value_not_masked(self):
        """25-char values should NOT be masked if key is not secret-like."""
        assert _looks_like_secret("REGION", "us-east-1-long-region-name") is False

    def test_production_host_not_masked(self):
        assert _looks_like_secret("HOST", "production-db-server-host.example.com") is False

    # Key name hint is case-insensitive
    def test_key_hint_case_insensitive(self):
        assert _looks_like_secret("My_Api_Key", "somevalue") is True
        assert _looks_like_secret("GITHUB_TOKEN", "somevalue") is True


# --- list_installed tests --------------------------------------------------


class TestListInstalled:
    @patch("mcp_tap.tools.list.parse_servers")
    @patch("mcp_tap.tools.list.read_config")
    @patch("mcp_tap.tools.list.resolve_config_path")
    async def test_explicit_client(self, mock_resolve, mock_read, mock_parse):
        mock_resolve.return_value = _fake_location()
        mock_read.return_value = {"mcpServers": {}}
        server = _installed_server("my-server", env={"PORT": "8080"})
        mock_parse.return_value = [server]

        result = await list_installed(_make_ctx(), client="claude_code")

        assert len(result) == 1
        assert result[0]["name"] == "my-server"
        assert result[0]["command"] == "npx"
        assert result[0]["args"] == ["-y", "my-server"]
        assert result[0]["env"] == {"PORT": "8080"}
        mock_resolve.assert_called_once_with(MCPClient("claude_code"))

    @patch("mcp_tap.tools.list.parse_servers")
    @patch("mcp_tap.tools.list.read_config")
    @patch("mcp_tap.tools.list.detect_clients")
    async def test_auto_detect_client(self, mock_detect, mock_read, mock_parse):
        mock_detect.return_value = [_fake_location()]
        mock_read.return_value = {"mcpServers": {}}
        mock_parse.return_value = [_installed_server()]

        result = await list_installed(_make_ctx())

        assert len(result) == 1
        assert result[0]["name"] == "test-server"
        mock_detect.assert_called_once()

    @patch("mcp_tap.tools.list.detect_clients")
    async def test_no_client_detected(self, mock_detect):
        mock_detect.return_value = []

        result = await list_installed(_make_ctx())

        assert len(result) == 1
        assert result[0]["message"] == "No MCP client detected on this machine."

    @patch("mcp_tap.tools.list.parse_servers")
    @patch("mcp_tap.tools.list.read_config")
    @patch("mcp_tap.tools.list.detect_clients")
    async def test_empty_config(self, mock_detect, mock_read, mock_parse):
        mock_detect.return_value = [_fake_location()]
        mock_read.return_value = {"mcpServers": {}}
        mock_parse.return_value = []

        result = await list_installed(_make_ctx())

        assert result == []

    @patch("mcp_tap.tools.list.parse_servers")
    @patch("mcp_tap.tools.list.read_config")
    @patch("mcp_tap.tools.list.detect_clients")
    async def test_secrets_masked_in_output(self, mock_detect, mock_read, mock_parse):
        mock_detect.return_value = [_fake_location()]
        mock_read.return_value = {"mcpServers": {}}
        mock_parse.return_value = [
            _installed_server("s", env={"API_KEY": "sk_abcdefghijklmnopqrstuvwxyz"})
        ]

        result = await list_installed(_make_ctx())

        assert result[0]["env"]["API_KEY"] == "***"

    @patch("mcp_tap.tools.list.parse_servers")
    @patch("mcp_tap.tools.list.read_config")
    @patch("mcp_tap.tools.list.detect_clients")
    async def test_multiple_servers(self, mock_detect, mock_read, mock_parse):
        mock_detect.return_value = [_fake_location()]
        mock_read.return_value = {"mcpServers": {}}
        mock_parse.return_value = [
            _installed_server("server-a"),
            _installed_server("server-b"),
        ]

        result = await list_installed(_make_ctx())

        assert len(result) == 2
        names = {r["name"] for r in result}
        assert names == {"server-a", "server-b"}

    @patch("mcp_tap.tools.list.resolve_config_path")
    async def test_mcp_tap_error_returns_error_dict(self, mock_resolve):
        mock_resolve.side_effect = McpTapError("Config broken")

        result = await list_installed(_make_ctx(), client="claude_code")

        assert len(result) == 1
        assert result[0]["success"] is False
        assert "Config broken" in result[0]["error"]

    @patch("mcp_tap.tools.list.resolve_config_path")
    async def test_unexpected_error_returns_error_dict(self, mock_resolve):
        mock_resolve.side_effect = RuntimeError("boom")
        ctx = _make_ctx()

        result = await list_installed(ctx, client="claude_code")

        assert len(result) == 1
        assert result[0]["success"] is False
        assert "RuntimeError" in result[0]["error"]
        ctx.error.assert_awaited_once()


# --- HTTP Server Config in list output ----------------------------------------


def _http_installed_server(
    name: str = "vercel",
    url: str = "https://mcp.vercel.com",
    transport_type: str = "http",
    env: dict[str, str] | None = None,
) -> InstalledServer:
    return InstalledServer(
        name=name,
        config=HttpServerConfig(url=url, transport_type=transport_type, env=env or {}),
        source_file="/tmp/fake_config.json",
    )


class TestListInstalledHttpServers:
    """Tests for list_installed output format with HTTP servers."""

    @patch("mcp_tap.tools.list.parse_servers")
    @patch("mcp_tap.tools.list.read_config")
    @patch("mcp_tap.tools.list.detect_clients")
    async def test_http_server_has_type_and_url(self, mock_detect, mock_read, mock_parse):
        """HTTP server output should have type and url, not command and args."""
        mock_detect.return_value = [_fake_location()]
        mock_read.return_value = {"mcpServers": {}}
        mock_parse.return_value = [_http_installed_server()]

        result = await list_installed(_make_ctx())

        assert len(result) == 1
        assert result[0]["name"] == "vercel"
        assert result[0]["type"] == "http"
        assert result[0]["url"] == "https://mcp.vercel.com"
        # Should NOT have command/args keys
        assert "command" not in result[0]
        assert "args" not in result[0]

    @patch("mcp_tap.tools.list.parse_servers")
    @patch("mcp_tap.tools.list.read_config")
    @patch("mcp_tap.tools.list.detect_clients")
    async def test_http_server_sse_type(self, mock_detect, mock_read, mock_parse):
        """SSE server should report type='sse'."""
        mock_detect.return_value = [_fake_location()]
        mock_read.return_value = {"mcpServers": {}}
        mock_parse.return_value = [
            _http_installed_server("sse-srv", "https://sse.example.com", transport_type="sse")
        ]

        result = await list_installed(_make_ctx())

        assert result[0]["type"] == "sse"

    @patch("mcp_tap.tools.list.parse_servers")
    @patch("mcp_tap.tools.list.read_config")
    @patch("mcp_tap.tools.list.detect_clients")
    async def test_http_server_env_masked(self, mock_detect, mock_read, mock_parse):
        """HTTP server env vars should be masked like stdio servers."""
        mock_detect.return_value = [_fake_location()]
        mock_read.return_value = {"mcpServers": {}}
        mock_parse.return_value = [
            _http_installed_server(env={"API_KEY": "sk_abcdefghijklmnopqrstuvwxyz"})
        ]

        result = await list_installed(_make_ctx())

        assert result[0]["env"]["API_KEY"] == "***"

    @patch("mcp_tap.tools.list.parse_servers")
    @patch("mcp_tap.tools.list.read_config")
    @patch("mcp_tap.tools.list.detect_clients")
    async def test_stdio_server_still_has_command_args(self, mock_detect, mock_read, mock_parse):
        """Stdio server output should still have command and args (no regression)."""
        mock_detect.return_value = [_fake_location()]
        mock_read.return_value = {"mcpServers": {}}
        mock_parse.return_value = [_installed_server("pg-mcp")]

        result = await list_installed(_make_ctx())

        assert result[0]["command"] == "npx"
        assert result[0]["args"] == ["-y", "pg-mcp"]
        assert "type" not in result[0]
        assert "url" not in result[0]

    @patch("mcp_tap.tools.list.parse_servers")
    @patch("mcp_tap.tools.list.read_config")
    @patch("mcp_tap.tools.list.detect_clients")
    async def test_mixed_http_and_stdio_servers(self, mock_detect, mock_read, mock_parse):
        """Should handle mixed HTTP and stdio server entries."""
        mock_detect.return_value = [_fake_location()]
        mock_read.return_value = {"mcpServers": {}}
        mock_parse.return_value = [
            _installed_server("pg-mcp"),
            _http_installed_server("vercel"),
        ]

        result = await list_installed(_make_ctx())

        assert len(result) == 2
        stdio = next(r for r in result if r["name"] == "pg-mcp")
        http = next(r for r in result if r["name"] == "vercel")
        assert "command" in stdio
        assert "url" in http
