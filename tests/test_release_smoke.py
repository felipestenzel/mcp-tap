"""Release smoke tests for canonical lockfile/config behavior."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from mcp_tap.models import ConfigLocation, MCPClient
from mcp_tap.server import AppContext
from mcp_tap.tools.list import list_installed
from mcp_tap.tools.restore import restore
from mcp_tap.tools.verify import verify


def _make_ctx() -> MagicMock:
    app = MagicMock(spec=AppContext)
    app.installer_resolver = AsyncMock()
    app.connection_tester = AsyncMock()

    ctx = MagicMock()
    ctx.request_context.lifespan_context = app
    ctx.info = AsyncMock()
    ctx.error = AsyncMock()
    return ctx


def _write_lockfile(project_path: Path) -> None:
    data = {
        "lockfile_version": 1,
        "generated_by": "mcp-tap@test",
        "generated_at": "2026-02-23T00:00:00Z",
        "servers": {
            "postgres-mcp": {
                "package_identifier": "@mcp/server-postgres",
                "registry_type": "npm",
                "version": "1.0.0",
                "repository_url": "https://github.com/example/postgres-server",
                "config": {
                    "command": "npx",
                    "args": ["-y", "@mcp/server-postgres"],
                    "env_keys": [],
                },
                "tools": [],
                "tools_hash": "",
                "installed_at": "2026-02-23T00:00:00Z",
                "verified_at": None,
                "verified_healthy": False,
            }
        },
    }
    (project_path / "mcp-tap.lock").write_text(json.dumps(data), encoding="utf-8")


def _write_client_config(config_path: Path) -> None:
    data = {
        "mcpServers": {
            "pg": {
                "command": "npx",
                "args": ["-y", "@mcp/server-postgres"],
            }
        }
    }
    config_path.write_text(json.dumps(data), encoding="utf-8")


def _location(config_path: Path) -> ConfigLocation:
    return ConfigLocation(
        client=MCPClient.CLAUDE_CODE,
        path=str(config_path),
        scope="user",
        exists=True,
    )


class TestReleaseSmokeCanonicalIdentity:
    async def test_verify_clean_with_alias_mismatch(self, tmp_path: Path) -> None:
        """verify should be clean when lockfile package matches installed alias."""
        _write_lockfile(tmp_path)
        config_path = tmp_path / "client.json"
        _write_client_config(config_path)

        ctx = _make_ctx()
        with patch("mcp_tap.tools.verify.detect_clients", return_value=[_location(config_path)]):
            result = await verify(str(tmp_path), ctx)

        assert result["clean"] is True
        assert result["drift"] == []

    async def test_restore_skips_reinstall_when_alias_already_present(self, tmp_path: Path) -> None:
        """restore should skip reinstall when canonical package already exists."""
        _write_lockfile(tmp_path)
        config_path = tmp_path / "client.json"
        _write_client_config(config_path)

        ctx = _make_ctx()
        with patch(
            "mcp_tap.tools.restore.resolve_config_locations",
            return_value=[_location(config_path)],
        ):
            result = await restore(str(tmp_path), ctx)

        assert result["success"] is True
        assert result["servers"][0]["status"] == "already_installed"
        ctx.request_context.lifespan_context.installer_resolver.resolve_installer.assert_not_awaited()

    async def test_list_installed_enriches_canonical_fields_from_lockfile(
        self, tmp_path: Path
    ) -> None:
        """list_installed should expose canonical identity fields when project_path is provided."""
        _write_lockfile(tmp_path)
        config_path = tmp_path / "client.json"
        _write_client_config(config_path)

        ctx = _make_ctx()
        with patch("mcp_tap.tools.list.detect_clients", return_value=[_location(config_path)]):
            result = await list_installed(ctx, project_path=str(tmp_path))

        assert result[0]["name"] == "pg"
        assert result[0]["package_identifier"] == "@mcp/server-postgres"
        assert result[0]["registry_type"] == "npm"
