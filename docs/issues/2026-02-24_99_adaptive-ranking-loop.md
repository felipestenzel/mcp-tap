# Adaptive Ranking Loop From Production Feedback

- **Date**: 2026-02-24
- **Issue**: #99
- **Status**: `open`
- **Branch**: `feature/2026-02-24-enterprise-roadmap-issues`
- **Priority**: `low`

## Problem

Ranking weights are static and do not auto-adjust from production outcomes.

## Context

- Deterministic composite scoring already exists in `src/mcp_tap/tools/search.py`.
- Offline quality gate already exists in `src/mcp_tap/benchmark/recommendation.py`.
- There is not enough real-user telemetry volume to safely tune weights yet.

## Root Cause

Adaptive loop assumes production-scale data that the project does not currently have.

## Solution

Decision on 2026-02-24: **deferred to icebox**.

Keep current deterministic ranking and benchmark gate. Reopen only when:
1. There is sustained external usage with representative feedback volume.
2. A stable telemetry schema is adopted by users.
3. A replay dataset can be versioned without privacy risk.

## Files Changed

- `docs/issues/2026-02-24_99_adaptive-ranking-loop.md` — scope reduced and moved to icebox.

## Verification

- [x] Deferred decision documented.
- [x] Existing deterministic path acknowledged as current baseline.

## Lessons Learned

Do not add adaptive systems without enough signal quality and volume.
