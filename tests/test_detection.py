"""Tests for config/detection.py — multi-client + project-scoped config resolution."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from mcp_tap.config.detection import (
    resolve_config_locations,
    resolve_config_path,
)
from mcp_tap.errors import ClientNotFoundError
from mcp_tap.models import MCPClient

# ═══════════════════════════════════════════════════════════════
# resolve_config_path — project scope
# ═══════════════════════════════════════════════════════════════


class TestResolveConfigPathProjectScope:
    def test_cursor_project_path(self):
        loc = resolve_config_path(MCPClient.CURSOR, scope="project", project_path="/my/project")
        assert loc.client == MCPClient.CURSOR
        assert loc.path == "/my/project/.cursor/mcp.json"
        assert loc.scope == "project"

    def test_claude_code_project_path(self):
        loc = resolve_config_path(
            MCPClient.CLAUDE_CODE, scope="project", project_path="/my/project"
        )
        assert loc.path == "/my/project/.mcp.json"
        assert loc.scope == "project"

    def test_windsurf_project_path(self):
        loc = resolve_config_path(MCPClient.WINDSURF, scope="project", project_path="/my/project")
        assert loc.path == "/my/project/.windsurf/mcp_config.json"
        assert loc.scope == "project"

    def test_claude_desktop_no_project_scope(self):
        with pytest.raises(ClientNotFoundError, match="does not support project-scoped"):
            resolve_config_path(MCPClient.CLAUDE_DESKTOP, scope="project", project_path="/project")

    def test_project_scope_requires_project_path(self):
        with pytest.raises(ClientNotFoundError, match="project_path is required"):
            resolve_config_path(MCPClient.CURSOR, scope="project", project_path="")

    def test_user_scope_still_works(self):
        loc = resolve_config_path(MCPClient.CURSOR, scope="user")
        assert loc.scope == "user"
        assert ".cursor/mcp.json" in loc.path


# ═══════════════════════════════════════════════════════════════
# resolve_config_locations
# ═══════════════════════════════════════════════════════════════


class TestResolveConfigLocations:
    def test_single_client_string(self):
        locs = resolve_config_locations("cursor")
        assert len(locs) == 1
        assert locs[0].client == MCPClient.CURSOR

    def test_comma_separated_clients(self):
        locs = resolve_config_locations("cursor,windsurf")
        assert len(locs) == 2
        assert {loc.client for loc in locs} == {MCPClient.CURSOR, MCPClient.WINDSURF}

    def test_all_user_returns_all_known(self):
        locs = resolve_config_locations("all")
        clients = {loc.client for loc in locs}
        assert MCPClient.CLAUDE_DESKTOP in clients
        assert MCPClient.CLAUDE_CODE in clients
        assert MCPClient.CURSOR in clients
        assert MCPClient.WINDSURF in clients

    def test_all_project_returns_supported_only(self):
        locs = resolve_config_locations("all", scope="project", project_path="/proj")
        clients = {loc.client for loc in locs}
        # Claude Desktop does NOT support project scope
        assert MCPClient.CLAUDE_DESKTOP not in clients
        assert MCPClient.CLAUDE_CODE in clients
        assert MCPClient.CURSOR in clients
        assert MCPClient.WINDSURF in clients

    def test_all_project_requires_path(self):
        with pytest.raises(ClientNotFoundError, match="project_path is required"):
            resolve_config_locations("all", scope="project", project_path="")

    @patch("mcp_tap.config.detection.detect_clients")
    def test_empty_auto_detects(self, mock_detect):
        from mcp_tap.models import ConfigLocation

        mock_detect.return_value = [
            ConfigLocation(
                client=MCPClient.CURSOR,
                path="/home/.cursor/mcp.json",
                scope="user",
                exists=True,
            )
        ]

        locs = resolve_config_locations("")
        assert len(locs) == 1
        assert locs[0].client == MCPClient.CURSOR

    @patch("mcp_tap.config.detection.detect_clients", return_value=[])
    def test_empty_no_clients_returns_empty(self, _mock):
        locs = resolve_config_locations("")
        assert locs == []

    def test_project_scope_single_client(self):
        locs = resolve_config_locations("cursor", scope="project", project_path="/proj")
        assert len(locs) == 1
        assert locs[0].path == "/proj/.cursor/mcp.json"
        assert locs[0].scope == "project"

    def test_whitespace_in_clients_trimmed(self):
        locs = resolve_config_locations(" cursor , windsurf ")
        assert len(locs) == 2

    def test_invalid_client_raises(self):
        with pytest.raises(ValueError):
            resolve_config_locations("not_a_client")
