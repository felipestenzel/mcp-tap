"""Tests for the lockfile package: hasher, reader, writer."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from mcp_tap.errors import LockfileReadError
from mcp_tap.lockfile.hasher import compute_tools_hash
from mcp_tap.lockfile.reader import parse_lockfile, read_lockfile
from mcp_tap.lockfile.writer import (
    _lockfile_to_dict,
    _mcp_tap_version,
    _now_iso,
    add_server_to_lockfile,
    remove_server_from_lockfile,
    update_server_verification,
    write_lockfile,
)
from mcp_tap.models import LockedConfig, LockedServer, Lockfile, ServerConfig

# ─── Hasher Tests ─────────────────────────────────────────────


class TestComputeToolsHash:
    def test_empty_list_returns_none(self) -> None:
        assert compute_tools_hash([]) is None

    def test_single_tool(self) -> None:
        result = compute_tools_hash(["query"])
        expected = "sha256-" + hashlib.sha256(b"query").hexdigest()
        assert result == expected

    def test_multiple_tools_sorted(self) -> None:
        """Tools are sorted before hashing regardless of input order."""
        result_a = compute_tools_hash(["query", "list_tables", "describe_table"])
        result_b = compute_tools_hash(["describe_table", "list_tables", "query"])
        assert result_a == result_b

        expected_joined = "describe_table|list_tables|query"
        expected = "sha256-" + hashlib.sha256(expected_joined.encode()).hexdigest()
        assert result_a == expected

    def test_pipe_separator(self) -> None:
        result = compute_tools_hash(["a", "b"])
        expected = "sha256-" + hashlib.sha256(b"a|b").hexdigest()
        assert result == expected

    def test_deterministic(self) -> None:
        """Same input always produces the same hash."""
        tools = ["search", "create", "delete"]
        assert compute_tools_hash(tools) == compute_tools_hash(tools)


# ─── Reader Tests ─────────────────────────────────────────────


class TestReadLockfile:
    def test_file_not_found_returns_none(self, tmp_path: Path) -> None:
        assert read_lockfile(tmp_path) is None

    def test_empty_file_returns_none(self, tmp_path: Path) -> None:
        (tmp_path / "mcp-tap.lock").write_text("")
        assert read_lockfile(tmp_path) is None

    def test_whitespace_only_returns_none(self, tmp_path: Path) -> None:
        (tmp_path / "mcp-tap.lock").write_text("   \n  \n  ")
        assert read_lockfile(tmp_path) is None

    def test_invalid_json_raises(self, tmp_path: Path) -> None:
        (tmp_path / "mcp-tap.lock").write_text("{invalid json")
        with pytest.raises(LockfileReadError, match="Invalid JSON"):
            read_lockfile(tmp_path)

    def test_unsupported_version_raises(self, tmp_path: Path) -> None:
        data = {"lockfile_version": 99, "servers": {}}
        (tmp_path / "mcp-tap.lock").write_text(json.dumps(data))
        with pytest.raises(LockfileReadError, match="Unsupported lockfile version 99"):
            read_lockfile(tmp_path)

    def test_valid_lockfile(self, tmp_path: Path) -> None:
        data = {
            "lockfile_version": 1,
            "generated_by": "mcp-tap@0.3.0",
            "generated_at": "2026-02-19T14:30:00Z",
            "servers": {
                "postgres": {
                    "package_identifier": "@mcp/server-postgres",
                    "registry_type": "npm",
                    "version": "0.6.2",
                    "integrity": None,
                    "repository_url": "https://github.com/example/repo",
                    "config": {
                        "command": "npx",
                        "args": ["-y", "@mcp/server-postgres"],
                        "env_keys": ["POSTGRES_URL"],
                    },
                    "tools": ["describe_table", "query"],
                    "tools_hash": "sha256-abc123",
                    "installed_at": "2026-02-19T14:30:00Z",
                    "verified_at": "2026-02-19T14:30:05Z",
                    "verified_healthy": True,
                }
            },
        }
        (tmp_path / "mcp-tap.lock").write_text(json.dumps(data))
        result = read_lockfile(tmp_path)

        assert result is not None
        assert result.lockfile_version == 1
        assert result.generated_by == "mcp-tap@0.3.0"
        assert "postgres" in result.servers

        pg = result.servers["postgres"]
        assert pg.package_identifier == "@mcp/server-postgres"
        assert pg.registry_type == "npm"
        assert pg.version == "0.6.2"
        assert pg.integrity is None
        assert pg.config.command == "npx"
        assert pg.config.args == ["-y", "@mcp/server-postgres"]
        assert pg.config.env_keys == ["POSTGRES_URL"]
        assert pg.tools == ["describe_table", "query"]
        assert pg.verified_healthy is True

    def test_missing_optional_fields_have_defaults(self, tmp_path: Path) -> None:
        """Minimal server entry parses with defaults."""
        data = {
            "lockfile_version": 1,
            "servers": {
                "minimal": {
                    "package_identifier": "some-pkg",
                    "version": "1.0.0",
                }
            },
        }
        (tmp_path / "mcp-tap.lock").write_text(json.dumps(data))
        result = read_lockfile(tmp_path)
        assert result is not None
        srv = result.servers["minimal"]
        assert srv.registry_type == "npm"  # default
        assert srv.integrity is None
        assert srv.repository_url == ""
        assert srv.tools == []
        assert srv.tools_hash is None
        assert srv.verified_healthy is False


class TestParseLockfile:
    def test_version_zero_raises(self) -> None:
        with pytest.raises(LockfileReadError, match="Unsupported lockfile version 0"):
            parse_lockfile({"servers": {}})

    def test_empty_servers(self) -> None:
        result = parse_lockfile({"lockfile_version": 1, "servers": {}})
        assert result.servers == {}
        assert result.lockfile_version == 1


# ─── Writer Tests ─────────────────────────────────────────────


class TestWriteLockfile:
    def test_write_and_read_roundtrip(self, tmp_path: Path) -> None:
        """Write a lockfile, read it back, verify the data matches."""
        config = LockedConfig(command="npx", args=["-y", "pkg"], env_keys=["API_KEY"])
        server = LockedServer(
            package_identifier="test-pkg",
            registry_type="npm",
            version="1.0.0",
            config=config,
            tools=["tool_a", "tool_b"],
            tools_hash=compute_tools_hash(["tool_a", "tool_b"]),
            installed_at="2026-02-19T14:30:00Z",
            verified_at="2026-02-19T14:30:05Z",
            verified_healthy=True,
        )
        lockfile = Lockfile(
            lockfile_version=1,
            generated_by="mcp-tap@test",
            generated_at="2026-02-19T14:30:00Z",
            servers={"test": server},
        )

        write_lockfile(tmp_path, lockfile)

        result = read_lockfile(tmp_path)
        assert result is not None
        assert result.lockfile_version == 1
        assert result.generated_by == "mcp-tap@test"
        assert "test" in result.servers
        assert result.servers["test"].version == "1.0.0"
        assert result.servers["test"].tools == ["tool_a", "tool_b"]

    def test_file_ends_with_newline(self, tmp_path: Path) -> None:
        lockfile = Lockfile(lockfile_version=1, generated_by="test", generated_at="now")
        write_lockfile(tmp_path, lockfile)
        content = (tmp_path / "mcp-tap.lock").read_text()
        assert content.endswith("\n")

    def test_creates_parent_directories(self, tmp_path: Path) -> None:
        nested = tmp_path / "deep" / "nested" / "project"
        lockfile = Lockfile(lockfile_version=1, generated_by="test", generated_at="now")
        write_lockfile(nested, lockfile)
        assert (nested / "mcp-tap.lock").exists()


class TestAddServerToLockfile:
    def test_creates_lockfile_if_not_exists(self, tmp_path: Path) -> None:
        config = ServerConfig(command="npx", args=["-y", "pkg"], env={"API_KEY": "secret"})
        add_server_to_lockfile(
            project_path=tmp_path,
            name="test-server",
            package_identifier="test-pkg",
            registry_type="npm",
            version="1.0.0",
            server_config=config,
            tools=["query", "search"],
        )

        result = read_lockfile(tmp_path)
        assert result is not None
        assert "test-server" in result.servers
        srv = result.servers["test-server"]
        assert srv.package_identifier == "test-pkg"
        assert srv.version == "1.0.0"
        assert srv.tools == ["query", "search"]  # sorted
        assert srv.tools_hash is not None
        assert srv.verified_healthy is True

    def test_env_values_are_not_stored(self, tmp_path: Path) -> None:
        """Security invariant: only env key names are stored, never values."""
        config = ServerConfig(
            command="npx",
            args=[],
            env={"SECRET_KEY": "super-secret-value", "API_TOKEN": "tok123"},
        )
        add_server_to_lockfile(
            project_path=tmp_path,
            name="secure",
            package_identifier="pkg",
            registry_type="npm",
            version="1.0.0",
            server_config=config,
        )

        # Read raw JSON to verify no secret values leaked
        raw = json.loads((tmp_path / "mcp-tap.lock").read_text())
        server_raw = raw["servers"]["secure"]
        config_raw = server_raw["config"]

        assert "env_keys" in config_raw
        assert sorted(config_raw["env_keys"]) == ["API_TOKEN", "SECRET_KEY"]
        # env_keys must be a list of strings, not a dict
        assert isinstance(config_raw["env_keys"], list)
        # No env values anywhere in the raw output
        raw_str = json.dumps(raw)
        assert "super-secret-value" not in raw_str
        assert "tok123" not in raw_str

    def test_preserves_installed_at_on_update(self, tmp_path: Path) -> None:
        """When updating an existing server, installed_at is preserved."""
        config = ServerConfig(command="npx", args=[], env={})
        add_server_to_lockfile(
            project_path=tmp_path,
            name="svr",
            package_identifier="pkg",
            registry_type="npm",
            version="1.0.0",
            server_config=config,
        )

        first_result = read_lockfile(tmp_path)
        assert first_result is not None
        first_installed_at = first_result.servers["svr"].installed_at

        # Update the same server with a new version
        add_server_to_lockfile(
            project_path=tmp_path,
            name="svr",
            package_identifier="pkg",
            registry_type="npm",
            version="2.0.0",
            server_config=config,
            tools=["new_tool"],
        )

        second_result = read_lockfile(tmp_path)
        assert second_result is not None
        assert second_result.servers["svr"].version == "2.0.0"
        assert second_result.servers["svr"].installed_at == first_installed_at

    def test_adds_second_server_without_losing_first(self, tmp_path: Path) -> None:
        config = ServerConfig(command="npx", args=[], env={})
        add_server_to_lockfile(
            project_path=tmp_path,
            name="alpha",
            package_identifier="alpha-pkg",
            registry_type="npm",
            version="1.0.0",
            server_config=config,
        )
        add_server_to_lockfile(
            project_path=tmp_path,
            name="beta",
            package_identifier="beta-pkg",
            registry_type="pypi",
            version="2.0.0",
            server_config=config,
        )

        result = read_lockfile(tmp_path)
        assert result is not None
        assert "alpha" in result.servers
        assert "beta" in result.servers

    def test_no_tools_sets_null_hash_and_not_healthy(self, tmp_path: Path) -> None:
        config = ServerConfig(command="npx", args=[], env={})
        add_server_to_lockfile(
            project_path=tmp_path,
            name="unverified",
            package_identifier="pkg",
            registry_type="npm",
            version="1.0.0",
            server_config=config,
            tools=None,
        )

        result = read_lockfile(tmp_path)
        assert result is not None
        srv = result.servers["unverified"]
        assert srv.tools == []
        assert srv.tools_hash is None
        assert srv.verified_at is None
        assert srv.verified_healthy is False


class TestRemoveServerFromLockfile:
    def test_remove_existing_server(self, tmp_path: Path) -> None:
        config = ServerConfig(command="npx", args=[], env={})
        add_server_to_lockfile(
            project_path=tmp_path,
            name="to-remove",
            package_identifier="pkg",
            registry_type="npm",
            version="1.0.0",
            server_config=config,
        )

        removed = remove_server_from_lockfile(tmp_path, "to-remove")
        assert removed is True

        result = read_lockfile(tmp_path)
        assert result is not None
        assert "to-remove" not in result.servers

    def test_remove_nonexistent_server_returns_false(self, tmp_path: Path) -> None:
        config = ServerConfig(command="npx", args=[], env={})
        add_server_to_lockfile(
            project_path=tmp_path,
            name="keep",
            package_identifier="pkg",
            registry_type="npm",
            version="1.0.0",
            server_config=config,
        )

        removed = remove_server_from_lockfile(tmp_path, "nonexistent")
        assert removed is False

    def test_remove_from_missing_lockfile_returns_false(self, tmp_path: Path) -> None:
        removed = remove_server_from_lockfile(tmp_path, "any")
        assert removed is False

    def test_remove_preserves_other_servers(self, tmp_path: Path) -> None:
        config = ServerConfig(command="npx", args=[], env={})
        add_server_to_lockfile(
            project_path=tmp_path,
            name="keep-me",
            package_identifier="pkg-a",
            registry_type="npm",
            version="1.0.0",
            server_config=config,
        )
        add_server_to_lockfile(
            project_path=tmp_path,
            name="remove-me",
            package_identifier="pkg-b",
            registry_type="npm",
            version="1.0.0",
            server_config=config,
        )

        remove_server_from_lockfile(tmp_path, "remove-me")

        result = read_lockfile(tmp_path)
        assert result is not None
        assert "keep-me" in result.servers
        assert "remove-me" not in result.servers


class TestUpdateServerVerification:
    def test_updates_verification_fields(self, tmp_path: Path) -> None:
        config = ServerConfig(command="npx", args=[], env={})
        add_server_to_lockfile(
            project_path=tmp_path,
            name="svr",
            package_identifier="pkg",
            registry_type="npm",
            version="1.0.0",
            server_config=config,
            tools=None,
        )

        update_server_verification(tmp_path, "svr", ["tool_x", "tool_y"], healthy=True)

        result = read_lockfile(tmp_path)
        assert result is not None
        srv = result.servers["svr"]
        assert srv.tools == ["tool_x", "tool_y"]  # sorted
        assert srv.tools_hash == compute_tools_hash(["tool_x", "tool_y"])
        assert srv.verified_at is not None
        assert srv.verified_healthy is True

    def test_noop_if_lockfile_missing(self, tmp_path: Path) -> None:
        """Does not raise if lockfile does not exist."""
        update_server_verification(tmp_path, "nonexistent", ["tool"], healthy=True)

    def test_noop_if_server_missing(self, tmp_path: Path) -> None:
        """Does not raise if server is not in lockfile."""
        config = ServerConfig(command="npx", args=[], env={})
        add_server_to_lockfile(
            project_path=tmp_path,
            name="other",
            package_identifier="pkg",
            registry_type="npm",
            version="1.0.0",
            server_config=config,
        )
        # Should not raise
        update_server_verification(tmp_path, "nonexistent", ["tool"], healthy=True)

    def test_preserves_installed_at(self, tmp_path: Path) -> None:
        config = ServerConfig(command="npx", args=[], env={})
        add_server_to_lockfile(
            project_path=tmp_path,
            name="svr",
            package_identifier="pkg",
            registry_type="npm",
            version="1.0.0",
            server_config=config,
        )
        original = read_lockfile(tmp_path)
        assert original is not None
        original_installed_at = original.servers["svr"].installed_at

        update_server_verification(tmp_path, "svr", ["tool"], healthy=True)

        result = read_lockfile(tmp_path)
        assert result is not None
        assert result.servers["svr"].installed_at == original_installed_at


# ─── Deterministic Output Tests ──────────────────────────────


class TestDeterministicOutput:
    def test_servers_sorted_alphabetically(self, tmp_path: Path) -> None:
        config = ServerConfig(command="npx", args=[], env={})
        add_server_to_lockfile(
            project_path=tmp_path,
            name="zebra",
            package_identifier="z-pkg",
            registry_type="npm",
            version="1.0.0",
            server_config=config,
        )
        add_server_to_lockfile(
            project_path=tmp_path,
            name="alpha",
            package_identifier="a-pkg",
            registry_type="npm",
            version="1.0.0",
            server_config=config,
        )

        raw = json.loads((tmp_path / "mcp-tap.lock").read_text())
        server_names = list(raw["servers"].keys())
        assert server_names == ["alpha", "zebra"]

    def test_tools_sorted_in_output(self, tmp_path: Path) -> None:
        config = ServerConfig(command="npx", args=[], env={})
        add_server_to_lockfile(
            project_path=tmp_path,
            name="svr",
            package_identifier="pkg",
            registry_type="npm",
            version="1.0.0",
            server_config=config,
            tools=["zebra_tool", "alpha_tool", "middle_tool"],
        )

        raw = json.loads((tmp_path / "mcp-tap.lock").read_text())
        assert raw["servers"]["svr"]["tools"] == [
            "alpha_tool",
            "middle_tool",
            "zebra_tool",
        ]

    def test_env_keys_sorted_in_output(self, tmp_path: Path) -> None:
        config = ServerConfig(
            command="npx",
            args=[],
            env={"ZEBRA_VAR": "z", "ALPHA_VAR": "a", "MIDDLE_VAR": "m"},
        )
        add_server_to_lockfile(
            project_path=tmp_path,
            name="svr",
            package_identifier="pkg",
            registry_type="npm",
            version="1.0.0",
            server_config=config,
        )

        raw = json.loads((tmp_path / "mcp-tap.lock").read_text())
        assert raw["servers"]["svr"]["config"]["env_keys"] == [
            "ALPHA_VAR",
            "MIDDLE_VAR",
            "ZEBRA_VAR",
        ]

    def test_json_indented_with_2_spaces(self, tmp_path: Path) -> None:
        lockfile = Lockfile(lockfile_version=1, generated_by="test", generated_at="now")
        write_lockfile(tmp_path, lockfile)
        content = (tmp_path / "mcp-tap.lock").read_text()
        # 2-space indent: first property should be indented 2 spaces
        assert '  "lockfile_version": 1' in content

    def test_same_data_produces_identical_output(self, tmp_path: Path) -> None:
        """Writing the same logical data twice produces identical JSON."""
        config = ServerConfig(command="npx", args=["-y", "pkg"], env={"KEY": "val"})
        add_server_to_lockfile(
            project_path=tmp_path,
            name="svr",
            package_identifier="pkg",
            registry_type="npm",
            version="1.0.0",
            server_config=config,
            tools=["b", "a"],
        )
        content_1 = (tmp_path / "mcp-tap.lock").read_text()

        # Read, re-serialize via _lockfile_to_dict, compare structure
        lockfile = read_lockfile(tmp_path)
        assert lockfile is not None
        data = _lockfile_to_dict(lockfile)
        content_2 = json.dumps(data, indent=2, ensure_ascii=False, sort_keys=False) + "\n"

        # The generated_at might differ, so compare structure
        assert json.loads(content_1)["servers"] == json.loads(content_2)["servers"]


# ─── Helper Function Tests ───────────────────────────────────


class TestHelpers:
    def test_now_iso_format(self) -> None:
        result = _now_iso()
        assert result.endswith("Z")
        assert "T" in result
        # Should not contain +00:00
        assert "+00:00" not in result

    def test_mcp_tap_version_format(self) -> None:
        result = _mcp_tap_version()
        assert result.startswith("mcp-tap@")

    def test_lockfile_to_dict_structure(self) -> None:
        config = LockedConfig(command="npx", args=["-y", "pkg"], env_keys=["KEY"])
        server = LockedServer(
            package_identifier="test-pkg",
            registry_type="npm",
            version="1.0.0",
            config=config,
            tools=["tool_b", "tool_a"],
            installed_at="2026-01-01T00:00:00Z",
        )
        lockfile = Lockfile(
            lockfile_version=1,
            generated_by="test",
            generated_at="2026-01-01T00:00:00Z",
            servers={"svr": server},
        )

        data = _lockfile_to_dict(lockfile)
        assert data["lockfile_version"] == 1
        assert "svr" in data["servers"]
        # Tools should be sorted in the dict
        assert data["servers"]["svr"]["tools"] == ["tool_a", "tool_b"]
