"""Domain models for mcp-tap. All frozen dataclasses -- no mutation after creation."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

# ─── Enumerations ─────────────────────────────────────────────


class Transport(StrEnum):
    STDIO = "stdio"
    SSE = "sse"
    STREAMABLE_HTTP = "streamable-http"


class RegistryType(StrEnum):
    NPM = "npm"
    PYPI = "pypi"
    OCI = "oci"


class MCPClient(StrEnum):
    CLAUDE_DESKTOP = "claude_desktop"
    CLAUDE_CODE = "claude_code"
    CURSOR = "cursor"
    WINDSURF = "windsurf"


# ─── Registry Models ──────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class EnvVarSpec:
    """An environment variable required by an MCP server package."""

    name: str
    description: str = ""
    is_required: bool = True
    is_secret: bool = False


@dataclass(frozen=True, slots=True)
class PackageInfo:
    """A specific package distribution of an MCP server."""

    registry_type: RegistryType
    identifier: str
    version: str = ""
    transport: Transport = Transport.STDIO
    environment_variables: list[EnvVarSpec] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class RegistryServer:
    """An MCP server as returned by the MCP Registry API."""

    name: str
    description: str
    version: str = ""
    repository_url: str = ""
    packages: list[PackageInfo] = field(default_factory=list)
    is_official: bool = False
    updated_at: str = ""


# ─── Config Models ────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class ServerConfig:
    """A single MCP server entry in a client config file."""

    command: str
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        result: dict[str, object] = {"command": self.command, "args": list(self.args)}
        if self.env:
            result["env"] = dict(self.env)
        return result


@dataclass(frozen=True, slots=True)
class ConfigLocation:
    """Location of an MCP client's config file on disk."""

    client: MCPClient
    path: str
    scope: str  # "user" or "project"
    exists: bool


@dataclass(frozen=True, slots=True)
class InstalledServer:
    """An MCP server currently configured in a client config file."""

    name: str
    config: ServerConfig
    source_file: str


# ─── Tool Return Models ───────────────────────────────────────


@dataclass(frozen=True, slots=True)
class SearchResult:
    name: str
    description: str
    version: str
    registry_type: str
    package_identifier: str
    transport: str
    is_official: bool
    updated_at: str
    env_vars_required: list[str]
    repository_url: str


@dataclass(frozen=True, slots=True)
class InstallResult:
    success: bool
    package_identifier: str
    install_method: str
    message: str
    command_output: str = ""


@dataclass(frozen=True, slots=True)
class ConfigureResult:
    success: bool
    server_name: str
    config_file: str
    message: str
    config_written: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ConnectionTestResult:
    success: bool
    server_name: str
    tools_discovered: list[str] = field(default_factory=list)
    error: str = ""


@dataclass(frozen=True, slots=True)
class RemoveResult:
    success: bool
    server_name: str
    config_file: str = ""
    uninstalled_package: bool = False
    message: str = ""


# ─── Scanner Models ──────────────────────────────────────────


class TechnologyCategory(StrEnum):
    LANGUAGE = "language"
    FRAMEWORK = "framework"
    DATABASE = "database"
    SERVICE = "service"
    PLATFORM = "platform"


@dataclass(frozen=True, slots=True)
class DetectedTechnology:
    """A technology detected by scanning project files."""

    name: str
    category: TechnologyCategory
    source_file: str
    confidence: float = 1.0


@dataclass(frozen=True, slots=True)
class ServerRecommendation:
    """A recommended MCP server based on detected project technologies."""

    server_name: str
    package_identifier: str
    registry_type: RegistryType
    reason: str
    priority: str  # "high", "medium", "low"


@dataclass(frozen=True, slots=True)
class ProjectProfile:
    """Aggregated scan result describing a project's technology stack."""

    path: str
    technologies: list[DetectedTechnology] = field(default_factory=list)
    env_var_names: list[str] = field(default_factory=list)
    recommendations: list[ServerRecommendation] = field(default_factory=list)
