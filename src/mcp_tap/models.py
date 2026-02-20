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
    install_status: str = ""  # installed / already_available / skipped / failed
    tools_discovered: list[str] = field(default_factory=list)
    validation_passed: bool = False


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


# ─── Health Check Models ─────────────────────────────────────


@dataclass(frozen=True, slots=True)
class ServerHealth:
    """Health status of a single configured MCP server."""

    name: str
    status: str  # "healthy", "unhealthy", "timeout"
    tools_count: int = 0
    tools: list[str] = field(default_factory=list)
    error: str = ""


@dataclass(frozen=True, slots=True)
class HealthReport:
    """Aggregated health report for all configured MCP servers."""

    client: str
    config_file: str
    total: int
    healthy: int
    unhealthy: int
    servers: list[ServerHealth] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class ToolConflict:
    """A tool name that appears in multiple configured servers."""

    tool_name: str
    servers: list[str] = field(default_factory=list)


# ─── Scanner Models ──────────────────────────────────────────


class TechnologyCategory(StrEnum):
    LANGUAGE = "language"
    FRAMEWORK = "framework"
    DATABASE = "database"
    SERVICE = "service"
    PLATFORM = "platform"


class RecommendationSource(StrEnum):
    CURATED = "curated"
    REGISTRY = "registry"


class HintType(StrEnum):
    UNMAPPED_TECHNOLOGY = "unmapped_technology"
    WORKFLOW_INFERENCE = "workflow_inference"
    STACK_ARCHETYPE = "stack_archetype"
    ENV_VAR_HINT = "env_var_hint"
    MISSING_COMPLEMENT = "missing_complement"
    DEPLOYMENT_TARGET = "deployment_target"


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
    source: RecommendationSource = RecommendationSource.CURATED
    confidence: float = 1.0


@dataclass(frozen=True, slots=True)
class DiscoveryHint:
    """A suggestion for additional MCP server searches based on project signals."""

    hint_type: HintType
    trigger: str
    suggestion: str
    search_queries: list[str] = field(default_factory=list)
    confidence: float = 0.7


@dataclass(frozen=True, slots=True)
class StackArchetype:
    """A recognized project pattern (e.g. SaaS, Data Pipeline) with extra suggestions."""

    name: str
    label: str
    matched_technologies: list[str] = field(default_factory=list)
    extra_search_queries: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class ProjectProfile:
    """Aggregated scan result describing a project's technology stack."""

    path: str
    technologies: list[DetectedTechnology] = field(default_factory=list)
    env_var_names: list[str] = field(default_factory=list)
    recommendations: list[ServerRecommendation] = field(default_factory=list)
    discovery_hints: list[DiscoveryHint] = field(default_factory=list)
    archetypes: list[StackArchetype] = field(default_factory=list)


# ─── Healing Models ──────────────────────────────────────────


class ErrorCategory(StrEnum):
    COMMAND_NOT_FOUND = "command_not_found"
    CONNECTION_REFUSED = "connection_refused"
    TIMEOUT = "timeout"
    AUTH_FAILED = "auth_failed"
    MISSING_ENV_VAR = "missing_env_var"
    TRANSPORT_MISMATCH = "transport_mismatch"
    PERMISSION_DENIED = "permission_denied"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class DiagnosisResult:
    """Structured diagnosis of a server connection error."""

    category: ErrorCategory
    original_error: str
    explanation: str
    suggested_fix: str
    confidence: float = 1.0


@dataclass(frozen=True, slots=True)
class CandidateFix:
    """A proposed fix for a diagnosed server error."""

    description: str
    new_config: ServerConfig | None = None
    install_command: str | None = None
    env_var_hint: str | None = None
    requires_user_action: bool = False


@dataclass(frozen=True, slots=True)
class HealingAttempt:
    """A single diagnose-fix-retry iteration."""

    diagnosis: DiagnosisResult
    fix_applied: CandidateFix
    success: bool


@dataclass(frozen=True, slots=True)
class HealingResult:
    """Outcome of the full healing retry loop."""

    fixed: bool
    attempts: list[HealingAttempt] = field(default_factory=list)
    fixed_config: ServerConfig | None = None
    user_action_needed: str = ""


# ─── Credential Mapping Models ─────────────────────────────


@dataclass(frozen=True, slots=True)
class CredentialMapping:
    """Maps a server's required env var to an available project credential."""

    server_name: str
    required_env_var: str
    available_env_var: str | None = None
    source: str = "not found"
    status: str = "missing"  # "exact_match", "compatible_match", "missing"
    help_url: str = ""


# ─── Inspector Models ───────────────────────────────────────


@dataclass(frozen=True, slots=True)
class EnvVarHint:
    """An environment variable mentioned in server documentation."""

    name: str
    context: str
    is_required: bool = True


@dataclass(frozen=True, slots=True)
class ConfigHints:
    """Structured hints extracted from a server's documentation."""

    install_commands: list[str] = field(default_factory=list)
    transport_hints: list[str] = field(default_factory=list)
    env_vars_mentioned: list[EnvVarHint] = field(default_factory=list)
    command_patterns: list[str] = field(default_factory=list)
    json_config_blocks: list[str] = field(default_factory=list)
    confidence: float = 0.0


# ─── Evaluation Models ──────────────────────────────────────


@dataclass(frozen=True, slots=True)
class MaturitySignals:
    """Raw signals collected about a server's maturity/health."""

    stars: int | None = None
    forks: int | None = None
    open_issues: int | None = None
    last_commit_date: str | None = None
    last_release_date: str | None = None
    is_official: bool = False
    is_archived: bool = False
    license: str | None = None


@dataclass(frozen=True, slots=True)
class MaturityScore:
    """Computed maturity assessment for a server."""

    score: float
    tier: str  # "recommended", "acceptable", "caution", "avoid"
    reasons: list[str] = field(default_factory=list)
    warning: str | None = None


# ─── Lockfile Models ──────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class LockedConfig:
    """Server config as stored in the lockfile (no env values)."""

    command: str
    args: list[str] = field(default_factory=list)
    env_keys: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class LockedServer:
    """A single server entry in the lockfile."""

    package_identifier: str
    registry_type: str
    version: str
    integrity: str | None = None
    repository_url: str = ""
    config: LockedConfig = field(default_factory=lambda: LockedConfig(command=""))
    tools: list[str] = field(default_factory=list)
    tools_hash: str | None = None
    installed_at: str = ""
    verified_at: str | None = None
    verified_healthy: bool = False


@dataclass(frozen=True, slots=True)
class Lockfile:
    """The complete mcp-tap.lock file."""

    lockfile_version: int = 1
    generated_by: str = ""
    generated_at: str = ""
    servers: dict[str, LockedServer] = field(default_factory=dict)


class DriftType(StrEnum):
    TOOLS_CHANGED = "tools_changed"
    CONFIG_CHANGED = "config_changed"
    VERSION_CHANGED = "version_changed"
    MISSING = "missing"
    EXTRA = "extra"


class DriftSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class DriftEntry:
    """A single drift finding between lockfile and actual state."""

    server: str
    drift_type: DriftType
    detail: str = ""
    severity: DriftSeverity = DriftSeverity.WARNING


@dataclass(frozen=True, slots=True)
class VerifyResult:
    """Result of lockfile verification."""

    lockfile_path: str
    total_locked: int
    total_installed: int
    drift: list[DriftEntry] = field(default_factory=list)
    clean: bool = True


# ─── Security Gate Models ────────────────────────────────────


class SecurityRisk(StrEnum):
    PASS = "pass"
    WARN = "warn"
    BLOCK = "block"


@dataclass(frozen=True, slots=True)
class SecuritySignal:
    """A single security finding about a package."""

    category: str  # e.g. "repo_age", "stars", "archived", "license", "command"
    risk: SecurityRisk
    message: str  # Human-readable explanation


@dataclass(frozen=True, slots=True)
class SecurityReport:
    """Aggregated security assessment for a package."""

    overall_risk: SecurityRisk
    signals: list[SecuritySignal] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return self.overall_risk != SecurityRisk.BLOCK

    @property
    def warnings(self) -> list[SecuritySignal]:
        return [s for s in self.signals if s.risk == SecurityRisk.WARN]

    @property
    def blockers(self) -> list[SecuritySignal]:
        return [s for s in self.signals if s.risk == SecurityRisk.BLOCK]


# ─── Stack Models ────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class StackServer:
    """A single server entry in a stack definition."""

    name: str
    package_identifier: str
    registry_type: str = "npm"
    version: str = "latest"
    env_vars: list[str] = field(default_factory=list)  # names only, user provides values


@dataclass(frozen=True, slots=True)
class Stack:
    """A shareable MCP server profile."""

    name: str
    description: str
    servers: list[StackServer] = field(default_factory=list)
    version: str = "1"
    author: str = ""
