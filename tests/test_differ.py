"""Tests for lockfile drift detection (lockfile/differ.py)."""

from __future__ import annotations

import pytest

from mcp_tap.lockfile.differ import _check_config_drift, _check_tools_drift, diff_lockfile
from mcp_tap.lockfile.hasher import compute_tools_hash
from mcp_tap.models import (
    DriftEntry,
    DriftSeverity,
    DriftType,
    InstalledServer,
    LockedConfig,
    LockedServer,
    Lockfile,
    ServerConfig,
    ServerHealth,
)

# --- Fixtures ---------------------------------------------------------------


@pytest.fixture
def empty_lockfile() -> Lockfile:
    return Lockfile(lockfile_version=1, generated_by="test", generated_at="now")


def _locked_server(
    command: str = "npx",
    args: list[str] | None = None,
    env_keys: list[str] | None = None,
    tools: list[str] | None = None,
    tools_hash: str | None = None,
    pkg: str = "test-pkg",
    version: str = "1.0.0",
) -> LockedServer:
    """Build a LockedServer with defaults for testing."""
    if args is None:
        args = ["-y", "test-pkg"]
    config = LockedConfig(command=command, args=args, env_keys=env_keys or [])
    actual_tools = tools or []
    return LockedServer(
        package_identifier=pkg,
        registry_type="npm",
        version=version,
        config=config,
        tools=actual_tools,
        tools_hash=tools_hash or compute_tools_hash(actual_tools),
        installed_at="2026-02-19T14:30:00Z",
    )


def _installed(
    name: str,
    command: str = "npx",
    args: list[str] | None = None,
) -> InstalledServer:
    """Build an InstalledServer with defaults for testing."""
    if args is None:
        args = ["-y", "test-pkg"]
    return InstalledServer(
        name=name,
        config=ServerConfig(command=command, args=args),
        source_file="/tmp/config.json",
    )


def _healthy(name: str, tools: list[str]) -> ServerHealth:
    return ServerHealth(
        name=name,
        status="healthy",
        tools_count=len(tools),
        tools=tools,
    )


def _unhealthy(name: str) -> ServerHealth:
    return ServerHealth(
        name=name,
        status="unhealthy",
        error="Connection refused",
    )


# === diff_lockfile: Empty inputs ============================================


class TestDiffLockfileEmpty:
    """Tests with empty lockfile and/or empty installed list."""

    def test_empty_lockfile_empty_installed_returns_no_drift(
        self, empty_lockfile: Lockfile
    ) -> None:
        """Should return empty list when both lockfile and installed are empty."""
        result = diff_lockfile(empty_lockfile, [])
        assert result == []

    def test_empty_lockfile_with_installed_returns_extra(
        self, empty_lockfile: Lockfile
    ) -> None:
        """Should detect EXTRA servers that are installed but not in lockfile."""
        installed = [_installed("postgres")]
        result = diff_lockfile(empty_lockfile, installed)

        assert len(result) == 1
        assert result[0].drift_type == DriftType.EXTRA
        assert result[0].server == "postgres"
        assert result[0].severity == DriftSeverity.INFO

    def test_lockfile_with_servers_empty_installed_returns_missing(self) -> None:
        """Should detect MISSING servers that are in lockfile but not installed."""
        lockfile = Lockfile(
            lockfile_version=1,
            servers={"postgres": _locked_server()},
        )
        result = diff_lockfile(lockfile, [])

        assert len(result) == 1
        assert result[0].drift_type == DriftType.MISSING
        assert result[0].server == "postgres"
        assert result[0].severity == DriftSeverity.WARNING


# === diff_lockfile: MISSING server drift ====================================


class TestMissingDrift:
    """Tests for servers in lockfile but not installed."""

    def test_single_missing_server(self) -> None:
        """Should report MISSING when server is locked but not installed."""
        lockfile = Lockfile(servers={"pg": _locked_server()})
        result = diff_lockfile(lockfile, [])

        assert len(result) == 1
        entry = result[0]
        assert entry.drift_type == DriftType.MISSING
        assert entry.server == "pg"
        assert entry.severity == DriftSeverity.WARNING
        assert "pg" in entry.detail
        assert "lockfile" in entry.detail
        assert "not in client config" in entry.detail

    def test_multiple_missing_servers(self) -> None:
        """Should report one MISSING entry per missing server."""
        lockfile = Lockfile(
            servers={
                "alpha": _locked_server(),
                "beta": _locked_server(),
                "gamma": _locked_server(),
            }
        )
        result = diff_lockfile(lockfile, [])

        assert len(result) == 3
        assert all(e.drift_type == DriftType.MISSING for e in result)
        missing_names = {e.server for e in result}
        assert missing_names == {"alpha", "beta", "gamma"}


# === diff_lockfile: EXTRA server drift ======================================


class TestExtraDrift:
    """Tests for servers installed but not in lockfile."""

    def test_single_extra_server(self, empty_lockfile: Lockfile) -> None:
        """Should report EXTRA when server is installed but not locked."""
        installed = [_installed("github")]
        result = diff_lockfile(empty_lockfile, installed)

        assert len(result) == 1
        entry = result[0]
        assert entry.drift_type == DriftType.EXTRA
        assert entry.server == "github"
        assert entry.severity == DriftSeverity.INFO
        assert "github" in entry.detail
        assert "not in lockfile" in entry.detail

    def test_multiple_extra_servers(self, empty_lockfile: Lockfile) -> None:
        """Should report one EXTRA entry per extra server."""
        installed = [_installed("a"), _installed("b")]
        result = diff_lockfile(empty_lockfile, installed)

        assert len(result) == 2
        assert all(e.drift_type == DriftType.EXTRA for e in result)
        extra_names = {e.server for e in result}
        assert extra_names == {"a", "b"}


# === diff_lockfile: No drift (matching) =====================================


class TestNoDrift:
    """Tests where lockfile matches installed exactly."""

    def test_matching_server_no_health(self) -> None:
        """Should return no drift when server matches and no health data."""
        lockfile = Lockfile(
            servers={"pg": _locked_server(command="npx", args=["-y", "test-pkg"])},
        )
        installed = [_installed("pg", command="npx", args=["-y", "test-pkg"])]
        result = diff_lockfile(lockfile, installed)
        assert result == []

    def test_matching_config_matching_tools(self) -> None:
        """Should return no drift when config AND tools match."""
        tools = ["query", "list_tables"]
        lockfile = Lockfile(
            servers={
                "pg": _locked_server(
                    tools=tools,
                    tools_hash=compute_tools_hash(tools),
                )
            },
        )
        installed = [_installed("pg")]
        healths = [_healthy("pg", tools)]
        result = diff_lockfile(lockfile, installed, healths)
        assert result == []

    def test_multiple_matching_servers(self) -> None:
        """Should return no drift when all servers match."""
        lockfile = Lockfile(
            servers={
                "pg": _locked_server(command="npx", args=["-y", "pg-pkg"]),
                "redis": _locked_server(command="uvx", args=["redis-mcp"]),
            },
        )
        installed = [
            _installed("pg", command="npx", args=["-y", "pg-pkg"]),
            _installed("redis", command="uvx", args=["redis-mcp"]),
        ]
        result = diff_lockfile(lockfile, installed)
        assert result == []


# === diff_lockfile: CONFIG_CHANGED drift ====================================


class TestConfigChangedDrift:
    """Tests for config command/args mismatch."""

    def test_command_changed(self) -> None:
        """Should report CONFIG_CHANGED when command differs."""
        lockfile = Lockfile(
            servers={"pg": _locked_server(command="npx", args=["-y", "pkg"])},
        )
        installed = [_installed("pg", command="uvx", args=["-y", "pkg"])]
        result = diff_lockfile(lockfile, installed)

        assert len(result) == 1
        entry = result[0]
        assert entry.drift_type == DriftType.CONFIG_CHANGED
        assert entry.server == "pg"
        assert entry.severity == DriftSeverity.WARNING
        assert "npx" in entry.detail
        assert "uvx" in entry.detail

    def test_args_changed(self) -> None:
        """Should report CONFIG_CHANGED when args differ."""
        lockfile = Lockfile(
            servers={"pg": _locked_server(command="npx", args=["-y", "old-pkg"])},
        )
        installed = [_installed("pg", command="npx", args=["-y", "new-pkg"])]
        result = diff_lockfile(lockfile, installed)

        assert len(result) == 1
        assert result[0].drift_type == DriftType.CONFIG_CHANGED

    def test_args_order_matters(self) -> None:
        """Should detect drift when args are in different order."""
        lockfile = Lockfile(
            servers={"pg": _locked_server(command="npx", args=["a", "b"])},
        )
        installed = [_installed("pg", command="npx", args=["b", "a"])]
        result = diff_lockfile(lockfile, installed)

        assert len(result) == 1
        assert result[0].drift_type == DriftType.CONFIG_CHANGED

    def test_args_added(self) -> None:
        """Should detect drift when installed has extra args."""
        lockfile = Lockfile(
            servers={"pg": _locked_server(command="npx", args=["-y"])},
        )
        installed = [_installed("pg", command="npx", args=["-y", "--extra"])]
        result = diff_lockfile(lockfile, installed)

        assert len(result) == 1
        assert result[0].drift_type == DriftType.CONFIG_CHANGED

    def test_args_removed(self) -> None:
        """Should detect drift when installed has fewer args."""
        lockfile = Lockfile(
            servers={"pg": _locked_server(command="npx", args=["-y", "--verbose"])},
        )
        installed = [_installed("pg", command="npx", args=["-y"])]
        result = diff_lockfile(lockfile, installed)

        assert len(result) == 1
        assert result[0].drift_type == DriftType.CONFIG_CHANGED

    def test_both_command_and_args_changed(self) -> None:
        """Should produce a single CONFIG_CHANGED when both differ."""
        lockfile = Lockfile(
            servers={"pg": _locked_server(command="npx", args=["-y", "old"])},
        )
        installed = [_installed("pg", command="uvx", args=["new"])]
        result = diff_lockfile(lockfile, installed)

        # Still only one CONFIG_CHANGED entry (not two)
        config_drifts = [e for e in result if e.drift_type == DriftType.CONFIG_CHANGED]
        assert len(config_drifts) == 1


# === diff_lockfile: TOOLS_CHANGED drift =====================================


class TestToolsChangedDrift:
    """Tests for tools hash mismatch."""

    def test_tools_added(self) -> None:
        """Should report TOOLS_CHANGED when current tools include new ones."""
        locked_tools = ["query"]
        lockfile = Lockfile(
            servers={
                "pg": _locked_server(
                    tools=locked_tools,
                    tools_hash=compute_tools_hash(locked_tools),
                )
            },
        )
        installed = [_installed("pg")]
        current_tools = ["query", "new_tool"]
        healths = [_healthy("pg", current_tools)]

        result = diff_lockfile(lockfile, installed, healths)

        tools_drift = [e for e in result if e.drift_type == DriftType.TOOLS_CHANGED]
        assert len(tools_drift) == 1
        entry = tools_drift[0]
        assert entry.severity == DriftSeverity.ERROR
        assert "new_tool" in entry.detail
        assert "added" in entry.detail

    def test_tools_removed(self) -> None:
        """Should report TOOLS_CHANGED when current tools are missing some."""
        locked_tools = ["query", "describe_table"]
        lockfile = Lockfile(
            servers={
                "pg": _locked_server(
                    tools=locked_tools,
                    tools_hash=compute_tools_hash(locked_tools),
                )
            },
        )
        installed = [_installed("pg")]
        current_tools = ["query"]
        healths = [_healthy("pg", current_tools)]

        result = diff_lockfile(lockfile, installed, healths)

        tools_drift = [e for e in result if e.drift_type == DriftType.TOOLS_CHANGED]
        assert len(tools_drift) == 1
        entry = tools_drift[0]
        assert "describe_table" in entry.detail
        assert "removed" in entry.detail

    def test_tools_added_and_removed(self) -> None:
        """Should report both added and removed in the detail."""
        locked_tools = ["old_tool", "shared"]
        lockfile = Lockfile(
            servers={
                "pg": _locked_server(
                    tools=locked_tools,
                    tools_hash=compute_tools_hash(locked_tools),
                )
            },
        )
        installed = [_installed("pg")]
        current_tools = ["new_tool", "shared"]
        healths = [_healthy("pg", current_tools)]

        result = diff_lockfile(lockfile, installed, healths)

        tools_drift = [e for e in result if e.drift_type == DriftType.TOOLS_CHANGED]
        assert len(tools_drift) == 1
        detail = tools_drift[0].detail
        assert "added" in detail
        assert "new_tool" in detail
        assert "removed" in detail
        assert "old_tool" in detail

    def test_same_tools_different_order_no_drift(self) -> None:
        """Should NOT report drift if tools are same but in different order.

        compute_tools_hash sorts before hashing, and diff_lockfile sorts
        current_tools before hashing, so order should not matter.
        """
        locked_tools = ["b_tool", "a_tool"]
        lockfile = Lockfile(
            servers={
                "pg": _locked_server(
                    tools=locked_tools,
                    tools_hash=compute_tools_hash(locked_tools),
                )
            },
        )
        installed = [_installed("pg")]
        healths = [_healthy("pg", ["a_tool", "b_tool"])]

        result = diff_lockfile(lockfile, installed, healths)
        tools_drift = [e for e in result if e.drift_type == DriftType.TOOLS_CHANGED]
        assert tools_drift == []


# === diff_lockfile: Tools check skip conditions =============================


class TestToolsCheckSkipped:
    """Tests for conditions that skip the tools hash comparison."""

    def test_no_health_data_skips_tools_check(self) -> None:
        """Should not check tools when healths is None."""
        tools = ["query"]
        lockfile = Lockfile(
            servers={
                "pg": _locked_server(
                    tools=tools,
                    tools_hash=compute_tools_hash(tools),
                )
            },
        )
        installed = [_installed("pg")]
        # Pass None for healths (the default)
        result = diff_lockfile(lockfile, installed, healths=None)

        tools_drift = [e for e in result if e.drift_type == DriftType.TOOLS_CHANGED]
        assert tools_drift == []

    def test_empty_health_list_skips_tools_check(self) -> None:
        """Should not check tools when healths is empty list."""
        tools = ["query"]
        lockfile = Lockfile(
            servers={
                "pg": _locked_server(
                    tools=tools,
                    tools_hash=compute_tools_hash(tools),
                )
            },
        )
        installed = [_installed("pg")]
        result = diff_lockfile(lockfile, installed, healths=[])

        tools_drift = [e for e in result if e.drift_type == DriftType.TOOLS_CHANGED]
        assert tools_drift == []

    def test_unhealthy_server_skips_tools_check(self) -> None:
        """Should not check tools for unhealthy servers."""
        locked_tools = ["query"]
        lockfile = Lockfile(
            servers={
                "pg": _locked_server(
                    tools=locked_tools,
                    tools_hash=compute_tools_hash(locked_tools),
                )
            },
        )
        installed = [_installed("pg")]
        # Unhealthy server has different tools, but should be skipped
        healths = [_unhealthy("pg")]

        result = diff_lockfile(lockfile, installed, healths)
        tools_drift = [e for e in result if e.drift_type == DriftType.TOOLS_CHANGED]
        assert tools_drift == []

    def test_timeout_server_skips_tools_check(self) -> None:
        """Should not check tools for servers with timeout status."""
        locked_tools = ["query"]
        lockfile = Lockfile(
            servers={
                "pg": _locked_server(
                    tools=locked_tools,
                    tools_hash=compute_tools_hash(locked_tools),
                )
            },
        )
        installed = [_installed("pg")]
        healths = [
            ServerHealth(name="pg", status="timeout", error="timed out")
        ]

        result = diff_lockfile(lockfile, installed, healths)
        tools_drift = [e for e in result if e.drift_type == DriftType.TOOLS_CHANGED]
        assert tools_drift == []

    def test_no_locked_tools_skips_tools_check(self) -> None:
        """Should not check tools when locked server has no tools."""
        lockfile = Lockfile(
            servers={
                "pg": _locked_server(tools=[], tools_hash=None)
            },
        )
        installed = [_installed("pg")]
        healths = [_healthy("pg", ["query", "list_tables"])]

        result = diff_lockfile(lockfile, installed, healths)
        tools_drift = [e for e in result if e.drift_type == DriftType.TOOLS_CHANGED]
        assert tools_drift == []

    def test_health_for_wrong_server_skips_tools_check(self) -> None:
        """Should skip tools check when health data exists but for a different server."""
        locked_tools = ["query"]
        lockfile = Lockfile(
            servers={
                "pg": _locked_server(
                    tools=locked_tools,
                    tools_hash=compute_tools_hash(locked_tools),
                )
            },
        )
        installed = [_installed("pg")]
        # Health data only for "redis", not "pg"
        healths = [_healthy("redis", ["other_tool"])]

        result = diff_lockfile(lockfile, installed, healths)
        tools_drift = [e for e in result if e.drift_type == DriftType.TOOLS_CHANGED]
        assert tools_drift == []


# === diff_lockfile: Multiple drift types combined ===========================


class TestCombinedDrift:
    """Tests producing multiple drift entries of different types."""

    def test_missing_and_extra_together(self) -> None:
        """Should report MISSING for locked-only and EXTRA for installed-only."""
        lockfile = Lockfile(
            servers={"locked-only": _locked_server()},
        )
        installed = [_installed("installed-only")]

        result = diff_lockfile(lockfile, installed)

        assert len(result) == 2
        types = {e.drift_type for e in result}
        assert types == {DriftType.MISSING, DriftType.EXTRA}
        missing = next(e for e in result if e.drift_type == DriftType.MISSING)
        extra = next(e for e in result if e.drift_type == DriftType.EXTRA)
        assert missing.server == "locked-only"
        assert extra.server == "installed-only"

    def test_config_and_tools_drift_for_same_server(self) -> None:
        """Should report both CONFIG_CHANGED and TOOLS_CHANGED for one server."""
        locked_tools = ["query"]
        lockfile = Lockfile(
            servers={
                "pg": _locked_server(
                    command="npx",
                    args=["-y", "old-pkg"],
                    tools=locked_tools,
                    tools_hash=compute_tools_hash(locked_tools),
                )
            },
        )
        installed = [_installed("pg", command="uvx", args=["new-pkg"])]
        healths = [_healthy("pg", ["query", "new_tool"])]

        result = diff_lockfile(lockfile, installed, healths)

        types = {e.drift_type for e in result}
        assert DriftType.CONFIG_CHANGED in types
        assert DriftType.TOOLS_CHANGED in types

    def test_complex_scenario_multiple_servers(self) -> None:
        """Should handle a mix of missing, extra, config drift, tools drift."""
        locked_tools_pg = ["query", "describe"]
        lockfile = Lockfile(
            servers={
                "pg": _locked_server(
                    command="npx",
                    args=["-y", "pg"],
                    tools=locked_tools_pg,
                    tools_hash=compute_tools_hash(locked_tools_pg),
                ),
                "redis": _locked_server(command="uvx", args=["redis-mcp"]),
                "missing-svr": _locked_server(),
            },
        )
        installed = [
            _installed("pg", command="npx", args=["-y", "pg"]),  # config matches
            _installed("redis", command="npx", args=["redis-mcp"]),  # config changed!
            _installed("extra-svr"),  # not in lockfile
        ]
        # pg tools changed, redis has no health data
        healths = [_healthy("pg", ["query", "new_tool"])]

        result = diff_lockfile(lockfile, installed, healths)

        servers_and_types = [(e.server, e.drift_type) for e in result]
        assert ("missing-svr", DriftType.MISSING) in servers_and_types
        assert ("extra-svr", DriftType.EXTRA) in servers_and_types
        assert ("redis", DriftType.CONFIG_CHANGED) in servers_and_types
        assert ("pg", DriftType.TOOLS_CHANGED) in servers_and_types


# === _check_config_drift: Unit tests =======================================


class TestCheckConfigDrift:
    """Direct tests for the _check_config_drift helper."""

    def test_identical_config_returns_empty(self) -> None:
        """Should return empty list when config matches exactly."""
        locked = _locked_server(command="npx", args=["-y", "pkg"])
        installed = _installed("svr", command="npx", args=["-y", "pkg"])
        result = _check_config_drift("svr", locked, installed)
        assert result == []

    def test_command_differs_returns_drift(self) -> None:
        """Should return one CONFIG_CHANGED when command differs."""
        locked = _locked_server(command="npx", args=[])
        installed = _installed("svr", command="uvx", args=[])
        result = _check_config_drift("svr", locked, installed)

        assert len(result) == 1
        assert result[0].drift_type == DriftType.CONFIG_CHANGED
        assert result[0].server == "svr"

    def test_args_differ_returns_drift(self) -> None:
        """Should return one CONFIG_CHANGED when args differ."""
        locked = _locked_server(command="npx", args=["a"])
        installed = _installed("svr", command="npx", args=["b"])
        result = _check_config_drift("svr", locked, installed)

        assert len(result) == 1
        assert result[0].drift_type == DriftType.CONFIG_CHANGED

    def test_empty_args_vs_no_args(self) -> None:
        """Should not report drift when both have empty args."""
        locked = _locked_server(command="npx", args=[])
        installed = _installed("svr", command="npx", args=[])
        result = _check_config_drift("svr", locked, installed)
        assert result == []

    def test_detail_contains_both_configs(self) -> None:
        """Detail message should show both locked and installed configs."""
        locked = _locked_server(command="npx", args=["old"])
        installed = _installed("svr", command="uvx", args=["new"])
        result = _check_config_drift("svr", locked, installed)

        detail = result[0].detail
        assert "Locked config:" in detail
        assert "Installed config:" in detail
        assert "npx" in detail
        assert "uvx" in detail


# === _check_tools_drift: Unit tests ========================================


class TestCheckToolsDrift:
    """Direct tests for the _check_tools_drift helper."""

    def test_matching_tools_returns_empty(self) -> None:
        """Should return empty list when tools match."""
        tools = ["query", "describe"]
        locked = _locked_server(tools=tools, tools_hash=compute_tools_hash(tools))
        health = _healthy("pg", tools)
        result = _check_tools_drift("pg", locked, health)
        assert result == []

    def test_added_tools_reports_drift(self) -> None:
        """Should detect added tools."""
        locked_tools = ["query"]
        locked = _locked_server(
            tools=locked_tools, tools_hash=compute_tools_hash(locked_tools)
        )
        health = _healthy("pg", ["query", "new_tool"])
        result = _check_tools_drift("pg", locked, health)

        assert len(result) == 1
        assert result[0].drift_type == DriftType.TOOLS_CHANGED
        assert "new_tool" in result[0].detail
        assert "added" in result[0].detail

    def test_removed_tools_reports_drift(self) -> None:
        """Should detect removed tools."""
        locked_tools = ["query", "describe"]
        locked = _locked_server(
            tools=locked_tools, tools_hash=compute_tools_hash(locked_tools)
        )
        health = _healthy("pg", ["query"])
        result = _check_tools_drift("pg", locked, health)

        assert len(result) == 1
        assert "describe" in result[0].detail
        assert "removed" in result[0].detail

    def test_both_added_and_removed(self) -> None:
        """Should include both added and removed in detail."""
        locked_tools = ["old_a", "shared"]
        locked = _locked_server(
            tools=locked_tools, tools_hash=compute_tools_hash(locked_tools)
        )
        health = _healthy("pg", ["shared", "new_b"])
        result = _check_tools_drift("pg", locked, health)

        assert len(result) == 1
        detail = result[0].detail
        assert "added" in detail
        assert "new_b" in detail
        assert "removed" in detail
        assert "old_a" in detail

    def test_severity_is_error(self) -> None:
        """Tools drift should always be ERROR severity."""
        locked_tools = ["query"]
        locked = _locked_server(
            tools=locked_tools, tools_hash=compute_tools_hash(locked_tools)
        )
        health = _healthy("pg", ["completely_different"])
        result = _check_tools_drift("pg", locked, health)

        assert result[0].severity == DriftSeverity.ERROR

    def test_detail_includes_server_name(self) -> None:
        """Detail message should include the server name."""
        locked_tools = ["query"]
        locked = _locked_server(
            tools=locked_tools, tools_hash=compute_tools_hash(locked_tools)
        )
        health = _healthy("my-server", ["other"])
        result = _check_tools_drift("my-server", locked, health)

        assert "my-server" in result[0].detail

    def test_added_tools_are_sorted_in_detail(self) -> None:
        """Added and removed tool lists in detail should be sorted."""
        locked_tools = ["a"]
        locked = _locked_server(
            tools=locked_tools, tools_hash=compute_tools_hash(locked_tools)
        )
        health = _healthy("pg", ["z_tool", "a_tool", "m_tool"])
        result = _check_tools_drift("pg", locked, health)

        detail = result[0].detail
        # The added list should contain sorted tool names
        assert "['a_tool', 'm_tool', 'z_tool']" in detail


# === DriftEntry model tests =================================================


class TestDriftEntryModel:
    """Tests for the DriftEntry dataclass."""

    def test_frozen(self) -> None:
        """DriftEntry should be immutable."""
        entry = DriftEntry(server="test", drift_type=DriftType.MISSING)
        with pytest.raises(AttributeError):
            entry.server = "other"  # type: ignore[misc]

    def test_default_severity_is_warning(self) -> None:
        """DriftEntry severity should default to WARNING."""
        entry = DriftEntry(server="test", drift_type=DriftType.MISSING)
        assert entry.severity == DriftSeverity.WARNING

    def test_default_detail_is_empty(self) -> None:
        """DriftEntry detail should default to empty string."""
        entry = DriftEntry(server="test", drift_type=DriftType.MISSING)
        assert entry.detail == ""
