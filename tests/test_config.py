"""Tests for config reading, writing, and detection."""

from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest

from mcp_tap.config.reader import parse_servers, read_config
from mcp_tap.config.writer import remove_server_config, write_server_config
from mcp_tap.errors import ConfigReadError, ConfigWriteError
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
        with pytest.raises(ConfigReadError):
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


# === File Locking Tests (Fix C1) =============================================


class TestWriteServerConfigLocking:
    """Tests for in-process and cross-process file locking in config writer."""

    def test_lock_file_created_during_write(self, tmp_path: Path):
        """Should create a .lock file next to the config file during write."""
        f = tmp_path / "config.json"
        config = ServerConfig(command="npx", args=["-y", "test"])
        write_server_config(f, "my-server", config)

        # The lock file should have been created
        lock_file = tmp_path / "config.lock"
        assert lock_file.exists()

    def test_unique_temp_files_no_fixed_tmp_suffix(self, tmp_path: Path):
        """Should use tempfile.mkstemp() (unique names), not a fixed .tmp file."""
        f = tmp_path / "config.json"

        # Write two servers sequentially to verify no temp file collision
        write_server_config(f, "server-1", ServerConfig(command="a", args=[]))
        write_server_config(f, "server-2", ServerConfig(command="b", args=[]))

        data = json.loads(f.read_text())
        assert "server-1" in data["mcpServers"]
        assert "server-2" in data["mcpServers"]

        # No leftover .tmp files should remain
        tmp_files = list(tmp_path.glob("*.tmp"))
        assert len(tmp_files) == 0

    def test_concurrent_writes_do_not_corrupt_file(self, tmp_path: Path):
        """Should handle concurrent writes from same process without corruption."""
        f = tmp_path / "config.json"
        f.write_text(json.dumps({"mcpServers": {}}))

        errors: list[Exception] = []
        num_threads = 10

        def _write_server(index: int) -> None:
            try:
                write_server_config(
                    f,
                    f"server-{index}",
                    ServerConfig(command="npx", args=["-y", f"pkg-{index}"]),
                )
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=_write_server, args=(i,)) for i in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"Errors during concurrent writes: {errors}"

        data = json.loads(f.read_text())
        assert len(data["mcpServers"]) == num_threads
        for i in range(num_threads):
            assert f"server-{i}" in data["mcpServers"]

    def test_concurrent_write_and_remove_no_corruption(self, tmp_path: Path):
        """Should handle concurrent write + remove operations safely."""
        f = tmp_path / "config.json"
        # Pre-populate with servers to remove
        initial = {"mcpServers": {f"existing-{i}": {"command": "x"} for i in range(5)}}
        f.write_text(json.dumps(initial))

        errors: list[Exception] = []

        def _write(index: int) -> None:
            try:
                write_server_config(f, f"new-{index}", ServerConfig(command="npx", args=[]))
            except Exception as exc:
                errors.append(exc)

        def _remove(index: int) -> None:
            try:
                remove_server_config(f, f"existing-{index}")
            except Exception as exc:
                errors.append(exc)

        threads = []
        for i in range(5):
            threads.append(threading.Thread(target=_write, args=(i,)))
            threads.append(threading.Thread(target=_remove, args=(i,)))

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"Errors during concurrent ops: {errors}"

        data = json.loads(f.read_text())
        # All existing should be removed, all new should be added
        for i in range(5):
            assert f"existing-{i}" not in data["mcpServers"]
            assert f"new-{i}" in data["mcpServers"]

    def test_write_creates_parent_directories(self, tmp_path: Path):
        """Should create parent directories if they don't exist."""
        f = tmp_path / "subdir" / "deep" / "config.json"
        write_server_config(f, "my-server", ServerConfig(command="npx", args=[]))

        assert f.exists()
        data = json.loads(f.read_text())
        assert "my-server" in data["mcpServers"]
