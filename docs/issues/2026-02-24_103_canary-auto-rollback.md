# Safe Rollback MVP For Configuration Changes

- **Date**: 2026-02-24
- **Issue**: #103
- **Status**: `open`
- **Branch**: `feature/2026-02-24-enterprise-roadmap-issues`
- **Priority**: `medium`

## Problem

`configure_server` changes config directly once pre-checks pass. There is no simple local rollback
artifact produced automatically before writes.

## Context

- Fleet-scale canary orchestration is out of scope for the current product stage.
- A local snapshot/rollback primitive delivers most of the safety value with low complexity.

## Root Cause

Original issue proposed fleet deployment semantics instead of local CLI safety primitives.

## Solution

Re-scoped to a **local rollback MVP**:

1. Before destructive config writes, save snapshot of affected config + lockfile metadata.
2. Expose a simple rollback command that restores the last snapshot.
3. Keep snapshot retention bounded and deterministic.
4. No fleet rollout channels, no canary orchestration, no remote controller.

## Files Changed

- `docs/issues/2026-02-24_103_canary-auto-rollback.md` — reduced to local MVP scope.

## Verification

- [ ] Tests pass: `uv run pytest tests/`
- [ ] Linter passes: `uv run ruff check src/ tests/`
- [ ] Snapshot exists before write
- [ ] Rollback restores config and lockfile state
- [ ] Snapshot cleanup policy tested

## Lessons Learned

For a local-first CLI, prioritize reversible local operations over fleet workflows.
