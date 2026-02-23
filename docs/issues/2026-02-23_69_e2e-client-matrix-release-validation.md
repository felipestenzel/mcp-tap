# Multi-Client E2E Matrix for Release Validation

- **Date**: 2026-02-23
- **Issue**: #69
- **Status**: `open`
- **Branch**: `feature/2026-02-23-e2e-client-matrix`
- **Priority**: `high`

## Problem

Even with strong unit/integration coverage, release confidence would improve with real end-to-end
validation across supported MCP clients.

## Context

- Supported clients include Claude Code, Cursor, and Windsurf.
- Recent work added HTTP-native/per-client behavior and canonical matching.
- Compatibility regressions are expensive because they are discovered after release.

## Root Cause

No automated E2E client matrix exists for release-critical flows.

## Solution

(Fill after implementation)

## Files Changed

- `docs/issues/2026-02-23_69_e2e-client-matrix-release-validation.md` — issue tracking doc

## Verification

- [ ] Matrix scenarios defined per client
- [ ] E2E harness automated for release usage
- [ ] Critical flows covered: configure/list/verify/restore
- [ ] Docs with run instructions and prerequisites

## Lessons Learned

(Optional — if something surprising was discovered, note it here and in MEMORY.md)
