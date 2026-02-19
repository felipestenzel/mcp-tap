"""Tests for config reading, writing, and detection."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mcp_tap.config.reader import parse_servers, read_config
from mcp_tap.config.writer import remove_server_config, write_server_config
from mcp_tap.errors import ConfigWriteError
from mcp_tap.models import ServerConfig


class TestReadConfig:
    def test_nonexistent_file_returns_empty(self, tmp_path: Path):
        result = read_config(tmp_path / "nonexistent.json")
        assert result == {"mcpServers": {}}

    def test_empty_file_returns_empty(self, tmp_path: Path):
        f = tmp_path / "config.json"
        f.write_text("")
        result = read_config(f)
        assert result == {"mcpServers": {}}

    def test_reads_valid_config(self, tmp_path: Path):
        f = tmp_path / "config.json"
        data = {
            "mcpServers": {
                "test-server": {
                    "command": "npx",
                    "args": ["-y", "test-pkg"],
                    "env": {"KEY": "value"},
                }
            },
            "otherKey": "preserved",
        }
        f.write_text(json.dumps(data))
        result = read_config(f)
        assert "otherKey" in result
        assert "test-server" in result["mcpServers"]

    def test_invalid_json_raises(self, tmp_path: Path):
        f = tmp_path / "config.json"
        f.write_text("{broken json")
        with pytest.raises(Exception):
            read_config(f)


class TestParseServers:
    def test_parses_server_entries(self):
        raw = {
            "mcpServers": {
                "pg": {"command": "npx", "args": ["-y", "pg-mcp"], "env": {"DB": "url"}},
                "gh": {"command": "uvx", "args": ["gh-mcp"]},
            }
        }
        servers = parse_servers(raw, source_file="/path/config.json")
        assert len(servers) == 2
        assert servers[0].name == "pg"
        assert servers[0].config.command == "npx"
        assert servers[0].config.env == {"DB": "url"}
        assert servers[1].name == "gh"
        assert servers[1].config.args == ["gh-mcp"]

    def test_empty_servers(self):
        assert parse_servers({"mcpServers": {}}) == []

    def test_missing_mcpservers_key(self):
        assert parse_servers({"other": "data"}) == []


class TestWriteServerConfig:
    def test_writes_new_server(self, tmp_path: Path):
        f = tmp_path / "config.json"
        config = ServerConfig(command="npx", args=["-y", "test"], env={"K": "v"})
        write_server_config(f, "my-server", config)

        data = json.loads(f.read_text())
        assert "my-server" in data["mcpServers"]
        assert data["mcpServers"]["my-server"]["command"] == "npx"
        assert data["mcpServers"]["my-server"]["env"] == {"K": "v"}

    def test_preserves_existing_servers(self, tmp_path: Path):
        f = tmp_path / "config.json"
        f.write_text(json.dumps({"mcpServers": {"existing": {"command": "old"}}}))

        write_server_config(f, "new", ServerConfig(command="npx", args=[]))

        data = json.loads(f.read_text())
        assert "existing" in data["mcpServers"]
        assert "new" in data["mcpServers"]

    def test_rejects_duplicate_server(self, tmp_path: Path):
        f = tmp_path / "config.json"
        f.write_text(json.dumps({"mcpServers": {"dup": {"command": "x"}}}))

        with pytest.raises(ConfigWriteError, match="already exists"):
            write_server_config(f, "dup", ServerConfig(command="y", args=[]))

    def test_preserves_unknown_keys(self, tmp_path: Path):
        f = tmp_path / "config.json"
        f.write_text(json.dumps({"mcpServers": {}, "globalShortcut": "Ctrl+Space"}))

        write_server_config(f, "s", ServerConfig(command="x", args=[]))

        data = json.loads(f.read_text())
        assert data["globalShortcut"] == "Ctrl+Space"


class TestRemoveServerConfig:
    def test_removes_existing(self, tmp_path: Path):
        f = tmp_path / "config.json"
        f.write_text(json.dumps({"mcpServers": {"rm-me": {"command": "x"}}}))

        removed = remove_server_config(f, "rm-me")
        assert removed is not None
        data = json.loads(f.read_text())
        assert "rm-me" not in data["mcpServers"]

    def test_returns_none_for_missing(self, tmp_path: Path):
        f = tmp_path / "config.json"
        f.write_text(json.dumps({"mcpServers": {}}))

        assert remove_server_config(f, "nope") is None
