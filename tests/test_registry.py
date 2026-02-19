"""Tests for the MCP Registry client."""

from __future__ import annotations

import httpx
import pytest

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
