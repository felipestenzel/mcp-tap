# Scan/HTTP polish: installed matching, remote registry_type, and security message

- **Date**: 2026-02-23
- **Status**: `done`
- **Branch**: `fix/2026-02-23-scan-http-polish`
- **Priority**: `high`

## Problem

Three quality issues are still visible after v0.6.0:

1. `scan_project` can mark a recommendation as not installed when the configured server uses a
   different alias than the recommended `server_name`.
2. Official registry remote servers (`remotes`) are exposed with `registry_type: "npm"` even when
   transport is HTTP/SSE (`streamable-http`, `http`, `sse`), which is semantically misleading.
3. `configure_server` returns a blocked-security message that instructs users to use
   `bypass_security=True`, but this parameter is not part of the tool signature.

## Context

- Affected layers:
  - `tools/scan.py` (recommendation/install cross-reference)
  - `tools/search.py` (remote result serialization)
  - `tools/configure.py` (user-facing security message)
- Discovered via real validation on `stz_profile` + code review of v0.6.0 handoff outputs.
- Current behavior is functionally workable, but creates avoidable confusion in UX and metadata.

## Root Cause

- Installed matching in `scan_project` currently compares only recommendation `server_name` against
  configured names.
- Tool output serialization (`scan_project`/`search_servers`) used `pkg.registry_type` verbatim,
  which maps remote URLs to `npm` in current model representation.
- Security block message references an override flag that does not exist in the public API.

## Solution

- `scan_project` now performs installed matching in two layers:
  - name match (existing behavior)
  - config-equivalence match (HTTP URL equality or stdio command/args package identifier match)
- Added HTTP-aware registry type serialization for output:
  - URL-based recommendations in `scan_project` now return `registry_type: "streamable-http"`
    when previously serialized as `npm`
  - `search_servers` now serializes URL-based remotes with transport-backed registry types
    (`streamable-http` / `sse`)
- Removed invalid guidance from blocked-security message in `configure_server`:
  - dropped `bypass_security=True` hint
  - replaced with trusted-alternative guidance
- Added/updated tests to cover:
  - installed detection by remote URL even with alias mismatch
  - remote registry_type serialization in `search_servers`
  - updated security message expectation

## Files Changed

- `src/mcp_tap/tools/scan.py` — installed matching improvements + HTTP-aware registry_type output
- `src/mcp_tap/tools/search.py` — transport-aware registry_type serialization for URL remotes
- `src/mcp_tap/tools/configure.py` — removed invalid `bypass_security` override hint
- `tests/test_tools_scan.py` — new coverage for URL-based installed detection and registry_type
- `tests/test_tools_search.py` — new coverage for remote transport-backed registry_type
- `tests/test_security_gate.py` — updated assertion for blocked-security message
- `docs/issues/2026-02-23_scan-http-polish.md` — completed issue lifecycle

## Verification

- [x] Tests pass: `pytest tests/`
  - `uv run pytest tests/` → 1232 passed
- [x] Linter passes: `ruff check src/ tests/`
  - `uv run ruff check src/ tests/ && uv run ruff format --check src/ tests/` → all checks passed
- [x] Manual verification description
  - Real-world `stz_profile` flow confirmed HTTP-native behavior in prior validation.
  - New test verifies alias mismatch + same URL is now recognized as already installed.

## Lessons Learned

- Keep transport semantics in output serialization close to user-facing tools even when internal
  domain modeling uses installer-centric registry types.
