# End-to-End Install Flow in configure_server

- **Date**: 2026-02-19
- **Status**: `open`
- **Branch**: `feature/2026-02-19-e2e-install-flow`
- **Priority**: `high`
- **Issue**: #3

## Problem

`configure_server` currently writes config to the client JSON file but **never calls `install()`** on the package and **never validates the connection**. It says "Done!" without verifying the server actually works. This is effectively lying to the user.

## Context

- `installer/npm.py`, `pip.py`, `docker.py` all exist and work — they're just never called by the tool
- `connection/tester.py` exists and works — also never called by configure
- The flow should be: resolve installer → install package → write config → validate connection → report
- If install fails, config should NOT be written (don't leave broken entries)
- If validation fails, config should still be written but the failure reported clearly

## Scope

1. **Update `tools/configure.py`**:
   - Step 1: Resolve installer via `resolver.resolve()`
   - Step 2: Call `installer.install(identifier, version)`
   - Step 3: If install fails, return error (do NOT write config)
   - Step 4: Write config atomically (existing logic)
   - Step 5: Call `test_server_connection()` to validate
   - Step 6: Return enriched result with install status + tools discovered

2. **Update `ConfigureResult` in `models.py`**:
   - Add `install_status: str` (installed / already_available / failed)
   - Add `tools_discovered: list[str]` (from validation step)
   - Add `validation_passed: bool`

3. **Tests**:
   - Mock installer + tester
   - Test happy path: install ok → config written → validation ok
   - Test install failure: no config written
   - Test validation failure: config written + warning

## Root Cause

configure_server was built as config-writer-only, skipping the install and validate steps.

## Solution

(Fill after implementation)

## Files Changed

(Fill after implementation)

## Verification

- [ ] Tests pass: `pytest tests/`
- [ ] Linter passes: `ruff check src/ tests/`
- [ ] `configure_server` calls installer before writing config
- [ ] Failed installs do not leave orphaned config entries
- [ ] Successful installs report discovered tools
