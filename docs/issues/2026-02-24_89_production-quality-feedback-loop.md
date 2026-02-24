# Production Recommendation Quality Feedback Loop

- **Date**: 2026-02-24
- **Issue**: #89
- **Status**: `open`
- **Branch**: `feature/2026-02-24-quality-gap-issues`
- **Priority**: `high`

## Problem

Recommendation quality is currently validated offline (benchmark gate), but not measured
systematically in production usage outcomes.

Without online feedback, we cannot reliably detect:
- quality regressions that benchmark fixtures do not capture
- real acceptance behavior shifts after ranking changes
- version-over-version impact on recommendation usefulness

## Context

- Existing benchmark infrastructure is strong for offline guardrails
- Missing layer: opt-in production telemetry + aggregation for decision-quality metrics
- Product goal (“best MCPs for each project”) benefits from real acceptance/rejection signals

## Root Cause

Current quality loop ends at offline evaluation and CI thresholds. No structured online event model
exists to close the loop with real-world outcomes.

## Solution

Implement an opt-in production quality loop:

1. Event schema (privacy-safe)
   - recommendations shown
   - recommendation accepted/configured
   - recommendation rejected/ignored
   - query metadata + ranked snapshot (non-sensitive)
2. Metric aggregation
   - acceptance@k
   - top-1 conversion
   - off-intent rejection rate
   - stability/drift indicators by release version
3. Reporting
   - periodic report artifact
   - version-segmented trend analysis
4. Governance
   - explicit opt-in policy
   - no secrets/source leakage
   - progressive release gates (warn-first, block later)

## Files Changed

- `src/mcp_tap/benchmark/` (extend metrics and reporting)
- potential new telemetry module (if accepted in architecture)
- docs for privacy policy and opt-in controls
- `docs/issues/2026-02-24_89_production-quality-feedback-loop.md` — issue tracking

## Verification

- [ ] Tests pass: `pytest tests/`
- [ ] Linter passes: `ruff check src/ tests/`
- [ ] Event schema validated via tests
- [ ] Synthetic data produces stable quality report output
- [ ] Version-based trend segmentation works

## Lessons Learned

(Complete after delivery)

## References

- Offline relevance evaluation framing:
  - https://www.pinecone.io/learn/offline-evaluation/
- Ranking quality metric background:
  - https://www.evidentlyai.com/ranking-metrics/ndcg-metric
