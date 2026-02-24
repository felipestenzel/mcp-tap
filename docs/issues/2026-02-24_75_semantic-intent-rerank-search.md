# Semantic Intent Routing and Rerank in search_servers

- **Date**: 2026-02-24
- **Issue**: #75
- **Status**: `open`
- **Branch**: `fix/2026-02-24-semantic-search-rerank-issue`
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

(Fill after implementation)

## Files Changed

- `docs/issues/2026-02-24_75_semantic-intent-rerank-search.md` — issue tracking doc

## Verification

- [ ] Query intent normalization implemented for multi-word queries
- [ ] Intent-match signal integrated into deterministic ranking
- [ ] Tests added for semantic-intent rerank stability
- [ ] Benchmark extended with broad-query semantic case

## Lessons Learned

(Optional)
