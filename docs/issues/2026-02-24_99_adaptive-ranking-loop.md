# Adaptive Ranking Loop From Production Feedback

- **Date**: 2026-02-24
- **Issue**: #99
- **Status**: `open`
- **Branch**: `feature/2026-02-24-enterprise-roadmap-issues`
- **Priority**: `high`

## Problem

Search ranking is strong but uses static deterministic weights. Over time, real usage may diverge
from offline assumptions, and quality regressions can pass unnoticed between releases.

## Context

- Existing strengths:
  - semantic intent scoring in `tools/search.py`
  - deterministic composite ranking
  - offline benchmark gate (`benchmark/recommendation.py`)
  - opt-in production telemetry (`benchmark/production_feedback.py`)
- Missing: controlled mechanism to tune weights from real outcomes while keeping deterministic safety.

## Root Cause

The quality loop currently ends at fixed-weight evaluation. Production feedback is collected but not
used to generate and safely promote improved ranking artifacts.

## Solution

Create a reproducible adaptive ranking pipeline with strict guardrails.

### Phase 1 (MVP)

1. Add versioned weight artifact (`ranking_weights_vN.json`).
2. Build offline optimizer using production feedback replay.
3. Compare baseline vs candidate via holdout replay.
4. Add canary rollout mode for candidate weights.
5. Auto-rollback when acceptance@k drops past threshold.

### Guardrails

- Deterministic fallback to default weights on any anomaly.
- Minimum sample size before any weight update.
- Full audit metadata: dataset window, metrics, chosen artifact, rollback reason.

## Files Changed

- `docs/issues/2026-02-24_99_adaptive-ranking-loop.md` — tracking spec for implementation

## Verification

- [ ] Tests pass: `uv run pytest tests/ -q`
- [ ] Linter passes: `uv run ruff check src/ tests/`
- [ ] Same dataset -> same optimized weights (reproducibility)
- [ ] Candidate weights pass replay quality gate before rollout
- [ ] Canary + rollback logic covered with deterministic tests
- [ ] Ranking remains deterministic for fixed weight artifact

## Lessons Learned

(Complete after implementation)
