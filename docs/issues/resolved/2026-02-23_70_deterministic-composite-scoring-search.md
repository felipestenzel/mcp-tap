# Deterministic Composite Scoring in search_servers

- **Date**: 2026-02-23
- **Issue**: #70
- **Status**: `done`
- **Branch**: `feature/2026-02-23-issue-process-and-reco-benchmark`
- **Priority**: `high`

## Problem

`search_servers` already exposes strong quality signals, but ranking still depends heavily on LLM
interpretation, causing recommendation variance.

## Context

- Signals already available: relevance, maturity, verified, use_count, credential_status.
- Product promise is to recommend the best MCPs consistently.
- Deterministic scoring reduces behavioral drift between sessions and clients.

## Root Cause

No single weighted ranking formula currently combines all known recommendation signals.

## Solution

Implemented deterministic composite ranking in `search_servers`:

1. Added weighted score model combining:
   - relevance
   - maturity
   - verified
   - use_count
   - credential_status
2. Added output fields per result:
   - `composite_score`
   - `composite_breakdown` (weights, normalized signals, contributions)
3. Added stable deterministic sorting key based on:
   - composite score
   - relevance tier
   - maturity score
   - use_count
   - name/index tie-breakers
4. Added unit/integration coverage for composite ranking behavior.

## Files Changed

- `src/mcp_tap/tools/search.py` — composite scoring logic + deterministic sort + fields
- `tests/test_tools_search.py` — composite scoring tests and result structure assertions
- `docs/issues/2026-02-23_70_deterministic-composite-scoring-search.md` — issue tracking

## Verification

- [x] Composite score formula documented
- [x] Ranked output includes score and explanation fields
- [x] Ranking stability tests added
- [x] Backward compatibility validated

Validation commands:

- `uv run pytest tests/test_tools_search.py -q` -> PASS
- `uv run pytest tests/ -q` -> PASS

## Lessons Learned

(Optional — if something surprising was discovered, note it here and in MEMORY.md)
