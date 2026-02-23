# Archive Resolved Issue Docs into docs/issues/resolved

- **Date**: 2026-02-23
- **Issue**: #71
- **Status**: `done`
- **Branch**: `feature/2026-02-23-issue-process-and-reco-benchmark`
- **Priority**: `medium`

## Problem

After introducing the active/resolved split, historical issue docs with `Status: done` remain in
`docs/issues/`.

## Context

- New process requires active issues in `docs/issues/` and completed issues in
  `docs/issues/resolved/`.
- Current repository still has many completed items in the active folder.

## Root Cause

The folder policy was introduced after most issues were already closed, without retroactive
migration.

## Solution

Executed a retroactive archive migration:

1. Added `docs/issues/resolved/` as the canonical location for completed issues.
2. Moved every file in `docs/issues/` with `Status: done` to `docs/issues/resolved/`.
3. Kept active files (`Status: open`/`in_progress`) and `_TEMPLATE.md` in `docs/issues/`.
4. Confirmed process documentation already enforces this behavior for future work.

## Files Changed

- `docs/issues/2026-02-23_71_archive-resolved-issue-docs.md` — migration tracking issue doc
- `docs/issues/resolved/*.md` — 30 completed issue docs archived from active folder

## Verification

- [x] All `done`/`wont_fix` issues moved to `docs/issues/resolved/`
- [x] Only active issues remain in `docs/issues/` (+ `_TEMPLATE.md`)
- [x] `CLAUDE.md` and template rules remain consistent

## Lessons Learned

(Optional — if something surprising was discovered, note it here and in MEMORY.md)
