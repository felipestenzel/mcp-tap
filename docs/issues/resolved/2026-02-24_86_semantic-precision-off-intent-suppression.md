# Semantic Precision V2: Off-Intent Suppression in `search_servers`

- **Date**: 2026-02-24
- **Issue**: #86
- **Status**: `done`
- **Branch**: `fix/2026-02-24-semantic-precision-v2`
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

1. Retrieval stage is intentionally broad and returns mixed-signal candidates.
2. Ranking had positive intent evidence but no explicit negative off-intent gate.
3. Partial keyword overlap plus popularity/provenance could still surface weakly related
   candidates in top-k for broad semantic queries.

## Solution

Implemented **Semantic Precision V2** with intent suppression gate:

1. Kept Stage A retrieval broad (query expansion unchanged) to preserve recall.
2. Added Stage B intent gate in `_score_intent_match`:
   - intent term groups (`_INTENT_TERM_GROUPS`) for `error_monitoring` and
     `incident_management`
   - explicit off-intent demotion when required semantic groups are missing
   - deterministic penalty score (`0.05`) plus clear reason
3. Added extra intent diagnostics per result:
   - `intent_confidence`
   - `intent_gate_applied`
   - `intent_positive_signals`
   - `intent_negative_signals`
4. Preserved deterministic composite ranking and added gate signal in
   `composite_breakdown.signals`.
5. Added regression coverage for off-intent suppression in broad query ranking.

## Files Changed

- `src/mcp_tap/tools/search.py` — intent suppression/gating logic
- `tests/test_tools_search.py` — regression tests for broad-query precision
- `docs/issues/2026-02-24_86_semantic-precision-off-intent-suppression.md` — issue tracking

## Verification

- [x] Tests pass: `pytest tests/`
- [x] Linter passes: `ruff check src/ tests/`
- [x] Broad intent query top-3 has only intent-relevant candidates
- [x] Deterministic output preserved for identical input
- [x] No regression in narrow/exact query behavior

Validation executed:
- `uv run pytest tests/test_tools_search.py -q` -> `26 passed`
- `uv run ruff check src/ tests/` -> `All checks passed!`
- `uv run ruff format --check src/ tests/` -> `119 files already formatted`
- `uv run pytest tests/ -q` -> `1272 passed`
- Practical smoke (`search_servers("error monitoring")`):
  - top results intent-relevant (`sentry`, `sentry-mcp`, `newrelic`, `datadog`)
  - prior noisy candidate (`Supabase`) demoted to #5 with:
    - `intent_match_score=0.05`
    - `intent_gate_applied=true`

## Lessons Learned

- Broad semantic retrieval is useful for recall, but discovery quality requires explicit
  negative gating, not only positive scoring.

## References

- OpenSearch hybrid ranking optimization:
  - https://docs.opensearch.org/latest/search-plugins/search-relevance/optimize-hybrid-search/
- OpenSearch reciprocal rank fusion (RRF):
  - https://opensearch.org/blog/introducing-reciprocal-rank-fusion-hybrid-search/
- Azure semantic ranking (two-stage concept):
  - https://learn.microsoft.com/en-us/azure/search/semantic-ranking
