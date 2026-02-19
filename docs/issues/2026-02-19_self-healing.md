# Self-Healing Retry Loop — Diagnose, Fix, Retry

- **Date**: 2026-02-19
- **Status**: `open`
- **Branch**: `feature/YYYY-MM-DD-self-healing`
- **Priority**: `critical`
- **Issue**: #10

## Problem

When `configure_server` installs a server and validation fails, or when `check_health` finds unhealthy servers, mcp-tap returns the raw error and stops. The user is left alone to debug — the exact pain point mcp-tap was built to eliminate.

Today's behavior:
```
configure_server → install ✓ → write config ✓ → validate ✗
→ "ConnectionRefused: port 5432" → user googles for 20 minutes
```

Target behavior:
```
configure_server → install ✓ → write config ✓ → validate ✗
→ diagnose: "port 5432 refused — docker-compose uses 54320"
→ fix config: port 5432 → 54320
→ retry validate ✓ → "Connected. 8 tools available."
```

This is the #1 differentiator from the original issue (adenhq/hive#4527). Without it, mcp-tap is a "CLI tool that installs" rather than an "agent that makes things work."

## Context

- **Module affected**: `connection/tester.py` (already returns structured errors), `tools/configure.py` (calls `_validate`), `tools/health.py` (batch check)
- **Existing infrastructure**: `ConnectionTestResult` already captures error type and message. `tester.py` already distinguishes `TimeoutError`, `FileNotFoundError`, and generic exceptions.
- **The original issue** describes a `diagnose_fix` node with `max_node_visits: 3` — a feedback loop that reads errors, reasons about causes, applies fixes, and retries.

## Architecture

### New module: `src/mcp_tap/healing/`

```
src/mcp_tap/healing/
├── __init__.py
├── classifier.py    # Error → ErrorCategory classification
├── fixer.py         # ErrorCategory → CandidateFix generation
└── retry.py         # Fix → rewrite config → re-validate → loop
```

### Error Classification (`classifier.py`)

Parse error messages from `ConnectionTestResult.error` into structured categories:

```python
class ErrorCategory(StrEnum):
    COMMAND_NOT_FOUND = "command_not_found"      # FileNotFoundError, ENOENT
    CONNECTION_REFUSED = "connection_refused"      # wrong port, server not running
    TIMEOUT = "timeout"                           # server too slow to start
    AUTH_FAILED = "auth_failed"                   # missing/invalid credentials
    MISSING_ENV_VAR = "missing_env_var"           # required env var not set
    TRANSPORT_MISMATCH = "transport_mismatch"     # stdio vs http confusion
    PERMISSION_DENIED = "permission_denied"       # file/network permissions
    UNKNOWN = "unknown"                           # unclassifiable

@dataclass(frozen=True, slots=True)
class DiagnosisResult:
    category: ErrorCategory
    original_error: str
    explanation: str        # Human-readable explanation for LLM consumption
    suggested_fix: str      # What the fixer should try
    confidence: float       # 0.0-1.0 how sure we are about the diagnosis
```

Classification rules (pattern matching on error strings):
- `"Command not found"` / `"FileNotFoundError"` / `"ENOENT"` → `COMMAND_NOT_FOUND`
- `"Connection refused"` / `"ECONNREFUSED"` → `CONNECTION_REFUSED`
- `"did not respond within"` / `"TimeoutError"` → `TIMEOUT`
- `"401"` / `"403"` / `"authentication"` / `"unauthorized"` → `AUTH_FAILED`
- `"not set"` / `"missing"` / `"required"` + env var pattern → `MISSING_ENV_VAR`
- `"Permission denied"` / `"EACCES"` → `PERMISSION_DENIED`

### Fix Generation (`fixer.py`)

For each `ErrorCategory`, generate a `CandidateFix`:

```python
@dataclass(frozen=True, slots=True)
class CandidateFix:
    description: str                    # What we're trying
    new_config: ServerConfig | None     # Modified config, or None if not a config fix
    install_command: str | None         # Re-install command, or None
    env_var_hint: str | None            # Env var guidance for the user
    requires_user_action: bool          # True if we can't fix this automatically
```

Fix strategies per category:

| Category | Auto-fix | Strategy |
|----------|----------|----------|
| `COMMAND_NOT_FOUND` | Yes | Try alternative runner: `npx` → global path lookup → `uvx` → `pip` installed path |
| `CONNECTION_REFUSED` | Partial | Check if Docker is running, suggest port from docker-compose.yml if available |
| `TIMEOUT` | Yes | Increase timeout to 30s, then 60s. If still fails, check if deps are missing |
| `AUTH_FAILED` | No | Report which env var is likely wrong/missing, provide help URL |
| `MISSING_ENV_VAR` | No | Identify which vars are needed (from registry data), check if user's .env has them under different names |
| `TRANSPORT_MISMATCH` | Yes | Flip stdio↔http in the config, retry |
| `PERMISSION_DENIED` | Partial | Suggest `--prefix ~/.local` for npm, check file permissions |
| `UNKNOWN` | No | Return the raw error with context for the LLM to reason about |

### Retry Loop (`retry.py`)

```python
async def heal_and_retry(
    server_name: str,
    server_config: ServerConfig,
    error: ConnectionTestResult,
    *,
    max_attempts: int = 3,
    project_path: str | None = None,
) -> HealingResult:
    """Diagnose an error, apply a fix, and retry validation.

    Loops up to max_attempts times. Each iteration:
    1. Classify the error
    2. Generate a candidate fix
    3. If auto-fixable: apply fix, re-validate
    4. If not auto-fixable: return diagnosis with user guidance

    Returns HealingResult with: fixed (bool), attempts made,
    final config (if modified), and user_action_needed (str) if
    the fix requires human intervention.
    """
```

```python
@dataclass(frozen=True, slots=True)
class HealingResult:
    fixed: bool
    attempts: list[HealingAttempt]
    final_config: ServerConfig | None    # The working config, if fixed
    user_action_needed: str              # Guidance if human must intervene

@dataclass(frozen=True, slots=True)
class HealingAttempt:
    attempt_number: int
    diagnosis: DiagnosisResult
    fix_applied: CandidateFix
    result: ConnectionTestResult         # Re-validation result
```

### Integration Points

1. **`configure_server`** — After `_validate` fails, call `heal_and_retry`. If healed, update the written config with the fixed version. Return `HealingResult` alongside `ConfigureResult`.

2. **`check_health`** — When servers are unhealthy, optionally trigger healing for each. Add `auto_heal: bool = False` parameter to `check_health`.

3. **`test_connection`** — Add `auto_heal: bool = False` parameter. When True, attempt healing before returning failure.

### New models in `models.py`

```python
class ErrorCategory(StrEnum): ...
class DiagnosisResult: ...
class CandidateFix: ...
class HealingAttempt: ...
class HealingResult: ...
```

## Scope

1. `src/mcp_tap/healing/__init__.py`
2. `src/mcp_tap/healing/classifier.py` — Error pattern matching → ErrorCategory
3. `src/mcp_tap/healing/fixer.py` — ErrorCategory → CandidateFix
4. `src/mcp_tap/healing/retry.py` — Orchestrate diagnose → fix → re-validate loop
5. `src/mcp_tap/models.py` — Add ErrorCategory, DiagnosisResult, CandidateFix, HealingAttempt, HealingResult
6. `src/mcp_tap/tools/configure.py` — Integrate healing after validation failure
7. `src/mcp_tap/tools/health.py` — Add `auto_heal` parameter
8. `src/mcp_tap/tools/test.py` — Add `auto_heal` parameter
9. `tests/test_healing.py` — Unit tests for classifier, fixer, retry loop

## Test Plan

- [ ] Classifier correctly maps ≥6 error patterns to categories
- [ ] Fixer generates valid CandidateFix for each auto-fixable category
- [ ] Retry loop stops after max_attempts
- [ ] Retry loop stops early when fix succeeds
- [ ] `requires_user_action=True` fixes are NOT auto-applied
- [ ] configure_server returns HealingResult when validation fails then heals
- [ ] check_health with auto_heal=True triggers healing for unhealthy servers
- [ ] All tests mock subprocess/connection (no real servers needed)
- [ ] 100% of existing tests still pass

## Root Cause

No error diagnosis logic exists — `ConnectionTestResult.error` is a raw string that gets passed through without interpretation.

## Solution

(Fill after implementation)

## Files Changed

(Fill after implementation)

## Lessons Learned

(Fill after implementation)
