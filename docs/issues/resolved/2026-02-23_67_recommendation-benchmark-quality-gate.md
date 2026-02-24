# Recommendation Benchmark Quality Gate

- **Date**: 2026-02-23
- **Issue**: #67
- **Status**: `done`
- **Branch**: `feature/2026-02-23-issue-process-and-reco-benchmark`
- **Priority**: `high`

## Problem

`scan_project` + `search_servers` currently rely on qualitative validation and manual review.
There is no objective benchmark proving recommendation quality over time.

## Context

- Core product promise: recommend the best MCP servers for each project stack.
- Current regressions are caught by unit/integration tests, but recommendation quality drift
  is not measured with a reproducible metric.
- Without a benchmark gate, releases can unintentionally reduce recommendation precision.

## Root Cause

No benchmark dataset, no measurable recommendation KPI in CI, and no minimum quality threshold
for release readiness.

## Solution

Implemented an offline recommendation benchmark with deterministic thresholds:

1. Added benchmark module `mcp_tap.benchmark.recommendation` with:
   - versioned dataset loading
   - per-case metrics (`precision@k`, top-1 acceptance proxy)
   - aggregate quality gate with threshold failure support
2. Added versioned dataset file:
   - `src/mcp_tap/benchmark/recommendation_dataset_v1.json`
3. Added executable CLI command:
   - `uv run python -m mcp_tap.benchmark.recommendation`
4. Integrated benchmark gate into CI (Python 3.13 matrix lane).
5. Added benchmark tests and README documentation.

## Files Changed

- `src/mcp_tap/benchmark/recommendation.py` — benchmark runner, metrics, thresholds, CLI
- `src/mcp_tap/benchmark/recommendation_dataset_v1.json` — versioned benchmark dataset
- `src/mcp_tap/benchmark/__main__.py` — package CLI entrypoint
- `src/mcp_tap/benchmark/__init__.py` — benchmark package init
- `.github/workflows/ci.yml` — benchmark gate step in CI
- `tests/test_recommendation_benchmark.py` — benchmark tests
- `README.md` — benchmark command + dataset documentation
- `docs/issues/2026-02-23_67_recommendation-benchmark-quality-gate.md` — issue tracking

## Verification

- [x] Benchmark dataset committed and versioned
- [x] Automated benchmark command available (`uv run ...`)
- [x] Threshold check integrated in CI
- [x] Documentation for running/updating benchmark

Manual run:

- `uv run python -m mcp_tap.benchmark.recommendation` -> PASS

## Lessons Learned

(Optional — if something surprising was discovered, note it here and in MEMORY.md)
