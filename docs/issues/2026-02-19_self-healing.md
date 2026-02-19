# Self-Healing Retry Loop (Post-Launch)

- **Date**: 2026-02-19
- **Status**: `open`
- **Branch**: `feature/YYYY-MM-DD-self-healing`
- **Priority**: `low`
- **Issue**: #10

## Problem

When a server installation or connection fails, mcp-tap just reports the error. It does not attempt to diagnose, fix, and retry. "My MCP server broke and mcp-tap fixed it" is the #2 differentiator from the creative brief.

## Context

- **DEFERRED TO POST-LAUNCH** — the error taxonomy is unknowable until real users hit real failures
- Building a classifier for imagined errors is waste; real user data will reveal actual failure modes
- Prerequisite: Issue #3 (E2E install flow) and Issue #4 (health check) must work first
- Launch, collect 50+ error reports, THEN build self-healing against real patterns

## Scope (Planned — Refine After Launch Data)

1. **New module** (`healing/`):
   - `classifier.py` — parse error messages into categories:
     - ENOENT (command not found)
     - CONNECTION_REFUSED (wrong port, transport mismatch)
     - AUTH_FAILED (missing/invalid credentials)
     - TIMEOUT (server too slow to start)
     - MISSING_ENV_VAR (required env var not set)
   - `fixer.py` — for each category, generate a candidate fix:
     - ENOENT → suggest install command
     - CONNECTION_REFUSED → try alternate transport
     - AUTH_FAILED → prompt for credentials
     - MISSING_ENV_VAR → suggest env var name and format

2. **Retry wrapper**:
   - Apply fix → re-test → up to 3 attempts
   - Each attempt logged with what was tried

3. **Integration**:
   - Post-validation step in `configure_server`
   - Optional auto-heal in `test_connection`
   - Triggered by `check_health` for batch fixes

## Root Cause

No error diagnosis logic exists — only basic error reporting.

## Solution

(Fill after real user error data is collected)

## Files Changed

(Fill after implementation)

## Verification

- [ ] Tests pass with intentionally broken server configs
- [ ] At least 3 error categories correctly classified
- [ ] Retry loop fixes at least 2 common failure modes
- [ ] Clear reporting of what was tried and what worked

## Lessons Learned

**Strategic note**: Do NOT build this pre-launch. The first 50 real users will tell us exactly what breaks and how. That data is worth more than any amount of upfront engineering.
