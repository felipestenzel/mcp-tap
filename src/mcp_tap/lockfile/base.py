"""Ports: Lockfile reading, writing, and verification."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from mcp_tap.models import LockedServer, Lockfile, VerifyResult


class LockfileReaderPort(Protocol):
    """Port for reading and parsing mcp-tap.lock files."""

    def read_lockfile(self, project_path: Path | str) -> Lockfile | None:
        """Read the lockfile from a project directory. Returns None if not found."""
        ...


class LockfileWriterPort(Protocol):
    """Port for writing mcp-tap.lock files."""

    def write_lockfile(self, lockfile: Lockfile, project_path: Path | str) -> None:
        """Write the lockfile to a project directory."""
        ...

    def add_server(
        self,
        project_path: Path | str,
        server_name: str,
        server: LockedServer,
    ) -> None:
        """Add or update a single server in the lockfile."""
        ...

    def remove_server(self, project_path: Path | str, server_name: str) -> None:
        """Remove a server from the lockfile."""
        ...


class LockfileDifferPort(Protocol):
    """Port for computing drift between lockfile and actual state."""

    async def verify(self, project_path: str, *, client: str = "") -> VerifyResult:
        """Compare lockfile against installed servers and report drift."""
        ...
