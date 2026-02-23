"""Tests for canonical matching helpers (config/matching.py)."""

from __future__ import annotations

from mcp_tap.config.matching import (
    find_matching_installed_server,
    find_matching_locked_server,
    installed_matches_package_identifier,
)
from mcp_tap.models import (
    HttpServerConfig,
    InstalledServer,
    LockedConfig,
    LockedServer,
    ServerConfig,
)


def _installed_stdio(name: str, args: list[str]) -> InstalledServer:
    return InstalledServer(
        name=name,
        config=ServerConfig(command="npx", args=args),
        source_file="/tmp/config.json",
    )


def _installed_http(name: str, url: str) -> InstalledServer:
    return InstalledServer(
        name=name,
        config=HttpServerConfig(url=url, transport_type="http"),
        source_file="/tmp/config.json",
    )


def _locked(
    name: str,
    package_identifier: str,
    args: list[str] | None = None,
) -> tuple[str, LockedServer]:
    return (
        name,
        LockedServer(
            package_identifier=package_identifier,
            registry_type="npm",
            version="1.0.0",
            config=LockedConfig(
                command="npx",
                args=args or ["-y", package_identifier],
                env_keys=[],
            ),
            tools=[],
            tools_hash="",
            installed_at="2026-02-23T00:00:00Z",
        ),
    )


class TestInstalledMatchesPackageIdentifier:
    def test_matches_by_command_args_for_stdio(self) -> None:
        installed = _installed_stdio("pg", ["-y", "@mcp/server-postgres"])
        assert installed_matches_package_identifier(installed, "@mcp/server-postgres") is True

    def test_matches_http_native_by_url(self) -> None:
        installed = _installed_http("vercel", "https://mcp.vercel.com")
        assert installed_matches_package_identifier(installed, "https://mcp.vercel.com") is True

    def test_matches_mcp_remote_by_url(self) -> None:
        installed = _installed_stdio("vercel", ["-y", "mcp-remote", "https://mcp.vercel.com"])
        assert installed_matches_package_identifier(installed, "https://mcp.vercel.com") is True

    def test_returns_false_when_identifier_differs(self) -> None:
        installed = _installed_stdio("pg", ["-y", "@mcp/server-postgres"])
        assert installed_matches_package_identifier(installed, "@mcp/server-redis") is False


class TestFindMatchingInstalledServer:
    def test_prefers_name_match(self) -> None:
        _, locked = _locked("postgres-mcp", "@mcp/server-postgres")
        installed = [
            _installed_stdio("postgres-mcp", ["-y", "something-else"]),
            _installed_stdio("pg", ["-y", "@mcp/server-postgres"]),
        ]

        match = find_matching_installed_server("postgres-mcp", locked, installed)
        assert match is not None
        assert match.name == "postgres-mcp"

    def test_falls_back_to_package_identifier_when_alias_differs(self) -> None:
        _, locked = _locked("postgres-mcp", "@mcp/server-postgres")
        installed = [_installed_stdio("pg", ["-y", "@mcp/server-postgres"])]

        match = find_matching_installed_server("postgres-mcp", locked, installed)
        assert match is not None
        assert match.name == "pg"

    def test_skips_used_installed_names(self) -> None:
        _, locked = _locked("postgres-mcp", "@mcp/server-postgres")
        installed = [
            _installed_stdio("pg", ["-y", "@mcp/server-postgres"]),
            _installed_stdio("pg-backup", ["-y", "@mcp/server-postgres"]),
        ]

        match = find_matching_installed_server(
            "postgres-mcp", locked, installed, used_installed_names={"pg"}
        )
        assert match is not None
        assert match.name == "pg-backup"


class TestFindMatchingLockedServer:
    def test_matches_by_name(self) -> None:
        locked_name, locked = _locked("pg", "@mcp/server-postgres")
        installed = _installed_stdio("pg", ["-y", "anything"])

        match = find_matching_locked_server(installed, {locked_name: locked})
        assert match is not None
        assert match[0] == "pg"

    def test_matches_by_canonical_identifier_with_alias(self) -> None:
        locked_name, locked = _locked("postgres-mcp", "@mcp/server-postgres")
        installed = _installed_stdio("pg", ["-y", "@mcp/server-postgres"])

        match = find_matching_locked_server(installed, {locked_name: locked})
        assert match is not None
        assert match[0] == "postgres-mcp"
