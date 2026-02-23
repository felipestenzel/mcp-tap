# Deterministic Composite Scoring in search_servers

- **Date**: 2026-02-23
- **Issue**: #70
- **Status**: `open`
- **Branch**: `feature/2026-02-23-deterministic-composite-scoring`
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

(Fill after implementation)

## Files Changed

- `docs/issues/2026-02-23_70_deterministic-composite-scoring-search.md` — issue tracking doc

## Verification

- [ ] Composite score formula documented
- [ ] Ranked output includes score and explanation fields
- [ ] Ranking stability tests added
- [ ] Backward compatibility validated

## Lessons Learned

(Optional — if something surprising was discovered, note it here and in MEMORY.md)
