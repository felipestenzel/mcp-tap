# Configure Preflight Dry-Run (Sandbox Step 1)

- **Date**: 2026-02-24
- **Issue**: #105
- **Status**: `done`
- **Branch**: `feature/2026-02-24-enterprise-roadmap-issues`
- **Priority**: `high`

## Problem

Users had no safe preflight mode in `configure_server` to test installation/validation without
writing client config.

## Context

- `configure_server` already installs, validates, and writes config.
- `test_connection` exists but requires an already configured server entry.
- We needed a no-write preflight path for lower-trust candidates.

## Root Cause

`configure_server` lacked an explicit dry-run execution mode.

## Solution

Implemented `dry_run` in `configure_server`:

1. Added `dry_run: bool = False` parameter to tool signature.
2. For stdio servers:
   - install + validate (and optional self-healing attempt)
   - do not write config
   - do not update lockfile
   - do not emit accepted-recommendation telemetry
3. For HTTP servers:
   - run reachability preflight
   - return per-client config preview
   - do not write config/lockfile
4. Dry-run responses include `dry_run: true` and `install_status: "dry_run"`.

## Files Changed

- `src/mcp_tap/tools/configure.py` — dry-run flow and preflight helpers.
- `tests/test_tools_configure.py` — dry-run tests for stdio and HTTP paths.
- `docs/issues/2026-02-24_105_sandbox-preflight-untrusted-servers.md` — final issue record.

## Verification

- [x] Tests pass: `uv run pytest tests/`
- [x] Linter passes: `uv run ruff check src/ tests/`
- [x] Dry-run validates without writing config files
- [x] Dry-run skips lockfile update and accepted telemetry event
- [x] HTTP dry-run returns config preview without file writes

## Lessons Learned

A preflight dry-run delivers concrete safety value now and can serve as the foundation for stricter
sandboxing later.
