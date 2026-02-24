# [TITLE]

- **Date**: YYYY-MM-DD
- **Issue**: #<github-issue-id>
- **Status**: `open` | `in_progress` | `done` | `wont_fix`
- **Branch**: `feature/YYYY-MM-DD-description`
- **Priority**: `critical` | `high` | `medium` | `low`

> Filename format (mandatory): `YYYY-MM-DD_<issue-id>_descriptive-slug.md`
>
> When status becomes `done` or `wont_fix`, move this file to `docs/issues/resolved/`.

## Problem

Describe the problem clearly. What is happening? What should be happening?

## Context

- What module/layer is affected?
- How was this discovered?
- Relevant error messages or logs

## Root Cause

(Fill after investigation)

## Solution

(Fill after implementation)

## Files Changed

- `path/to/file.py` — what changed and why

## Verification

- [ ] Tests pass: `pytest tests/`
- [ ] Linter passes: `ruff check src/ tests/`
- [ ] Manual verification description

## Lessons Learned

(Optional — if something surprising was discovered, note it here and in MEMORY.md)
