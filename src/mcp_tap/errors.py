"""Exception hierarchy for mcp-tap.

All exceptions inherit from McpTapError (single catch point).
Messages are written for LLM consumption -- clear, actionable, no stack traces.
"""

from __future__ import annotations


class McpTapError(Exception):
    """Base exception for all mcp-tap errors."""


class RegistryError(McpTapError):
    """Error communicating with the MCP Registry API."""


class ConfigReadError(McpTapError):
    """Error reading an MCP client config file."""


class ConfigWriteError(McpTapError):
    """Error writing to an MCP client config file."""


class ClientNotFoundError(McpTapError):
    """No MCP client detected on this machine."""


class ServerNotFoundError(McpTapError):
    """Server name not found in config file."""


class InstallerNotFoundError(McpTapError):
    """Required package manager is not installed."""


class InstallError(McpTapError):
    """Package installation failed."""


class ScanError(McpTapError):
    """Error scanning a project directory."""
