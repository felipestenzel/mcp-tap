# Semantic Intent Routing and Rerank in search_servers

- **Date**: 2026-02-24
- **Issue**: #75
- **Status**: `done`
- **Branch**: `fix/2026-02-24-implement-semantic-intent-rerank`
- **Priority**: `high`

## Problem

Broad multi-word queries (for example `error monitoring`) can still produce noisy top-ranked
results where popularity/provenance signals outrank intent-specific matches.

## Context

- `search_servers` already has deterministic composite scoring with relevance, maturity,
  verified, use_count, and credential_status.
- Real smoke execution exposed semantic-intent drift on broad queries.
- Product promise depends on top results matching user intent, not only generic popularity.

## Root Cause

Current ranking lacks an explicit intent-specific signal for broad semantic queries,
so high-popularity but weak-intent candidates can bubble to the top.

## Solution

Implemented semantic intent routing + deterministic rerank in `search_servers`:

1. Added query intent parsing and controlled query expansion for broad queries:
   - token normalization with stopword filtering
   - intent inference for `error_monitoring` and `incident_management`
   - provider-targeted expansions (`sentry`, `datadog`, `newrelic`, etc.)
2. Added intent scoring per result:
   - new output fields: `intent_match_score`, `intent_match_reason`
   - provider-aware matching that is punctuation/spacing insensitive
3. Integrated intent as the strongest deterministic signal in composite ranking:
   - updated weights: intent + relevance + maturity + verified + use_count + credential
   - deterministic tie-break now includes intent score
4. Added deduplication safeguards:
   - merged expanded-query results deduplicated by server identity
   - package-level dedup in final result assembly
5. Added regression tests for semantic rerank stability:
   - query expansion for `error monitoring`
   - provider-intent outranking generic popularity noise
   - output structure assertions for intent metadata

## Files Changed

- `src/mcp_tap/tools/search.py` — semantic intent routing, query expansion, intent score integration, rerank updates
- `tests/test_tools_search.py` — semantic intent regression tests and composite scoring checks
- `docs/issues/resolved/2026-02-24_75_semantic-intent-rerank-search.md` — issue tracking doc (closed)

## Verification

- [x] Query intent normalization implemented for multi-word queries
- [x] Intent-match signal integrated into deterministic ranking
- [x] Tests added for semantic-intent rerank stability
- [x] Semantic broad-query regression case added (benchmark-style) in test suite

Validation executed:
- `uv run pytest tests/test_tools_search.py -q` -> `25 passed`
- `uv run pytest tests/ -q` -> `1271 passed`
- `uv run --python 3.14 pytest tests/ -q` -> `1271 passed`
- Practical smoke (`search_servers(\"error monitoring\")`) confirms top-ranked provider-intent matches and intent metadata present

## Lessons Learned

(Optional)
