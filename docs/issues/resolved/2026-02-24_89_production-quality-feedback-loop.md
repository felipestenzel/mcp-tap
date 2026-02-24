# Production Recommendation Quality Feedback Loop

- **Date**: 2026-02-24
- **Issue**: #89
- **Status**: `done`
- **Branch**: `fix/2026-02-24-production-quality-feedback-loop`
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

- `src/mcp_tap/benchmark/production_feedback.py` — event schema, JSONL telemetry, aggregation, CLI report
- `src/mcp_tap/tools/scan.py` — emits `recommendations_shown` (best-effort) and returns `feedback_query_id`
- `src/mcp_tap/tools/configure.py` — emits `recommendation_accepted` on successful configure
- `tests/test_production_feedback.py` — schema/metrics/version trend tests with synthetic events
- `tests/test_tools_scan.py` — telemetry hook assertion for scan output
- `tests/test_tools_configure.py` — telemetry hook assertion for configure success
- `README.md` — opt-in policy and reporting command
- `docs/issues/2026-02-24_89_production-quality-feedback-loop.md` — issue tracking

## Verification

- [x] Tests pass: `uv run pytest tests/ -q`
- [x] Linter passes: `uv run ruff check src/ tests/`
- [x] Event schema validated via tests
- [x] Synthetic data produces stable quality report output
- [x] Version-based trend segmentation works

## Lessons Learned

- Telemetry must stay strictly opt-in and fail-safe; feedback capture can never break core configure/scan flows.
- A single event schema with query-linked IDs makes offline benchmark and online usage metrics directly comparable.
- Drift gating is safer as warn/block thresholds over version deltas instead of absolute static thresholds.

## References

- Offline relevance evaluation framing:
  - https://www.pinecone.io/learn/offline-evaluation/
- Ranking quality metric background:
  - https://www.evidentlyai.com/ranking-metrics/ndcg-metric
