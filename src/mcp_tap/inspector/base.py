"""Ports: README fetching and config hint extraction."""

from __future__ import annotations

from typing import Protocol

from mcp_tap.models import ConfigHints


class ReadmeFetcherPort(Protocol):
    """Port for fetching README files from repository URLs."""

    async def fetch_readme(
        self,
        repository_url: str,
    ) -> str | None:
        """Fetch README.md content from a repository URL."""
        ...


class ConfigHintExtractorPort(Protocol):
    """Port for extracting configuration hints from README markdown."""

    def extract_config_hints(self, readme: str) -> ConfigHints:
        """Extract structured config hints (env vars, commands, transport) from README."""
        ...
