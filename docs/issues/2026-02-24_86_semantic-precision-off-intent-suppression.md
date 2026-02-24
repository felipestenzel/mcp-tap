# Semantic Precision V2: Off-Intent Suppression in `search_servers`

- **Date**: 2026-02-24
- **Issue**: #86
- **Status**: `open`
- **Branch**: `feature/2026-02-24-quality-gap-issues`
- **Priority**: `critical`

## Problem

`search_servers` improved semantic ranking in v0.6.6, but practical smoke still shows
off-intent noise in top-k for broad intent queries.

Observed output (real smoke post-release):
- Query: `error monitoring`
- Relevant providers appeared: `sentry`, `newrelic`, `datadog`
- But an off-intent candidate (`Supabase`) still appeared in top-2

For discovery UX, top-3 must be intent-clean. Partial improvement is not enough.

## Context

- Module affected: `src/mcp_tap/tools/search.py`
- Current state already includes:
  - query expansion
  - intent score (`intent_match_score`, `intent_match_reason`)
  - deterministic composite rerank
- Remaining gap appears when popularity/provenance + partial lexical overlap can still outrank
  weakly related generic tools.

## Root Cause

(Working hypothesis; confirm in implementation)

1. Retrieval stage is recall-oriented and intentionally broad, but precision cleanup is incomplete.
2. Current ranking has strong positive intent signals, but lacks a clear negative off-intent prior.
3. Candidate suppression/gating before final top-k is insufficient for broad semantic queries.

## Solution

Implement **Semantic Precision V2** with two-stage ranking:

### 1) Stage A: Recall-Oriented Candidate Retrieval
- Keep current query expansion (intent + provider hints)
- Keep broad candidate pool (do not over-prune retrieval)

### 2) Stage B: Precision-Oriented Intent Suppression
- Add explicit negative evidence model per intent family (off-intent priors)
- Add intent-confidence thresholding before final top-k
- Demote low-confidence/off-intent candidates below high-confidence intent matches
- Preserve deterministic ordering rules

### 3) Optional Debug Signals (if API-safe)
- `intent_confidence`
- `intent_positive_signals`
- `intent_negative_signals`
- `intent_gate_applied`

### 4) Benchmark + Regression Coverage
- Add broad-intent fixtures to recommendation benchmark
- Add unit regression tests for off-intent suppression in `tests/test_tools_search.py`
- Add release smoke assertion for target query class (`error monitoring`)

## Files Changed

- `src/mcp_tap/tools/search.py` — intent suppression/gating logic
- `tests/test_tools_search.py` — regression tests for broad-query precision
- `src/mcp_tap/benchmark/recommendation_dataset_v1.json` — broad-intent fixtures
- `tests/test_recommendation_benchmark.py` — benchmark assertions for semantic precision
- `docs/issues/2026-02-24_86_semantic-precision-off-intent-suppression.md` — issue tracking

## Verification

- [ ] Tests pass: `pytest tests/`
- [ ] Linter passes: `ruff check src/ tests/`
- [ ] Broad intent query top-3 has only intent-relevant candidates
- [ ] Deterministic output preserved for identical input
- [ ] No regression in narrow/exact query behavior

## Lessons Learned

(Complete after delivery)

## References

- OpenSearch hybrid ranking optimization:
  - https://docs.opensearch.org/latest/search-plugins/search-relevance/optimize-hybrid-search/
- OpenSearch reciprocal rank fusion (RRF):
  - https://opensearch.org/blog/introducing-reciprocal-rank-fusion-hybrid-search/
- Azure semantic ranking (two-stage concept):
  - https://learn.microsoft.com/en-us/azure/search/semantic-ranking
