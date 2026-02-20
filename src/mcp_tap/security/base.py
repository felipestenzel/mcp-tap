"""Port: Pre-install security gate."""

from __future__ import annotations

from typing import Protocol

from mcp_tap.models import SecurityReport


class SecurityGatePort(Protocol):
    """Port for running pre-install security checks on MCP packages."""

    async def run_security_gate(
        self,
        package_identifier: str,
        repository_url: str,
        command: str,
        args: list[str],
    ) -> SecurityReport:
        """Run all security checks and return an aggregated report."""
        ...
