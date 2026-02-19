"""Tests for inspector module -- fetcher and extractor."""

from __future__ import annotations

from unittest.mock import AsyncMock

import httpx

from mcp_tap.inspector.extractor import extract_config_hints
from mcp_tap.inspector.fetcher import _github_raw_url, _gitlab_raw_url, fetch_readme

# ─── Fetcher URL conversion ─────────────────────────────────


class TestGitHubRawUrl:
    def test_standard_repo(self) -> None:
        url = _github_raw_url("https://github.com/owner/repo")
        assert url == "https://raw.githubusercontent.com/owner/repo/HEAD/README.md"

    def test_repo_with_trailing_slash(self) -> None:
        url = _github_raw_url("https://github.com/owner/repo/")
        assert url == "https://raw.githubusercontent.com/owner/repo/HEAD/README.md"

    def test_monorepo_subpath(self) -> None:
        url = _github_raw_url("https://github.com/org/monorepo/tree/main/packages/server-foo")
        assert url == (
            "https://raw.githubusercontent.com/org/monorepo/main/packages/server-foo/README.md"
        )

    def test_non_github_returns_empty(self) -> None:
        assert _github_raw_url("https://gitlab.com/owner/repo") == ""


class TestGitLabRawUrl:
    def test_standard_repo(self) -> None:
        url = _gitlab_raw_url("https://gitlab.com/owner/repo")
        assert url == "https://gitlab.com/owner/repo/-/raw/main/README.md"

    def test_non_gitlab_returns_empty(self) -> None:
        assert _gitlab_raw_url("https://github.com/owner/repo") == ""


# ─── Fetcher async ───────────────────────────────────────────


class TestFetchReadme:
    async def test_successful_fetch(self) -> None:
        mock_response = httpx.Response(200, text="# My Server\nThis is a test.")
        client = AsyncMock(spec=httpx.AsyncClient)
        client.get = AsyncMock(return_value=mock_response)

        result = await fetch_readme("https://github.com/owner/repo", client)
        assert result == "# My Server\nThis is a test."

    async def test_404_returns_none(self) -> None:
        mock_response = httpx.Response(404)
        client = AsyncMock(spec=httpx.AsyncClient)
        client.get = AsyncMock(return_value=mock_response)

        result = await fetch_readme("https://github.com/owner/repo", client)
        assert result is None

    async def test_network_error_returns_none(self) -> None:
        client = AsyncMock(spec=httpx.AsyncClient)
        client.get = AsyncMock(side_effect=httpx.ConnectError("Connection failed"))

        result = await fetch_readme("https://github.com/owner/repo", client)
        assert result is None


# ─── Extractor ───────────────────────────────────────────────

SAMPLE_README = """\
# MCP Server Postgres

A Model Context Protocol server for PostgreSQL databases.

## Installation

```bash
npm install @modelcontextprotocol/server-postgres
```

Or run directly:

```bash
npx -y @modelcontextprotocol/server-postgres --port 5432
```

## Configuration

The server uses **stdio** transport by default.

Set the following environment variables:

```bash
export POSTGRES_CONNECTION_STRING="postgresql://user:pass@localhost:5432/db"
export POSTGRES_SSL_MODE="require"  # optional
```

### MCP Client Config

```json
{
  "command": "npx",
  "args": ["-y", "@modelcontextprotocol/server-postgres"],
  "env": {
    "POSTGRES_CONNECTION_STRING": "postgresql://..."
  }
}
```

## Docker

```bash
docker run -e POSTGRES_CONNECTION_STRING=... mcp/postgres
```
"""


class TestExtractConfigHints:
    def test_extracts_install_commands(self) -> None:
        hints = extract_config_hints(SAMPLE_README)
        assert any("npm install" in cmd for cmd in hints.install_commands)

    def test_extracts_npx_command(self) -> None:
        hints = extract_config_hints(SAMPLE_README)
        assert any("npx" in cmd for cmd in hints.install_commands)

    def test_extracts_docker_command(self) -> None:
        hints = extract_config_hints(SAMPLE_README)
        assert any("docker run" in cmd.lower() for cmd in hints.install_commands)

    def test_extracts_env_vars(self) -> None:
        hints = extract_config_hints(SAMPLE_README)
        var_names = [ev.name for ev in hints.env_vars_mentioned]
        assert "POSTGRES_CONNECTION_STRING" in var_names

    def test_extracts_transport_hints(self) -> None:
        hints = extract_config_hints(SAMPLE_README)
        assert "stdio" in hints.transport_hints

    def test_extracts_json_config(self) -> None:
        hints = extract_config_hints(SAMPLE_README)
        assert len(hints.json_config_blocks) >= 1

    def test_extracts_command_patterns(self) -> None:
        hints = extract_config_hints(SAMPLE_README)
        assert any("npx" in p for p in hints.command_patterns)

    def test_confidence_with_rich_readme(self) -> None:
        hints = extract_config_hints(SAMPLE_README)
        assert hints.confidence >= 0.5

    def test_confidence_with_empty_readme(self) -> None:
        hints = extract_config_hints("# Empty\nNo useful info here.")
        assert hints.confidence == 0.0

    def test_ignores_common_uppercase_words(self) -> None:
        hints = extract_config_hints(SAMPLE_README)
        var_names = [ev.name for ev in hints.env_vars_mentioned]
        assert "README" not in var_names
        assert "JSON" not in var_names
        assert "MCP" not in var_names

    def test_env_var_needs_underscore(self) -> None:
        readme = "```\nexport MYTOKEN=abc\n```"
        hints = extract_config_hints(readme)
        var_names = [ev.name for ev in hints.env_vars_mentioned]
        assert "MYTOKEN" not in var_names

    def test_env_var_with_underscore_kept(self) -> None:
        readme = "```\nexport MY_TOKEN=abc\n```"
        hints = extract_config_hints(readme)
        var_names = [ev.name for ev in hints.env_vars_mentioned]
        assert "MY_TOKEN" in var_names


# ─── Edge cases ──────────────────────────────────────────────


class TestExtractorEdgeCases:
    def test_empty_string(self) -> None:
        hints = extract_config_hints("")
        assert hints.confidence == 0.0
        assert hints.install_commands == []
        assert hints.env_vars_mentioned == []

    def test_no_code_blocks(self) -> None:
        hints = extract_config_hints("Just plain text, no code blocks at all.")
        assert hints.confidence == 0.0

    def test_multiple_transports(self) -> None:
        readme = "Supports stdio and streamable-http transports."
        hints = extract_config_hints(readme)
        assert "stdio" in hints.transport_hints
        assert "streamable-http" in hints.transport_hints

    def test_sse_transport(self) -> None:
        readme = "Connect via SSE at port 3000."
        hints = extract_config_hints(readme)
        assert "sse" in hints.transport_hints
