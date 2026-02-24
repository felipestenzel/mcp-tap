"""Release E2E client matrix for configure/list/verify/health/remove/restore flows."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mcp_tap.models import (
    ConfigLocation,
    ConnectionTestResult,
    MCPClient,
    SecurityReport,
    SecurityRisk,
)
from mcp_tap.server import AppContext
from mcp_tap.tools.configure import configure_server
from mcp_tap.tools.health import check_health
from mcp_tap.tools.list import list_installed
from mcp_tap.tools.remove import remove_server
from mcp_tap.tools.restore import restore
from mcp_tap.tools.verify import verify


def _location(client: MCPClient, path: Path) -> ConfigLocation:
    return ConfigLocation(
        client=client,
        path=str(path),
        scope="user",
        exists=True,
    )


def _configure_ctx() -> MagicMock:
    app = MagicMock(spec=AppContext)
    app.connection_tester = AsyncMock()
    app.healing = AsyncMock()
    app.installer_resolver = AsyncMock()
    app.http_reachability = AsyncMock()
    app.http_reachability.check_reachability = AsyncMock(
        return_value=ConnectionTestResult(success=True, server_name="vercel")
    )
    app.security_gate = AsyncMock()
    app.security_gate.run_security_gate = AsyncMock(
        return_value=SecurityReport(overall_risk=SecurityRisk.PASS)
    )

    ctx = MagicMock()
    ctx.request_context.lifespan_context = app
    ctx.info = AsyncMock()
    ctx.error = AsyncMock()
    return ctx


def _restore_ctx() -> MagicMock:
    app = MagicMock(spec=AppContext)
    app.installer_resolver = AsyncMock()
    app.connection_tester = AsyncMock()

    ctx = MagicMock()
    ctx.request_context.lifespan_context = app
    ctx.info = AsyncMock()
    ctx.error = AsyncMock()
    return ctx


def _health_ctx() -> MagicMock:
    app = MagicMock(spec=AppContext)
    app.connection_tester = MagicMock()
    app.connection_tester.test_server_connection = AsyncMock(
        return_value=ConnectionTestResult(
            success=True,
            server_name="vercel",
            tools_discovered=["deployments"],
        )
    )
    app.http_reachability = MagicMock()
    app.http_reachability.check_reachability = AsyncMock(
        return_value=ConnectionTestResult(
            success=True,
            server_name="vercel",
            tools_discovered=["deployments"],
        )
    )
    app.healing = AsyncMock()

    ctx = MagicMock()
    ctx.request_context.lifespan_context = app
    ctx.info = AsyncMock()
    ctx.error = AsyncMock()
    return ctx


def _readonly_ctx() -> MagicMock:
    ctx = MagicMock()
    ctx.info = AsyncMock()
    ctx.error = AsyncMock()
    return ctx


def _init_config(path: Path) -> None:
    path.write_text(json.dumps({"mcpServers": {}}), encoding="utf-8")


@pytest.mark.parametrize(
    ("client", "expects_native_http"),
    [
        (MCPClient.CLAUDE_CODE, True),
        (MCPClient.CURSOR, False),
        (MCPClient.WINDSURF, False),
    ],
)
async def test_http_release_flow_per_client(
    tmp_path: Path,
    client: MCPClient,
    expects_native_http: bool,
) -> None:
    """End-to-end flow per client with health and cleanup coverage."""
    project_path = tmp_path / client.value
    project_path.mkdir()
    config_path = project_path / "mcp.json"
    _init_config(config_path)
    location = _location(client, config_path)

    # configure_server (HTTP URL path)
    ctx_configure = _configure_ctx()
    with patch("mcp_tap.tools.configure.resolve_config_locations", return_value=[location]):
        configured = await configure_server(
            server_name="vercel",
            package_identifier="https://mcp.vercel.com",
            ctx=ctx_configure,
            clients=client.value,
            project_path=str(project_path),
        )

    assert configured["success"] is True
    assert configured["install_status"] == "configured"

    raw = json.loads(config_path.read_text(encoding="utf-8"))
    written = raw["mcpServers"]["vercel"]
    if expects_native_http:
        assert written["type"] == "http"
        assert written["url"] == "https://mcp.vercel.com"
    else:
        assert written["command"] == "npx"
        assert written["args"] == ["-y", "mcp-remote", "https://mcp.vercel.com"]

    # list_installed
    with patch("mcp_tap.tools.list.resolve_config_path", return_value=location):
        listed = await list_installed(
            _readonly_ctx(),
            client=client.value,
            project_path=str(project_path),
        )
    assert listed[0]["name"] == "vercel"
    assert listed[0]["package_identifier"] == "https://mcp.vercel.com"

    # verify
    with patch("mcp_tap.tools.verify.resolve_config_path", return_value=location):
        verified = await verify(
            project_path=str(project_path),
            ctx=_readonly_ctx(),
            client=client.value,
        )
    assert verified["clean"] is True
    assert verified["drift"] == []

    # check_health should route through the right transport adapter
    ctx_health = _health_ctx()
    with patch("mcp_tap.tools.health.resolve_config_path", return_value=location):
        health = await check_health(
            ctx_health,
            client=client.value,
        )
    assert health["total"] == 1
    assert health["healthy"] == 1
    assert health["unhealthy"] == 0

    health_app = ctx_health.request_context.lifespan_context
    if expects_native_http:
        health_app.http_reachability.check_reachability.assert_awaited_once()
        health_app.connection_tester.test_server_connection.assert_not_awaited()
    else:
        health_app.connection_tester.test_server_connection.assert_awaited_once()
        health_app.http_reachability.check_reachability.assert_not_awaited()

    # restore (should skip reinstall via canonical matching)
    ctx_restore = _restore_ctx()
    with patch(
        "mcp_tap.tools.restore.resolve_config_locations",
        return_value=[location],
    ):
        restored = await restore(
            project_path=str(project_path),
            ctx=ctx_restore,
            client=client.value,
        )

    assert restored["success"] is True
    assert restored["servers"][0]["status"] == "already_installed"
    ctx_restore.request_context.lifespan_context.installer_resolver.resolve_installer.assert_not_awaited()

    # remove should clean config entry
    with patch("mcp_tap.tools.remove.resolve_config_locations", return_value=[location]):
        removed = await remove_server(
            server_name="vercel",
            ctx=_readonly_ctx(),
            clients=client.value,
        )
    assert removed["success"] is True
    raw_after_remove = json.loads(config_path.read_text(encoding="utf-8"))
    assert "vercel" not in raw_after_remove["mcpServers"]

    # verify should now detect lockfile drift (missing server)
    with patch("mcp_tap.tools.verify.resolve_config_path", return_value=location):
        verified_after_remove = await verify(
            project_path=str(project_path),
            ctx=_readonly_ctx(),
            client=client.value,
        )
    assert verified_after_remove["clean"] is False
    assert any(
        drift["server"] == "vercel" and drift["drift_type"] == "missing"
        for drift in verified_after_remove["drift"]
    )


async def test_http_release_matrix_multi_client_single_configure_call(tmp_path: Path) -> None:
    """Single configure call should apply per-client best config across matrix."""
    project_path = tmp_path / "matrix"
    project_path.mkdir()

    cc_path = project_path / "claude_code.json"
    cursor_path = project_path / "cursor.json"
    windsurf_path = project_path / "windsurf.json"
    for p in (cc_path, cursor_path, windsurf_path):
        _init_config(p)

    locations = [
        _location(MCPClient.CLAUDE_CODE, cc_path),
        _location(MCPClient.CURSOR, cursor_path),
        _location(MCPClient.WINDSURF, windsurf_path),
    ]

    ctx_configure = _configure_ctx()
    with patch("mcp_tap.tools.configure.resolve_config_locations", return_value=locations):
        configured = await configure_server(
            server_name="vercel",
            package_identifier="https://mcp.vercel.com",
            ctx=ctx_configure,
            clients="claude_code,cursor,windsurf",
            project_path=str(project_path),
        )

    assert configured["success"] is True
    assert len(configured["per_client_results"]) == 3

    cc = json.loads(cc_path.read_text(encoding="utf-8"))["mcpServers"]["vercel"]
    cursor = json.loads(cursor_path.read_text(encoding="utf-8"))["mcpServers"]["vercel"]
    windsurf = json.loads(windsurf_path.read_text(encoding="utf-8"))["mcpServers"]["vercel"]

    assert cc["type"] == "http"
    assert cc["url"] == "https://mcp.vercel.com"
    assert cursor["args"] == ["-y", "mcp-remote", "https://mcp.vercel.com"]
    assert windsurf["args"] == ["-y", "mcp-remote", "https://mcp.vercel.com"]

    # verify should stay clean for each client against the same lockfile
    for client, path in (
        (MCPClient.CLAUDE_CODE, cc_path),
        (MCPClient.CURSOR, cursor_path),
        (MCPClient.WINDSURF, windsurf_path),
    ):
        with patch(
            "mcp_tap.tools.verify.resolve_config_path", return_value=_location(client, path)
        ):
            verified = await verify(
                project_path=str(project_path),
                ctx=_readonly_ctx(),
                client=client.value,
            )
        assert verified["clean"] is True
