"""Tests for the MCP Registry client."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx

from mcp_tap.registry.client import RegistryClient


class TestRegistryClientParsing:
    """Test the parsing logic without hitting the network."""

    def _make_client(self) -> RegistryClient:
        return RegistryClient(http=httpx.AsyncClient())

    def test_parse_server_minimal(self):
        client = self._make_client()
        raw = {"name": "test-server", "description": "A test"}
        server = client._parse_server(raw)
        assert server.name == "test-server"
        assert server.description == "A test"
        assert server.packages == []

    def test_parse_server_with_packages(self):
        client = self._make_client()
        raw = {
            "name": "pg-server",
            "description": "PostgreSQL MCP",
            "version": "1.0.0",
            "packages": [
                {
                    "registryType": "npm",
                    "identifier": "@mcp/server-postgres",
                    "transport": "stdio",
                    "environmentVariables": [
                        {"name": "POSTGRES_URL", "isRequired": True, "isSecret": False}
                    ],
                }
            ],
            "repository": {"url": "https://github.com/test/repo"},
            "_meta": {"isOfficial": True, "updatedAt": "2026-01-01"},
        }
        server = client._parse_server(raw)
        assert server.name == "pg-server"
        assert server.is_official is True
        assert len(server.packages) == 1
        assert server.packages[0].identifier == "@mcp/server-postgres"
        assert len(server.packages[0].environment_variables) == 1
        assert server.packages[0].environment_variables[0].name == "POSTGRES_URL"
        assert server.repository_url == "https://github.com/test/repo"

    def test_parse_server_unknown_registry_type(self):
        client = self._make_client()
        raw = {
            "name": "weird",
            "description": "test",
            "packages": [{"registryType": "unknown_type", "identifier": "pkg"}],
        }
        server = client._parse_server(raw)
        assert server.packages[0].registry_type.value == "npm"  # fallback

    def test_parse_server_missing_fields(self):
        client = self._make_client()
        raw = {}
        server = client._parse_server(raw)
        assert server.name == ""
        assert server.description == ""
        assert server.packages == []


class TestWrappedResponseFormat:
    """Test parsing the current API format where server data is wrapped."""

    def _make_client(self) -> RegistryClient:
        return RegistryClient(http=httpx.AsyncClient())

    def test_parse_entry_wrapped_format(self):
        client = self._make_client()
        entry = {
            "server": {
                "name": "io.github.user/my-server",
                "description": "A wrapped server",
                "version": "2.0.0",
                "packages": [
                    {
                        "registryType": "npm",
                        "identifier": "@user/my-server",
                        "transport": "stdio",
                    }
                ],
                "repository": {"url": "https://github.com/user/my-server"},
            },
            "_meta": {
                "io.modelcontextprotocol.registry/official": {
                    "status": "active",
                    "publishedAt": "2026-01-15T10:00:00Z",
                    "updatedAt": "2026-02-01T12:00:00Z",
                    "isLatest": True,
                }
            },
        }
        server = client._parse_entry(entry)
        assert server.name == "io.github.user/my-server"
        assert server.description == "A wrapped server"
        assert server.version == "2.0.0"
        assert server.is_official is True
        assert server.updated_at == "2026-02-01T12:00:00Z"
        assert len(server.packages) == 1
        assert server.packages[0].identifier == "@user/my-server"
        assert server.repository_url == "https://github.com/user/my-server"

    def test_parse_entry_flat_format_still_works(self):
        """Legacy format where server fields are at the top level."""
        client = self._make_client()
        entry = {
            "name": "flat-server",
            "description": "Old format",
            "packages": [],
            "_meta": {"isOfficial": False, "updatedAt": "2025-06-01"},
        }
        server = client._parse_entry(entry)
        assert server.name == "flat-server"
        assert server.is_official is False
        assert server.updated_at == "2025-06-01"

    def test_parse_entry_meta_not_official(self):
        client = self._make_client()
        entry = {
            "server": {
                "name": "community-server",
                "description": "Not official",
            },
            "_meta": {
                "io.modelcontextprotocol.registry/official": {
                    "status": "inactive",
                    "updatedAt": "2026-01-01T00:00:00Z",
                }
            },
        }
        server = client._parse_entry(entry)
        assert server.is_official is False


class TestRemotesFormat:
    """Test parsing the 'remotes' format used by hosted MCP servers."""

    def _make_client(self) -> RegistryClient:
        return RegistryClient(http=httpx.AsyncClient())

    def test_parse_remotes_basic(self):
        client = self._make_client()
        raw = {
            "name": "ai.waystation/postgres",
            "description": "Hosted PostgreSQL MCP",
            "version": "0.3.1",
            "remotes": [
                {
                    "type": "streamable-http",
                    "url": "https://waystation.ai/postgres/mcp",
                },
                {
                    "type": "sse",
                    "url": "https://waystation.ai/postgres/mcp/sse",
                },
            ],
            "repository": {"url": "https://github.com/waystation-ai/mcp"},
        }
        server = client._parse_server(raw)
        assert server.name == "ai.waystation/postgres"
        assert len(server.packages) == 2
        assert server.packages[0].transport.value == "streamable-http"
        assert server.packages[0].identifier == "https://waystation.ai/postgres/mcp"
        assert server.packages[1].transport.value == "sse"

    def test_parse_remotes_with_headers(self):
        client = self._make_client()
        raw = {
            "name": "ai.smithery/slack",
            "description": "Hosted Slack MCP",
            "version": "1.0.0",
            "remotes": [
                {
                    "type": "streamable-http",
                    "url": "https://server.smithery.ai/slack/mcp",
                    "headers": [
                        {
                            "name": "Authorization",
                            "description": "Bearer token for Smithery",
                            "isRequired": True,
                            "isSecret": True,
                        }
                    ],
                }
            ],
        }
        server = client._parse_server(raw)
        assert len(server.packages) == 1
        pkg = server.packages[0]
        assert len(pkg.environment_variables) == 1
        assert pkg.environment_variables[0].name == "Authorization"
        assert pkg.environment_variables[0].is_secret is True
        assert pkg.environment_variables[0].is_required is True

    def test_parse_remotes_empty_headers(self):
        client = self._make_client()
        raw = {
            "name": "no-auth",
            "description": "No auth needed",
            "remotes": [{"type": "sse", "url": "https://example.com/sse"}],
        }
        server = client._parse_server(raw)
        assert len(server.packages) == 1
        assert server.packages[0].environment_variables == []

    def test_packages_preferred_over_remotes(self):
        """If both packages and remotes exist, packages wins."""
        client = self._make_client()
        raw = {
            "name": "dual-format",
            "description": "Has both",
            "packages": [
                {"registryType": "npm", "identifier": "@dual/server", "transport": "stdio"}
            ],
            "remotes": [{"type": "streamable-http", "url": "https://example.com/mcp"}],
        }
        server = client._parse_server(raw)
        assert len(server.packages) == 1
        assert server.packages[0].identifier == "@dual/server"
        assert server.packages[0].transport.value == "stdio"

    def test_remotes_unknown_transport_fallback(self):
        client = self._make_client()
        raw = {
            "name": "weird-transport",
            "description": "Unknown transport type",
            "remotes": [{"type": "grpc", "url": "https://example.com/mcp"}],
        }
        server = client._parse_server(raw)
        assert server.packages[0].transport.value == "streamable-http"


class TestTransportFieldFormats:
    """Test transport field as string or dict."""

    def _make_client(self) -> RegistryClient:
        return RegistryClient(http=httpx.AsyncClient())

    def test_transport_as_string(self):
        client = self._make_client()
        raw = {
            "name": "str-transport",
            "description": "Legacy",
            "packages": [{"registryType": "npm", "identifier": "pkg", "transport": "stdio"}],
        }
        server = client._parse_server(raw)
        assert server.packages[0].transport.value == "stdio"

    def test_transport_as_dict(self):
        client = self._make_client()
        raw = {
            "name": "dict-transport",
            "description": "Current",
            "packages": [
                {
                    "registryType": "npm",
                    "identifier": "pkg",
                    "transport": {"type": "streamable-http", "url": "http://localhost:8080/mcp"},
                }
            ],
        }
        server = client._parse_server(raw)
        assert server.packages[0].transport.value == "streamable-http"

    def test_transport_as_dict_sse(self):
        client = self._make_client()
        raw = {
            "name": "sse-dict",
            "description": "SSE transport",
            "packages": [
                {
                    "registryType": "npm",
                    "identifier": "pkg",
                    "transport": {"type": "sse", "url": "http://localhost:8080/sse"},
                }
            ],
        }
        server = client._parse_server(raw)
        assert server.packages[0].transport.value == "sse"

    def test_transport_dict_unknown_type_fallback(self):
        client = self._make_client()
        raw = {
            "name": "unknown-dict",
            "description": "Unknown transport type in dict",
            "packages": [
                {
                    "registryType": "npm",
                    "identifier": "pkg",
                    "transport": {"type": "websocket"},
                }
            ],
        }
        server = client._parse_server(raw)
        assert server.packages[0].transport.value == "stdio"


class TestSearchResponseParsing:
    """Test full search response parsing with wrapped entries."""

    def _make_client(self) -> RegistryClient:
        return RegistryClient(http=httpx.AsyncClient())

    async def test_search_parses_wrapped_entries(self):
        client = self._make_client()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "servers": [
                {
                    "server": {
                        "name": "io.github.user/pg-mcp",
                        "description": "PostgreSQL",
                        "version": "1.0.0",
                        "packages": [
                            {
                                "registryType": "npm",
                                "identifier": "@user/pg-mcp",
                                "transport": "stdio",
                            }
                        ],
                    },
                    "_meta": {
                        "io.modelcontextprotocol.registry/official": {
                            "status": "active",
                            "updatedAt": "2026-02-01T00:00:00Z",
                        }
                    },
                },
                {
                    "server": {
                        "name": "ai.waystation/postgres",
                        "description": "Hosted PG",
                        "version": "0.3.1",
                        "remotes": [
                            {
                                "type": "streamable-http",
                                "url": "https://waystation.ai/pg/mcp",
                            }
                        ],
                    },
                    "_meta": {
                        "io.modelcontextprotocol.registry/official": {
                            "status": "active",
                            "updatedAt": "2026-01-15T00:00:00Z",
                        }
                    },
                },
            ],
            "metadata": {"count": 2},
        }

        mock_get = AsyncMock(return_value=mock_response)
        with patch.object(client.http, "get", mock_get):
            results = await client.search("postgres")

        assert len(results) == 2
        assert results[0].name == "io.github.user/pg-mcp"
        assert results[0].is_official is True
        assert len(results[0].packages) == 1
        assert results[0].packages[0].identifier == "@user/pg-mcp"

        assert results[1].name == "ai.waystation/postgres"
        assert len(results[1].packages) == 1
        assert results[1].packages[0].transport.value == "streamable-http"


class TestGetServerEndpoint:
    """Test get_server uses the correct versioned endpoint."""

    def _make_client(self) -> RegistryClient:
        return RegistryClient(http=httpx.AsyncClient())

    async def test_get_server_url_encoding(self):
        client = self._make_client()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "server": {
                "name": "io.github.user/my-server",
                "description": "Test",
                "version": "1.0.0",
            },
            "_meta": {
                "io.modelcontextprotocol.registry/official": {
                    "status": "active",
                    "updatedAt": "2026-02-01T00:00:00Z",
                }
            },
        }

        mock_get = AsyncMock(return_value=mock_response)
        with patch.object(client.http, "get", mock_get):
            result = await client.get_server("io.github.user/my-server")

        called_url = mock_get.call_args[0][0]
        assert "io.github.user%2Fmy-server" in called_url
        assert "/versions/latest" in called_url
        assert result is not None
        assert result.name == "io.github.user/my-server"

    async def test_get_server_404_returns_none(self):
        client = self._make_client()
        mock_response = MagicMock()
        mock_response.status_code = 404

        mock_get = AsyncMock(return_value=mock_response)
        with patch.object(client.http, "get", mock_get):
            result = await client.get_server("nonexistent/server")

        assert result is None
