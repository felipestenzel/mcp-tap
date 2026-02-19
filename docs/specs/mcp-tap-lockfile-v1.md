# mcp-tap Lockfile Specification v1

> **Status**: Draft
> **Author**: Innovation Lab
> **Date**: 2026-02-19
> **OWASP References**: MCP03 (Tool Poisoning), MCP04 (Supply Chain Attacks)

---

## 1. Motivation

MCP server configurations are currently ephemeral. They live in client-specific config
files (`settings.json`, `claude_desktop_config.json`, etc.) that differ by client, by
machine, and by user. There is no way to:

- Reproduce an exact MCP setup on another machine
- Detect when a server's tools change unexpectedly (tool poisoning, MCP03)
- Verify that installed packages match expected checksums (supply chain, MCP04)
- Onboard a new team member with a known-good MCP configuration
- Audit which MCP servers are in use across a project

The lockfile solves all five problems with a single, committable artifact.

### Prior Art

| System | File | Format | Key Idea |
|--------|------|--------|----------|
| npm | `package-lock.json` | JSON | Exact versions + integrity hashes (sha512) |
| Deno | `deno.lock` | JSON | Module URLs + hashes, schema versioning |
| pip | `requirements.txt` / `pip.lock` | Text / TOML | Pinned versions, hashes via `--require-hashes` |
| Terraform | `.terraform.lock.hcl` | HCL | Provider checksums per platform |

mcp-tap follows the npm/Deno pattern: JSON format, integrity hashes, schema versioning.

---

## 2. Format Choice: JSON

**Decision**: JSON.

**Reasoning**:
- The entire MCP ecosystem uses JSON (config files, MCP protocol messages, Registry API)
- `package-lock.json` and `deno.lock` are both JSON -- developers expect lockfiles in JSON
- mcp-tap already reads and writes JSON atomically via `config/writer.py`
- JSON is unambiguous for machines, adequate for humans, universally parseable
- No new dependency needed (no `toml` or `pyyaml` import)

TOML would be more human-readable, but lockfiles are primarily machine-read. The few
times a human inspects a lockfile, JSON with proper indentation is sufficient.

---

## 3. File Name and Location

**File**: `mcp-tap.lock`
**Location**: Project root directory (next to `package.json`, `pyproject.toml`, etc.)
**Git**: COMMITTED to version control (like `package-lock.json`)

The `.lock` extension signals to developers and tools that this is a lockfile.
Placing it in the project root enables auto-detection by `scan_project`.

---

## 4. Schema

### 4.1. Top-Level Structure

```json
{
  "lockfile_version": 1,
  "generated_by": "mcp-tap@0.3.0",
  "generated_at": "2026-02-19T14:30:00Z",
  "servers": {
    "<server_name>": { ... }
  }
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `lockfile_version` | `integer` | Yes | Schema version. Always `1` for this spec. |
| `generated_by` | `string` | Yes | `mcp-tap@<version>` that last wrote this file. |
| `generated_at` | `string` (ISO 8601) | Yes | UTC timestamp of last write. |
| `servers` | `object` | Yes | Map of server name to `LockedServer`. |

### 4.2. LockedServer Entry

```json
{
  "postgres": {
    "package_identifier": "@modelcontextprotocol/server-postgres",
    "registry_type": "npm",
    "version": "0.6.2",
    "integrity": "sha256-a1b2c3d4e5f6...",
    "repository_url": "https://github.com/modelcontextprotocol/servers",
    "config": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-postgres"],
      "env_keys": ["POSTGRES_URL"]
    },
    "tools": ["query", "list_tables", "describe_table"],
    "tools_hash": "sha256-7f8e9d0c1b2a...",
    "installed_at": "2026-02-19T14:30:00Z",
    "verified_at": "2026-02-19T14:30:05Z",
    "verified_healthy": true
  }
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `package_identifier` | `string` | Yes | The package name (e.g. `@modelcontextprotocol/server-postgres`, `mcp-server-git`). |
| `registry_type` | `string` | Yes | One of `"npm"`, `"pypi"`, `"oci"`. |
| `version` | `string` | Yes | Exact installed version (not a range). Example: `"0.6.2"`, `"1.0.0"`. |
| `integrity` | `string \| null` | Yes | Package integrity hash. Format: `"<algorithm>-<hex_digest>"`. Null if hash could not be computed. |
| `repository_url` | `string` | No | Source repository URL. Empty string if unknown. |
| `config` | `LockedConfig` | Yes | The server's runtime configuration (see below). |
| `tools` | `string[]` | Yes | Sorted list of tool names from `list_tools()`. Empty if never verified. |
| `tools_hash` | `string \| null` | Yes | Hash of the sorted, joined tool names. Used for fast drift detection. Null if tools list is empty. |
| `installed_at` | `string` (ISO 8601) | Yes | UTC timestamp when first added to lockfile. |
| `verified_at` | `string \| null` (ISO 8601) | Yes | UTC timestamp of last successful `check_health` / `test_connection`. Null if never verified. |
| `verified_healthy` | `boolean` | Yes | Whether the server passed its last health check. |

### 4.3. LockedConfig

```json
{
  "command": "npx",
  "args": ["-y", "@modelcontextprotocol/server-postgres"],
  "env_keys": ["POSTGRES_URL"]
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `command` | `string` | Yes | The executable command. |
| `args` | `string[]` | Yes | Command arguments. |
| `env_keys` | `string[]` | Yes | **Sorted list of env var NAMES only.** Values are NEVER stored. |

**Security invariant**: `env_keys` stores only the key names. This allows
the lockfile to be committed to version control safely. The actual values
live in the client config files (which are user-local, not committed) or
in environment variables.

### 4.4. Integrity Hash

The `integrity` field uses the format `<algorithm>-<hex_digest>`, matching the
[Subresource Integrity](https://www.w3.org/TR/SRI/) convention used by npm.

**How to compute**:

| Registry | Method |
|----------|--------|
| npm | Run `npm view <pkg>@<version> dist.integrity` to get the registry-provided sha512. If unavailable, use `sha256` of the downloaded tarball. |
| pypi | Fetch the package's JSON metadata from `https://pypi.org/pypi/<pkg>/<version>/json` and extract `digests.sha256` from the matching distribution. |
| oci | Use the image manifest digest (already sha256 by convention). |

**Null integrity**: If the hash cannot be obtained (e.g., network error during
install, private registry without hash support), the field is set to `null`.
The `verify` command will flag null-integrity entries as warnings.

### 4.5. Tools Hash

The `tools_hash` provides fast drift detection without comparing the full tools list.

**Computation**:
```
tools_hash = "sha256-" + sha256("|".join(sorted(tools))).hexdigest()
```

Using `|` (pipe) as separator because tool names cannot contain pipes in the MCP spec.
Sorting ensures deterministic output regardless of `list_tools()` ordering.

---

## 5. Complete Example

```json
{
  "lockfile_version": 1,
  "generated_by": "mcp-tap@0.3.0",
  "generated_at": "2026-02-19T14:30:00Z",
  "servers": {
    "postgres": {
      "package_identifier": "@modelcontextprotocol/server-postgres",
      "registry_type": "npm",
      "version": "0.6.2",
      "integrity": "sha256-a3f2b8c91d4e7f5a0b6c3d2e1f9a8b7c6d5e4f3a2b1c0d9e8f7a6b5c4d3e2f1",
      "repository_url": "https://github.com/modelcontextprotocol/servers",
      "config": {
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-postgres"],
        "env_keys": ["POSTGRES_URL"]
      },
      "tools": ["describe_table", "list_tables", "query"],
      "tools_hash": "sha256-e7c4a1b3d5f2098c6b4a2d1e3f5c7b9a8d6e4f2c0a1b3d5e7f9c8b6a4d2e0f1",
      "installed_at": "2026-02-19T14:30:00Z",
      "verified_at": "2026-02-19T14:30:05Z",
      "verified_healthy": true
    },
    "github": {
      "package_identifier": "@modelcontextprotocol/server-github",
      "registry_type": "npm",
      "version": "2025.1.15",
      "integrity": "sha256-b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1b2c3d4e5f6a7b8c9d0e1f2a3b4",
      "repository_url": "https://github.com/modelcontextprotocol/servers",
      "config": {
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-github"],
        "env_keys": ["GITHUB_PERSONAL_ACCESS_TOKEN"]
      },
      "tools": [
        "create_issue",
        "create_pull_request",
        "get_file_contents",
        "list_commits",
        "search_code",
        "search_repositories"
      ],
      "tools_hash": "sha256-1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5a6b7c8d9e0f1a",
      "installed_at": "2026-02-18T10:00:00Z",
      "verified_at": "2026-02-19T14:30:05Z",
      "verified_healthy": true
    },
    "sentry": {
      "package_identifier": "mcp-server-sentry",
      "registry_type": "pypi",
      "version": "0.3.1",
      "integrity": "sha256-c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5",
      "repository_url": "https://github.com/getsentry/sentry-mcp",
      "config": {
        "command": "uvx",
        "args": ["mcp-server-sentry"],
        "env_keys": ["SENTRY_AUTH_TOKEN", "SENTRY_ORG"]
      },
      "tools": ["get_issue", "list_projects", "search_issues"],
      "tools_hash": "sha256-d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6",
      "installed_at": "2026-02-19T12:00:00Z",
      "verified_at": null,
      "verified_healthy": false
    }
  }
}
```

---

## 6. JSON Schema

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://github.com/felipestenzel/mcp-tap/schemas/lockfile-v1.json",
  "title": "mcp-tap Lockfile",
  "description": "Lockfile for reproducible MCP server configurations.",
  "type": "object",
  "required": ["lockfile_version", "generated_by", "generated_at", "servers"],
  "additionalProperties": false,
  "properties": {
    "lockfile_version": {
      "type": "integer",
      "const": 1,
      "description": "Schema version."
    },
    "generated_by": {
      "type": "string",
      "pattern": "^mcp-tap@.+$",
      "description": "The mcp-tap version that generated this lockfile."
    },
    "generated_at": {
      "type": "string",
      "format": "date-time",
      "description": "UTC timestamp of last write."
    },
    "servers": {
      "type": "object",
      "additionalProperties": { "$ref": "#/$defs/LockedServer" },
      "description": "Map of server name to locked configuration."
    }
  },
  "$defs": {
    "LockedServer": {
      "type": "object",
      "required": [
        "package_identifier",
        "registry_type",
        "version",
        "integrity",
        "config",
        "tools",
        "tools_hash",
        "installed_at",
        "verified_at",
        "verified_healthy"
      ],
      "additionalProperties": false,
      "properties": {
        "package_identifier": {
          "type": "string",
          "minLength": 1,
          "description": "Package name from the registry."
        },
        "registry_type": {
          "type": "string",
          "enum": ["npm", "pypi", "oci"],
          "description": "Package registry type."
        },
        "version": {
          "type": "string",
          "minLength": 1,
          "description": "Exact installed version."
        },
        "integrity": {
          "type": ["string", "null"],
          "pattern": "^sha(256|384|512)-[a-f0-9]+$",
          "description": "Package integrity hash, or null if unavailable."
        },
        "repository_url": {
          "type": "string",
          "description": "Source repository URL."
        },
        "config": { "$ref": "#/$defs/LockedConfig" },
        "tools": {
          "type": "array",
          "items": { "type": "string" },
          "description": "Sorted tool names from list_tools()."
        },
        "tools_hash": {
          "type": ["string", "null"],
          "description": "SHA-256 hash of sorted, pipe-joined tool names."
        },
        "installed_at": {
          "type": "string",
          "format": "date-time",
          "description": "UTC timestamp of first lockfile entry."
        },
        "verified_at": {
          "type": ["string", "null"],
          "format": "date-time",
          "description": "UTC timestamp of last successful health check."
        },
        "verified_healthy": {
          "type": "boolean",
          "description": "Whether the server passed its last health check."
        }
      }
    },
    "LockedConfig": {
      "type": "object",
      "required": ["command", "args", "env_keys"],
      "additionalProperties": false,
      "properties": {
        "command": {
          "type": "string",
          "minLength": 1,
          "description": "Executable command."
        },
        "args": {
          "type": "array",
          "items": { "type": "string" },
          "description": "Command arguments."
        },
        "env_keys": {
          "type": "array",
          "items": { "type": "string" },
          "description": "Sorted list of environment variable names (NO values)."
        }
      }
    }
  }
}
```

---

## 7. Lifecycle Rules

### 7.1. Creation

The lockfile is created on the **first `configure_server` call** when a
`project_path` is available (either explicitly passed or inferred from CWD).

If no `project_path` can be determined (global/user-scope install with no project
context), the lockfile is NOT created. The lockfile is inherently project-scoped.

**Trigger**: `configure_server(..., scope="project", project_path="/path/to/project")`
or `configure_server(...)` when CWD is inside a project directory.

**Algorithm**:
1. Check if `<project_path>/mcp-tap.lock` exists
2. If not, create it with `lockfile_version: 1`, empty `servers: {}`
3. Add the new server entry
4. Write atomically (same pattern as `config/writer.py`)

### 7.2. Updates

The lockfile is updated on these events:

| Event | What Changes |
|-------|-------------|
| `configure_server` succeeds | New server entry added (or existing entry updated if version changed) |
| `remove_server` succeeds | Server entry removed from lockfile |
| `check_health` completes | `verified_at`, `verified_healthy`, `tools`, `tools_hash` updated for each checked server |
| `test_connection` succeeds | Same as health check, but for a single server |

**Key principle**: The lockfile is updated as a side effect of existing tool operations.
There is no separate "lock" command in v1. The lockfile stays in sync automatically.

### 7.3. Reading (Drift Detection)

The lockfile is read on these events:

| Event | What Happens |
|-------|-------------|
| `configure_server` (with lockfile present) | Compare new config against locked entry. Warn if version differs from locked version. |
| `check_health` (with lockfile present) | After health check, compare discovered tools against `tools_hash`. Report drift if tools changed. |
| `scan_project` (with lockfile present) | Report lockfile presence. Show locked server count in output. Flag servers in lockfile not present in client config (missing). |

### 7.4. Drift Report

When `check_health` detects that a server's tools have changed since they were
locked, the result includes a drift warning:

```json
{
  "drift": [
    {
      "server": "postgres",
      "type": "tools_changed",
      "locked_tools": ["describe_table", "list_tables", "query"],
      "current_tools": ["describe_table", "execute_sql", "list_tables", "query"],
      "added": ["execute_sql"],
      "removed": []
    }
  ]
}
```

Tool drift can indicate:
- A legitimate version upgrade (new tools added)
- Tool poisoning (MCP03): a server silently replaced its tool set
- A different package was installed under the same name

### 7.5. Restore

A new tool, `restore`, uses the lockfile to recreate the MCP configuration:

```
restore(project_path="/path/to/project", client="claude_code")
```

**Algorithm**:
1. Read `<project_path>/mcp-tap.lock`
2. For each server in `servers`:
   a. Resolve the installer for `registry_type`
   b. Install `package_identifier@version`
   c. Build `ServerConfig` from `config`
   d. Write to the target client's config file
   e. Optionally verify via `test_connection`
3. Report results

The `restore` tool does NOT set env var values (they are not in the lockfile).
It reports which env vars need to be set by the user.

### 7.6. Verify

A new tool, `verify`, compares the lockfile against the actual state:

```
verify(project_path="/path/to/project", client="claude_code")
```

**Checks performed**:

| Check | Severity | Description |
|-------|----------|-------------|
| Server in lockfile but not in client config | WARNING | Server was removed outside of mcp-tap |
| Server in client config but not in lockfile | INFO | Server was added outside of mcp-tap |
| Version mismatch | WARNING | Installed version differs from locked version |
| Null integrity | WARNING | Package hash was not recorded |
| Tools hash mismatch | ERROR | Tools changed since lock -- possible poisoning |
| Config mismatch (command/args) | WARNING | Runtime config differs from locked config |

---

## 8. Security Considerations

### 8.1. No Secrets in Lockfile

The lockfile stores `env_keys` (names only), NEVER `env` values. This is enforced
at the model level: `LockedConfig.env_keys` is `list[str]`, not `dict[str, str]`.

### 8.2. Integrity Verification (OWASP MCP04)

The `integrity` hash detects supply chain attacks where a package is replaced
with a malicious version. On `restore`, mcp-tap can optionally verify that the
installed package matches the locked hash.

v1 scope: Record the hash. Verification against the hash is a v2 enhancement.

### 8.3. Tool Poisoning Detection (OWASP MCP03)

The `tools_hash` detects when a server's exposed tools change unexpectedly.
A legitimate update adds tools; a poisoning attack might rename or replace them.

The `verify` tool flags tools_hash mismatches as ERROR severity.

### 8.4. Lockfile Tampering

The lockfile itself can be tampered with in version control. This is mitigated by:
- Code review (lockfile diffs are human-readable in JSON)
- Future: signing the lockfile with a project key (v2+)

---

## 9. Implementation Plan

### 9.1. New Domain Models (`src/mcp_tap/models.py`)

Add the following frozen dataclasses:

```python
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
    config: LockedConfig = field(default_factory=LockedConfig)
    tools: list[str] = field(default_factory=list)
    tools_hash: str | None = None
    installed_at: str = ""
    verified_at: str | None = None
    verified_healthy: bool = False

@dataclass(frozen=True, slots=True)
class Lockfile:
    """The complete lockfile."""
    lockfile_version: int = 1
    generated_by: str = ""
    generated_at: str = ""
    servers: dict[str, LockedServer] = field(default_factory=dict)

@dataclass(frozen=True, slots=True)
class DriftEntry:
    """A single drift finding."""
    server: str
    drift_type: str  # "tools_changed", "config_changed", "version_changed", "missing", "extra"
    detail: str = ""
    severity: str = "warning"  # "info", "warning", "error"

@dataclass(frozen=True, slots=True)
class VerifyResult:
    """Result of lockfile verification."""
    lockfile_path: str
    total_locked: int
    total_installed: int
    drift: list[DriftEntry] = field(default_factory=list)
    clean: bool = True
```

### 9.2. New Error Types (`src/mcp_tap/errors.py`)

```python
class LockfileReadError(McpTapError):
    """Error reading or parsing the lockfile."""

class LockfileWriteError(McpTapError):
    """Error writing the lockfile."""

class LockfileDriftError(McpTapError):
    """Lockfile verification found drift."""
```

### 9.3. New Package: `src/mcp_tap/lockfile/`

```
src/mcp_tap/lockfile/
    __init__.py
    reader.py      # Read and parse mcp-tap.lock
    writer.py      # Atomic write to mcp-tap.lock
    hasher.py      # Compute integrity hashes and tools_hash
    differ.py      # Compare lockfile vs actual state (drift detection)
```

**`reader.py`**:
- `read_lockfile(project_path: Path) -> Lockfile | None` -- Returns None if no lockfile
- `parse_lockfile(data: dict) -> Lockfile` -- Parse raw JSON into domain model
- Validates `lockfile_version` and raises `LockfileReadError` on unknown versions

**`writer.py`**:
- `write_lockfile(project_path: Path, lockfile: Lockfile) -> None` -- Atomic write
- `add_server(project_path: Path, name: str, entry: LockedServer) -> None`
- `remove_server(project_path: Path, name: str) -> None`
- `update_verification(project_path: Path, name: str, tools: list[str], healthy: bool) -> None`
- Uses the same atomic write pattern as `config/writer.py` (tempfile + os.replace)
- Uses the same file locking pattern (fcntl.flock)

**`hasher.py`**:
- `compute_tools_hash(tools: list[str]) -> str | None` -- SHA-256 of sorted pipe-joined names
- `fetch_npm_integrity(identifier: str, version: str) -> str | None` -- async, calls npm registry
- `fetch_pypi_integrity(identifier: str, version: str) -> str | None` -- async, calls PyPI JSON API
- `fetch_oci_integrity(identifier: str, version: str) -> str | None` -- async, from manifest

**`differ.py`**:
- `diff_lockfile(lockfile: Lockfile, installed: list[InstalledServer], healths: list[ServerHealth]) -> list[DriftEntry]`
- Compares locked state against actual installed servers and their health check results

### 9.4. Modified Existing Tools

**`tools/configure.py`** -- After successful configure:
1. Check if `project_path` is available
2. If yes, call `lockfile.writer.add_server()` with the new entry
3. Integrity hash is computed asynchronously (best-effort, null if fails)

**`tools/remove.py`** -- After successful remove:
1. If lockfile exists in project_path, call `lockfile.writer.remove_server()`

**`tools/health.py`** -- After health check completes:
1. If lockfile exists, call `lockfile.writer.update_verification()` for each server
2. If lockfile exists, call `lockfile.differ.diff_lockfile()` and include drift in result

**`tools/scan.py`** -- During project scan:
1. Check for `mcp-tap.lock` in project root
2. Report its presence and locked server count

### 9.5. New Tools

**`tools/restore.py`** -- `restore(project_path, client, dry_run=False)`
- Reads lockfile, installs each server, writes config
- Reports which env vars need manual setup
- `dry_run=True` shows what would be installed without doing it
- Registered in `server.py` with `destructiveHint=True`

**`tools/verify.py`** -- `verify(project_path, client)`
- Reads lockfile, reads client config, optionally runs health checks
- Returns `VerifyResult` with drift entries
- Registered in `server.py` with `readOnlyHint=True`

### 9.6. Registration in `server.py`

```python
from mcp_tap.tools.restore import restore
from mcp_tap.tools.verify import verify

# Read-only
mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))(verify)

# Destructive
mcp.tool(annotations=ToolAnnotations(destructiveHint=True))(restore)
```

### 9.7. Installer Protocol Extension

The `PackageInstaller` protocol in `installer/base.py` needs a new optional method:

```python
class PackageInstaller(Protocol):
    # ... existing methods ...

    async def resolve_version(self, identifier: str, version: str = "latest") -> str:
        """Resolve a version specifier to an exact version string.

        Returns the exact version (e.g. "0.6.2") for the given specifier.
        Returns the input version unchanged if resolution is not possible.
        """
        ...
```

This allows the lockfile to record exact versions even when the user says "latest".

Each installer adapter implements this:
- **npm**: `npm view <pkg>@<version> version`
- **pip**: `pip index versions <pkg>` or PyPI JSON API
- **oci**: `docker inspect` or registry API

---

## 10. Migration and Compatibility

### 10.1. Schema Versioning

The `lockfile_version` field enables forward compatibility. When mcp-tap reads a
lockfile with `lockfile_version > 1`, it:
1. Warns the user that a newer lockfile format was detected
2. Attempts to read only the fields it understands (graceful degradation)
3. NEVER overwrites a lockfile with a higher version (would lose data)

### 10.2. v1 Limitations (Acknowledged)

These are explicitly out of scope for v1 and documented for v2 planning:

| Limitation | v2 Plan |
|-----------|---------|
| No hash verification at install time | Compare fetched package hash against locked integrity |
| No lockfile signing | GPG or SSH signing of the lockfile |
| No multi-client awareness | Track which clients have which servers |
| No automatic version resolution | Resolve "latest" to exact version at lock time |
| No transitive dependency tracking | Lock MCP server dependencies, not just the server itself |

### 10.3. Handling "Manual" Servers

Servers added directly to config files (not via mcp-tap) will NOT appear in the
lockfile. The `verify` tool reports these as `drift_type: "extra"` with
`severity: "info"`. This is informational, not an error -- mcp-tap respects that
users may configure servers through other means.

---

## 11. Deterministic Output

The lockfile MUST produce deterministic output for the same logical state:

1. **Server entries** are sorted alphabetically by name
2. **`tools`** lists are sorted alphabetically
3. **`env_keys`** lists are sorted alphabetically
4. **JSON serialization** uses `indent=2`, `sort_keys=True`, `ensure_ascii=False`
5. **Trailing newline** is always present

This ensures that lockfile diffs in version control are minimal and meaningful.

---

## 12. Implementation Phases

### Phase 1: Core (v0.3.0-alpha)
- [ ] Domain models in `models.py`
- [ ] Error types in `errors.py`
- [ ] `lockfile/reader.py` and `lockfile/writer.py` (atomic read/write)
- [ ] `lockfile/hasher.py` (tools_hash only, integrity deferred)
- [ ] Hook into `configure_server` to create/update lockfile
- [ ] Hook into `remove_server` to remove from lockfile
- [ ] Tests for all new modules

### Phase 2: Verification (v0.3.0-beta)
- [ ] `lockfile/differ.py` (drift detection)
- [ ] `tools/verify.py` (new tool)
- [ ] Hook into `check_health` to update verification timestamps and detect drift
- [ ] Hook into `scan_project` to report lockfile presence
- [ ] Tests for drift detection

### Phase 3: Restore (v0.3.0)
- [ ] `tools/restore.py` (new tool)
- [ ] `PackageInstaller.resolve_version()` on all adapters
- [ ] Integrity hash computation in `lockfile/hasher.py`
- [ ] Tests for restore flow

---

## 13. Open Questions

1. **Should `restore` also run `check_health` automatically?**
   Recommendation: Yes, with an opt-out flag. A restore without verification is
   half a job.

2. **Should the lockfile track which MCP clients the server was configured for?**
   Recommendation: No for v1. The lockfile is about *what* servers exist, not
   *where* they are configured. Client awareness is a v2 concern.

3. **How to handle servers installed from Git URLs (not registries)?**
   Recommendation: Use the Git commit SHA as `version` and the clone URL as
   `package_identifier`. The `integrity` field would be null.

4. **Should `configure_server` fail if the lockfile has a different version locked?**
   Recommendation: No, but warn. The lockfile is advisory in v1, not enforcing.
   Strict enforcement is a v2 mode (`--frozen` flag, similar to `npm ci`).
