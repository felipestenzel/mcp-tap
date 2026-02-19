"""Tests for the scan_project MCP tool (tools/scan.py)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from mcp_tap.models import ConfigLocation, MCPClient
from mcp_tap.tools.scan import _build_summary, _get_installed_server_names, scan_project

# ─── Fixture paths ───────────────────────────────────────────

FIXTURES_DIR = Path(__file__).parent / "fixtures"
PYTHON_FASTAPI = FIXTURES_DIR / "python_fastapi_project"
NODE_EXPRESS = FIXTURES_DIR / "node_express_project"
MINIMAL = FIXTURES_DIR / "minimal_project"
EMPTY = FIXTURES_DIR / "empty_project"


# ─── Helpers ─────────────────────────────────────────────────


def _make_ctx() -> MagicMock:
    """Build a mock Context with async info/error methods."""
    ctx = MagicMock()
    ctx.info = AsyncMock()
    ctx.error = AsyncMock()
    return ctx


def _fake_location(
    client: MCPClient = MCPClient.CLAUDE_CODE,
    path: str = "/tmp/fake_config.json",
    exists: bool = True,
) -> ConfigLocation:
    return ConfigLocation(client=client, path=path, scope="user", exists=exists)


# ═══════════════════════════════════════════════════════════════
# scan_project Tool Tests
# ═══════════════════════════════════════════════════════════════


class TestScanReturnsTechnologies:
    """Tests that scan_project detects technologies from fixture projects."""

    @patch("mcp_tap.tools.scan._get_installed_server_names", return_value=set())
    async def test_python_fastapi_project(self, _mock_installed: MagicMock):
        """Should detect Python, FastAPI, PostgreSQL, Redis from fixture."""
        ctx = _make_ctx()
        result = await scan_project(ctx, path=str(PYTHON_FASTAPI))

        assert "detected_technologies" in result
        tech_names = {t["name"] for t in result["detected_technologies"]}
        assert "python" in tech_names
        assert "fastapi" in tech_names
        assert "postgresql" in tech_names
        assert "redis" in tech_names

    @patch("mcp_tap.tools.scan._get_installed_server_names", return_value=set())
    async def test_node_express_project(self, _mock_installed: MagicMock):
        """Should detect Node.js, Express, PostgreSQL from fixture."""
        ctx = _make_ctx()
        result = await scan_project(ctx, path=str(NODE_EXPRESS))

        tech_names = {t["name"] for t in result["detected_technologies"]}
        assert "node.js" in tech_names
        assert "express" in tech_names
        assert "postgresql" in tech_names

    @patch("mcp_tap.tools.scan._get_installed_server_names", return_value=set())
    async def test_technologies_have_category_as_string(self, _mock_installed: MagicMock):
        """Should serialize category as a plain string, not StrEnum."""
        ctx = _make_ctx()
        result = await scan_project(ctx, path=str(PYTHON_FASTAPI))

        for tech in result["detected_technologies"]:
            assert isinstance(tech["category"], str)
            assert tech["category"] in ("language", "framework", "database", "service", "platform")


class TestScanReturnsRecommendations:
    """Tests that scan_project populates recommendations."""

    @patch("mcp_tap.tools.scan._get_installed_server_names", return_value=set())
    async def test_recommendations_populated(self, _mock_installed: MagicMock):
        """Should return non-empty recommendations for a real project."""
        ctx = _make_ctx()
        result = await scan_project(ctx, path=str(PYTHON_FASTAPI))

        assert "recommendations" in result
        assert len(result["recommendations"]) > 0

    @patch("mcp_tap.tools.scan._get_installed_server_names", return_value=set())
    async def test_postgres_recommendation_present(self, _mock_installed: MagicMock):
        """Should recommend postgres-mcp for a project with PostgreSQL."""
        ctx = _make_ctx()
        result = await scan_project(ctx, path=str(PYTHON_FASTAPI))

        rec_names = {r["server_name"] for r in result["recommendations"]}
        assert "postgres-mcp" in rec_names

    @patch("mcp_tap.tools.scan._get_installed_server_names", return_value=set())
    async def test_filesystem_always_recommended(self, _mock_installed: MagicMock):
        """Should always include filesystem-mcp recommendation."""
        ctx = _make_ctx()
        result = await scan_project(ctx, path=str(MINIMAL))

        rec_names = {r["server_name"] for r in result["recommendations"]}
        assert "filesystem-mcp" in rec_names

    @patch("mcp_tap.tools.scan._get_installed_server_names", return_value=set())
    async def test_recommendations_have_already_installed_field(
        self,
        _mock_installed: MagicMock,
    ):
        """Should add 'already_installed' boolean to each recommendation."""
        ctx = _make_ctx()
        result = await scan_project(ctx, path=str(PYTHON_FASTAPI))

        for rec in result["recommendations"]:
            assert "already_installed" in rec
            assert isinstance(rec["already_installed"], bool)

    @patch("mcp_tap.tools.scan._get_installed_server_names", return_value=set())
    async def test_recommendations_have_registry_type_as_string(
        self,
        _mock_installed: MagicMock,
    ):
        """Should serialize registry_type as a plain string."""
        ctx = _make_ctx()
        result = await scan_project(ctx, path=str(PYTHON_FASTAPI))

        for rec in result["recommendations"]:
            assert isinstance(rec["registry_type"], str)
            assert rec["registry_type"] in ("npm", "pypi", "oci")


class TestScanReturnsEnvVars:
    """Tests that scan_project extracts environment variables."""

    @patch("mcp_tap.tools.scan._get_installed_server_names", return_value=set())
    async def test_env_vars_from_python_project(self, _mock_installed: MagicMock):
        """Should extract env var names from .env.example."""
        ctx = _make_ctx()
        result = await scan_project(ctx, path=str(PYTHON_FASTAPI))

        assert "env_vars_found" in result
        assert "DATABASE_URL" in result["env_vars_found"]
        assert "REDIS_URL" in result["env_vars_found"]
        assert "SLACK_BOT_TOKEN" in result["env_vars_found"]

    @patch("mcp_tap.tools.scan._get_installed_server_names", return_value=set())
    async def test_env_vars_from_node_project(self, _mock_installed: MagicMock):
        """Should extract env var names from .env file."""
        ctx = _make_ctx()
        result = await scan_project(ctx, path=str(NODE_EXPRESS))

        assert "DATABASE_URL" in result["env_vars_found"]
        assert "GITHUB_TOKEN" in result["env_vars_found"]


class TestScanMarksAlreadyInstalled:
    """Tests that scan cross-references with installed servers."""

    @patch(
        "mcp_tap.tools.scan._get_installed_server_names",
        return_value={"postgres-mcp", "redis-mcp"},
    )
    async def test_marks_installed_servers(self, _mock_installed: MagicMock):
        """Should mark matching recommendations as already_installed=True."""
        ctx = _make_ctx()
        result = await scan_project(ctx, path=str(PYTHON_FASTAPI))

        installed_map = {
            r["server_name"]: r["already_installed"] for r in result["recommendations"]
        }
        assert installed_map.get("postgres-mcp") is True
        assert installed_map.get("redis-mcp") is True

    @patch(
        "mcp_tap.tools.scan._get_installed_server_names",
        return_value={"postgres-mcp"},
    )
    async def test_marks_non_installed_servers(self, _mock_installed: MagicMock):
        """Should mark non-installed recommendations as already_installed=False."""
        ctx = _make_ctx()
        result = await scan_project(ctx, path=str(PYTHON_FASTAPI))

        installed_map = {
            r["server_name"]: r["already_installed"] for r in result["recommendations"]
        }
        # filesystem-mcp is not in the installed set
        assert installed_map.get("filesystem-mcp") is False

    @patch(
        "mcp_tap.tools.scan._get_installed_server_names",
        return_value={"postgres-mcp", "redis-mcp"},
    )
    async def test_already_installed_list_populated(self, _mock_installed: MagicMock):
        """Should populate the top-level 'already_installed' list."""
        ctx = _make_ctx()
        result = await scan_project(ctx, path=str(PYTHON_FASTAPI))

        assert "already_installed" in result
        assert "postgres-mcp" in result["already_installed"]
        assert "redis-mcp" in result["already_installed"]

    @patch("mcp_tap.tools.scan._get_installed_server_names", return_value=set())
    async def test_no_installed_servers(self, _mock_installed: MagicMock):
        """Should have empty already_installed when nothing is installed."""
        ctx = _make_ctx()
        result = await scan_project(ctx, path=str(PYTHON_FASTAPI))

        assert result["already_installed"] == []


class TestScanEmptyProject:
    """Tests for scanning an empty project directory."""

    @patch("mcp_tap.tools.scan._get_installed_server_names", return_value=set())
    async def test_returns_valid_result(self, _mock_installed: MagicMock):
        """Should return a valid dict for an empty project (no crash)."""
        ctx = _make_ctx()
        result = await scan_project(ctx, path=str(EMPTY))

        assert "path" in result
        assert "detected_technologies" in result
        assert "recommendations" in result

    @patch("mcp_tap.tools.scan._get_installed_server_names", return_value=set())
    async def test_no_technologies_detected(self, _mock_installed: MagicMock):
        """Should detect no technologies in an empty project."""
        ctx = _make_ctx()
        result = await scan_project(ctx, path=str(EMPTY))

        assert result["detected_technologies"] == []

    @patch("mcp_tap.tools.scan._get_installed_server_names", return_value=set())
    async def test_no_env_vars(self, _mock_installed: MagicMock):
        """Should have empty env_vars_found."""
        ctx = _make_ctx()
        result = await scan_project(ctx, path=str(EMPTY))

        assert result["env_vars_found"] == []

    @patch("mcp_tap.tools.scan._get_installed_server_names", return_value=set())
    async def test_only_filesystem_recommendation(self, _mock_installed: MagicMock):
        """Should only recommend filesystem-mcp for an empty project."""
        ctx = _make_ctx()
        result = await scan_project(ctx, path=str(EMPTY))

        assert len(result["recommendations"]) == 1
        assert result["recommendations"][0]["server_name"] == "filesystem-mcp"


class TestScanInvalidPath:
    """Tests for scanning paths that don't exist."""

    async def test_nonexistent_path_returns_error(self, tmp_path: Path):
        """Should return error dict for nonexistent path, not raise."""
        ctx = _make_ctx()
        fake_path = str(tmp_path / "does_not_exist")
        result = await scan_project(ctx, path=fake_path)

        assert result.get("success") is False
        assert "error" in result

    async def test_file_path_returns_error(self, tmp_path: Path):
        """Should return error dict when path is a file, not a directory."""
        ctx = _make_ctx()
        f = tmp_path / "not_a_dir.txt"
        f.write_text("hello")
        result = await scan_project(ctx, path=str(f))

        assert result.get("success") is False
        assert "error" in result

    async def test_unexpected_exception_returns_error(self):
        """Should catch unexpected exceptions and return error dict."""
        ctx = _make_ctx()

        with patch(
            "mcp_tap.tools.scan._scan_project",
            side_effect=RuntimeError("boom"),
        ):
            result = await scan_project(ctx, path=str(PYTHON_FASTAPI))

        assert result.get("success") is False
        assert "Internal error" in result["error"]
        ctx.error.assert_awaited_once()


class TestScanDefaultPath:
    """Tests for the default path parameter."""

    @patch("mcp_tap.tools.scan._get_installed_server_names", return_value=set())
    @patch("mcp_tap.tools.scan._scan_project")
    async def test_default_path_is_dot(
        self,
        mock_scan: AsyncMock,
        _mock_installed: MagicMock,
    ):
        """Should pass '.' to the scanner when no path is specified."""
        # We need to give scan_project a valid-looking profile to avoid errors
        from mcp_tap.models import ProjectProfile

        mock_scan.return_value = ProjectProfile(path="/resolved/path")

        ctx = _make_ctx()
        await scan_project(ctx)  # no path argument

        mock_scan.assert_awaited_once_with(".")


class TestScanHasSummary:
    """Tests for the summary field in scan results."""

    @patch("mcp_tap.tools.scan._get_installed_server_names", return_value=set())
    async def test_summary_is_nonempty_string(self, _mock_installed: MagicMock):
        """Should include a non-empty summary string."""
        ctx = _make_ctx()
        result = await scan_project(ctx, path=str(PYTHON_FASTAPI))

        assert "summary" in result
        assert isinstance(result["summary"], str)
        assert len(result["summary"]) > 0

    @patch("mcp_tap.tools.scan._get_installed_server_names", return_value=set())
    async def test_summary_mentions_path(self, _mock_installed: MagicMock):
        """Should mention the scanned path in the summary."""
        ctx = _make_ctx()
        result = await scan_project(ctx, path=str(PYTHON_FASTAPI))

        # The resolved absolute path should be referenced
        assert str(PYTHON_FASTAPI.resolve()) in result["summary"]

    @patch("mcp_tap.tools.scan._get_installed_server_names", return_value=set())
    async def test_summary_mentions_technology_count(self, _mock_installed: MagicMock):
        """Should mention the number of detected technologies."""
        ctx = _make_ctx()
        result = await scan_project(ctx, path=str(PYTHON_FASTAPI))

        tech_count = len(result["detected_technologies"])
        assert f"{tech_count} technologies" in result["summary"]

    @patch(
        "mcp_tap.tools.scan._get_installed_server_names",
        return_value={"postgres-mcp", "redis-mcp"},
    )
    async def test_summary_mentions_installed_count(self, _mock_installed: MagicMock):
        """Should mention how many servers are already installed."""
        ctx = _make_ctx()
        result = await scan_project(ctx, path=str(PYTHON_FASTAPI))

        installed_count = len(result["already_installed"])
        assert f"{installed_count} already installed" in result["summary"]

    @patch("mcp_tap.tools.scan._get_installed_server_names", return_value=set())
    async def test_summary_empty_project(self, _mock_installed: MagicMock):
        """Should produce a valid summary for an empty project."""
        ctx = _make_ctx()
        result = await scan_project(ctx, path=str(EMPTY))

        assert "0 technologies" in result["summary"]


class TestScanClientParameter:
    """Tests for the optional client parameter."""

    @patch("mcp_tap.tools.scan._scan_project")
    @patch("mcp_tap.tools.scan.resolve_config_path")
    @patch("mcp_tap.tools.scan.read_config", return_value={"mcpServers": {}})
    async def test_explicit_client_calls_resolve(
        self,
        _mock_read: MagicMock,
        mock_resolve: MagicMock,
        mock_scan: AsyncMock,
    ):
        """Should call resolve_config_path with the explicit client value."""
        from mcp_tap.models import ProjectProfile

        mock_resolve.return_value = _fake_location()
        mock_scan.return_value = ProjectProfile(path="/tmp")

        ctx = _make_ctx()
        await scan_project(ctx, path=str(EMPTY), client="claude_code")

        mock_resolve.assert_called_once_with(MCPClient.CLAUDE_CODE)


# ═══════════════════════════════════════════════════════════════
# _build_summary Unit Tests
# ═══════════════════════════════════════════════════════════════


class TestBuildSummary:
    """Tests for the _build_summary helper function."""

    def test_basic_summary(self):
        """Should produce a summary with path and tech count."""
        summary = _build_summary(
            project_path="/tmp/project",
            tech_count=5,
            rec_count=3,
            installed_count=1,
            env_var_count=2,
        )
        assert "/tmp/project" in summary
        assert "5 technologies" in summary
        assert "2 environment variables" in summary

    def test_all_installed(self):
        """Should mention 'all recommended' when all are installed."""
        summary = _build_summary(
            project_path="/p",
            tech_count=2,
            rec_count=3,
            installed_count=3,
            env_var_count=0,
        )
        assert "already installed" in summary.lower()

    def test_no_recommendations(self):
        """Should mention no recommendations when rec_count is 0."""
        summary = _build_summary(
            project_path="/p",
            tech_count=0,
            rec_count=0,
            installed_count=0,
            env_var_count=0,
        )
        assert "No MCP server recommendations" in summary

    def test_missing_count(self):
        """Should mention how many servers are missing."""
        summary = _build_summary(
            project_path="/p",
            tech_count=3,
            rec_count=5,
            installed_count=2,
            env_var_count=1,
        )
        assert "3 to add" in summary
        assert "configure_server" in summary

    def test_no_env_vars_omitted(self):
        """Should not mention environment variables when count is 0."""
        summary = _build_summary(
            project_path="/p",
            tech_count=1,
            rec_count=1,
            installed_count=0,
            env_var_count=0,
        )
        assert "environment variable" not in summary


# ═══════════════════════════════════════════════════════════════
# _get_installed_server_names Unit Tests
# ═══════════════════════════════════════════════════════════════


class TestGetInstalledServerNames:
    """Tests for the _get_installed_server_names helper."""

    @patch("mcp_tap.tools.scan.detect_clients", return_value=[])
    def test_no_clients_returns_empty(self, _mock_detect: MagicMock):
        """Should return empty set when no clients detected."""
        result = _get_installed_server_names(None)
        assert result == set()

    @patch("mcp_tap.tools.scan.read_config")
    @patch("mcp_tap.tools.scan.detect_clients")
    def test_reads_from_detected_client(
        self,
        mock_detect: MagicMock,
        mock_read: MagicMock,
    ):
        """Should read config from the first detected client."""
        mock_detect.return_value = [_fake_location(path="/home/.claude.json")]
        mock_read.return_value = {
            "mcpServers": {
                "postgres-mcp": {"command": "npx", "args": ["-y", "pg"]},
                "github-mcp": {"command": "npx", "args": ["-y", "gh"]},
            }
        }

        result = _get_installed_server_names(None)
        assert result == {"postgres-mcp", "github-mcp"}

    @patch("mcp_tap.tools.scan.read_config")
    @patch("mcp_tap.tools.scan.resolve_config_path")
    def test_explicit_client(self, mock_resolve: MagicMock, mock_read: MagicMock):
        """Should use resolve_config_path when client is given explicitly."""
        mock_resolve.return_value = _fake_location()
        mock_read.return_value = {"mcpServers": {"my-server": {"command": "x"}}}

        result = _get_installed_server_names("claude_code")
        assert result == {"my-server"}
        mock_resolve.assert_called_once()

    @patch("mcp_tap.tools.scan.detect_clients", side_effect=Exception("filesystem error"))
    def test_error_returns_empty_set(self, _mock_detect: MagicMock):
        """Should return empty set on any error (graceful degradation)."""
        result = _get_installed_server_names(None)
        assert result == set()
