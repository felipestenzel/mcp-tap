"""Tests for the stacks module (loader, tool, and models)."""

from __future__ import annotations

import textwrap
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mcp_tap.errors import McpTapError
from mcp_tap.models import Stack, StackServer
from mcp_tap.stacks.loader import (
    BUILTIN_STACKS,
    _parse_yaml,
    list_builtin_stacks,
    load_stack,
)
from mcp_tap.tools.stack import apply_stack

# ─── Helpers ─────────────────────────────────────────────────


def _make_ctx() -> MagicMock:
    """Build a mock Context with async info/error methods."""
    ctx = MagicMock()
    ctx.info = AsyncMock()
    ctx.error = AsyncMock()
    return ctx


MINIMAL_YAML = textwrap.dedent("""\
    name: test-stack
    description: A test stack
    servers:
      - name: foo
        package: "@test/server-foo"
""")

FULL_YAML = textwrap.dedent("""\
    name: full-stack
    description: Stack with all fields
    version: "2"
    author: tester
    servers:
      - name: alpha
        package: "@test/alpha"
        registry: npm
        version: "1.2.3"
        env_vars: [ALPHA_KEY, ALPHA_SECRET]
      - name: beta
        package: "mcp-server-beta"
        registry: pypi
        version: "0.5.0"
        env_vars: [BETA_TOKEN]
""")


# ─── Loader tests ────────────────────────────────────────────


class TestLoadBuiltinStacks:
    def test_load_builtin_data_science(self) -> None:
        stack = load_stack("data-science")
        assert stack.name == "data-science"
        assert len(stack.servers) == 3
        names = [s.name for s in stack.servers]
        assert "sqlite" in names
        assert "postgres" in names

    def test_load_builtin_web_dev(self) -> None:
        stack = load_stack("web-dev")
        assert stack.name == "web-dev"
        assert len(stack.servers) == 3
        names = [s.name for s in stack.servers]
        assert "puppeteer" in names
        assert "github" in names

    def test_load_builtin_devops(self) -> None:
        stack = load_stack("devops")
        assert stack.name == "devops"
        assert len(stack.servers) == 3
        names = [s.name for s in stack.servers]
        assert "docker" in names
        assert "slack" in names

    def test_load_unknown_stack_raises(self) -> None:
        with pytest.raises(McpTapError, match="Unknown stack 'nonexistent'"):
            load_stack("nonexistent")


class TestLoadFromFile:
    def test_load_yaml_file(self, tmp_path: object) -> None:
        path = tmp_path / "my-stack.yaml"  # type: ignore[operator]
        path.write_text(MINIMAL_YAML)  # type: ignore[union-attr]
        stack = load_stack(str(path))
        assert stack.name == "test-stack"
        assert len(stack.servers) == 1
        assert stack.servers[0].name == "foo"
        assert stack.servers[0].package_identifier == "@test/server-foo"

    def test_load_yml_extension(self, tmp_path: object) -> None:
        path = tmp_path / "stack.yml"  # type: ignore[operator]
        path.write_text(MINIMAL_YAML)  # type: ignore[union-attr]
        stack = load_stack(str(path))
        assert stack.name == "test-stack"

    def test_load_nonexistent_file_raises(self) -> None:
        with pytest.raises(McpTapError, match="Stack file not found"):
            load_stack("/nonexistent/path.yaml")

    def test_load_invalid_yaml_raises(self, tmp_path: object) -> None:
        path = tmp_path / "bad.yaml"  # type: ignore[operator]
        path.write_text("- just\n- a\n- list\n")  # type: ignore[union-attr]
        with pytest.raises(McpTapError, match="expected a YAML mapping"):
            load_stack(str(path))


class TestParseYaml:
    def test_parse_yaml_with_all_fields(self) -> None:
        stack = _parse_yaml(FULL_YAML, source="test")
        assert stack.name == "full-stack"
        assert stack.description == "Stack with all fields"
        assert stack.version == "2"
        assert stack.author == "tester"
        assert len(stack.servers) == 2

        alpha = stack.servers[0]
        assert alpha.name == "alpha"
        assert alpha.package_identifier == "@test/alpha"
        assert alpha.registry_type == "npm"
        assert alpha.version == "1.2.3"
        assert alpha.env_vars == ["ALPHA_KEY", "ALPHA_SECRET"]

        beta = stack.servers[1]
        assert beta.name == "beta"
        assert beta.package_identifier == "mcp-server-beta"
        assert beta.registry_type == "pypi"
        assert beta.version == "0.5.0"
        assert beta.env_vars == ["BETA_TOKEN"]

    def test_parse_yaml_minimal(self) -> None:
        stack = _parse_yaml(MINIMAL_YAML, source="test")
        assert stack.name == "test-stack"
        assert stack.version == "1"
        assert stack.author == ""
        assert len(stack.servers) == 1
        assert stack.servers[0].registry_type == "npm"
        assert stack.servers[0].version == "latest"
        assert stack.servers[0].env_vars == []

    def test_load_empty_servers_list(self) -> None:
        yaml_text = "name: empty\ndescription: No servers\nservers: []\n"
        stack = _parse_yaml(yaml_text, source="test")
        assert stack.name == "empty"
        assert stack.servers == []

    def test_parse_yaml_invalid_servers_type(self) -> None:
        yaml_text = "name: bad\nservers: not-a-list\n"
        with pytest.raises(McpTapError, match="'servers' must be a list"):
            _parse_yaml(yaml_text, source="test")

    def test_parse_yaml_skips_non_dict_entries(self) -> None:
        yaml_text = textwrap.dedent("""\
            name: mixed
            description: Has non-dict entries
            servers:
              - name: valid
                package: "@test/valid"
              - "just a string"
        """)
        stack = _parse_yaml(yaml_text, source="test")
        assert len(stack.servers) == 1
        assert stack.servers[0].name == "valid"


class TestListBuiltinStacks:
    def test_list_builtin_stacks(self) -> None:
        stacks = list_builtin_stacks()
        assert len(stacks) == len(BUILTIN_STACKS)
        names = {s["name"] for s in stacks}
        assert names == BUILTIN_STACKS
        for s in stacks:
            assert "description" in s
            assert "server_count" in s
            assert s["server_count"] > 0


# ─── Tool tests ──────────────────────────────────────────────


class TestApplyStackDryRun:
    async def test_apply_stack_dry_run(self) -> None:
        ctx = _make_ctx()
        result = await apply_stack(stack="data-science", ctx=ctx, dry_run=True)
        assert result["success"] is True
        assert result["dry_run"] is True
        assert result["stack_name"] == "data-science"
        assert result["servers_total"] == 3
        assert isinstance(result["servers"], list)
        assert isinstance(result["env_vars_needed"], list)
        assert "POSTGRES_URL" in result["env_vars_needed"]

    async def test_apply_stack_dry_run_from_yaml_file(self, tmp_path: object) -> None:
        path = tmp_path / "custom.yaml"  # type: ignore[operator]
        path.write_text(FULL_YAML)  # type: ignore[union-attr]
        ctx = _make_ctx()
        result = await apply_stack(stack=str(path), ctx=ctx, dry_run=True)
        assert result["success"] is True
        assert result["stack_name"] == "full-stack"
        assert result["servers_total"] == 2


class TestApplyStackInstall:
    @patch("mcp_tap.tools.stack.configure_server")
    async def test_apply_stack_installs_all(self, mock_configure: AsyncMock) -> None:
        mock_configure.return_value = {"success": True, "server_name": "test"}
        ctx = _make_ctx()
        result = await apply_stack(stack="data-science", ctx=ctx)
        assert result["success"] is True
        assert result["servers_installed"] == 3
        assert result["servers_failed"] == 0
        assert mock_configure.call_count == 3

    @patch("mcp_tap.tools.stack.configure_server")
    async def test_apply_stack_partial_failure(self, mock_configure: AsyncMock) -> None:
        mock_configure.side_effect = [
            {"success": True, "server_name": "sqlite"},
            {"success": False, "server_name": "postgres", "message": "failed"},
            {"success": True, "server_name": "puppeteer"},
        ]
        ctx = _make_ctx()
        result = await apply_stack(stack="data-science", ctx=ctx)
        assert result["success"] is True  # at least one installed
        assert result["servers_installed"] == 2
        assert result["servers_failed"] == 1

    @patch("mcp_tap.tools.stack.configure_server")
    async def test_apply_stack_all_fail(self, mock_configure: AsyncMock) -> None:
        mock_configure.return_value = {"success": False, "message": "failed"}
        ctx = _make_ctx()
        result = await apply_stack(stack="data-science", ctx=ctx)
        assert result["success"] is False
        assert result["servers_installed"] == 0
        assert result["servers_failed"] == 3

    @patch("mcp_tap.tools.stack.configure_server")
    async def test_apply_stack_exception_handling(self, mock_configure: AsyncMock) -> None:
        mock_configure.side_effect = RuntimeError("boom")
        ctx = _make_ctx()
        result = await apply_stack(stack="data-science", ctx=ctx)
        assert result["success"] is False
        assert result["servers_failed"] == 3
        per_server = result["per_server_results"]
        assert "RuntimeError: boom" in per_server[0]["error"]

    async def test_apply_stack_unknown_stack(self) -> None:
        ctx = _make_ctx()
        result = await apply_stack(stack="nonexistent", ctx=ctx)
        assert result["success"] is False
        assert "error" in result
        assert "available_stacks" in result

    @patch("mcp_tap.tools.stack.configure_server")
    async def test_apply_stack_empty_stack(self, mock_configure: AsyncMock) -> None:
        ctx = _make_ctx()
        with patch("mcp_tap.tools.stack.load_stack") as mock_load:
            mock_load.return_value = Stack(name="empty", description="No servers", servers=[])
            result = await apply_stack(stack="empty", ctx=ctx)
        assert result["success"] is False
        assert "no servers" in result["error"].lower()
        mock_configure.assert_not_called()

    @patch("mcp_tap.tools.stack.configure_server")
    async def test_apply_stack_env_vars_collected(self, mock_configure: AsyncMock) -> None:
        mock_configure.return_value = {"success": True}
        ctx = _make_ctx()
        result = await apply_stack(stack="web-dev", ctx=ctx)
        env_vars = result["env_vars_needed"]
        assert "GITHUB_PERSONAL_ACCESS_TOKEN" in env_vars
        assert "SENTRY_AUTH_TOKEN" in env_vars
        assert "SENTRY_ORG" in env_vars

    @patch("mcp_tap.tools.stack.configure_server")
    async def test_apply_stack_from_yaml_file(
        self, mock_configure: AsyncMock, tmp_path: object
    ) -> None:
        mock_configure.return_value = {"success": True}
        path = tmp_path / "custom.yaml"  # type: ignore[operator]
        path.write_text(FULL_YAML)  # type: ignore[union-attr]
        ctx = _make_ctx()
        result = await apply_stack(stack=str(path), ctx=ctx)
        assert result["success"] is True
        assert result["stack_name"] == "full-stack"
        assert mock_configure.call_count == 2

    @patch("mcp_tap.tools.stack.configure_server")
    async def test_apply_stack_passes_clients_and_scope(self, mock_configure: AsyncMock) -> None:
        mock_configure.return_value = {"success": True}
        ctx = _make_ctx()
        await apply_stack(
            stack="data-science",
            ctx=ctx,
            clients="claude_desktop,cursor",
            scope="project",
            project_path="/some/project",
        )
        for call in mock_configure.call_args_list:
            assert call.kwargs["clients"] == "claude_desktop,cursor"
            assert call.kwargs["scope"] == "project"
            assert call.kwargs["project_path"] == "/some/project"


# ─── Model tests ─────────────────────────────────────────────


class TestStackModels:
    def test_stack_model_frozen(self) -> None:
        stack = Stack(name="test", description="desc")
        with pytest.raises(AttributeError):
            stack.name = "changed"  # type: ignore[misc]

    def test_stack_server_frozen(self) -> None:
        srv = StackServer(name="test", package_identifier="pkg")
        with pytest.raises(AttributeError):
            srv.name = "changed"  # type: ignore[misc]

    def test_stack_server_defaults(self) -> None:
        srv = StackServer(name="test", package_identifier="pkg")
        assert srv.registry_type == "npm"
        assert srv.version == "latest"
        assert srv.env_vars == []

    def test_stack_defaults(self) -> None:
        stack = Stack(name="test", description="desc")
        assert stack.servers == []
        assert stack.version == "1"
        assert stack.author == ""

    def test_stack_from_yaml_roundtrip(self) -> None:
        stack = _parse_yaml(FULL_YAML, source="test")
        assert stack.name == "full-stack"
        assert stack.description == "Stack with all fields"
        assert stack.version == "2"
        assert stack.author == "tester"
        assert len(stack.servers) == 2
        assert stack.servers[0].name == "alpha"
        assert stack.servers[0].package_identifier == "@test/alpha"
        assert stack.servers[0].env_vars == ["ALPHA_KEY", "ALPHA_SECRET"]
        assert stack.servers[1].name == "beta"
        assert stack.servers[1].registry_type == "pypi"
