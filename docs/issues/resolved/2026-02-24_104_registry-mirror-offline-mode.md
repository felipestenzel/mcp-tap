# Registry Cache Fallback And Offline Search Metadata

- **Date**: 2026-02-24
- **Issue**: #104
- **Status**: `done`
- **Branch**: `feature/2026-02-24-enterprise-roadmap-issues`
- **Priority**: `high`

## Problem

`search_servers` depended on live registry availability. During transient outages, discovery could
fail even when recent successful results existed.

## Context

- Online search is provided by `AggregatedRegistry` (official + Smithery).
- There was no fallback path when registry calls failed at runtime.

## Root Cause

No query-level cache fallback existed in the aggregated registry adapter.

## Solution

Implemented a minimal offline fallback (no mirror service):

1. Added in-memory cache in `AggregatedRegistry` keyed by normalized query.
2. Cache stores successful merged results with TTL.
3. On live search failures (with no live merged result), adapter returns cached results.
4. `search_servers` now marks fallback responses with:
   - `cache_status: "stale_fallback"`
   - `cache_age_seconds`

## Files Changed

- `src/mcp_tap/registry/aggregator.py` — query cache + TTL + fallback flags.
- `src/mcp_tap/tools/search.py` — result metadata for cache fallback visibility.
- `tests/test_registry_aggregator.py` — cache fallback behavior tests.
- `tests/test_tools_search.py` — cache metadata propagation test.
- `docs/issues/2026-02-24_104_registry-mirror-offline-mode.md` — final issue record.

## Verification

- [x] Tests pass: `uv run pytest tests/`
- [x] Linter passes: `uv run ruff check src/ tests/`
- [x] Fallback uses cache only when live calls fail
- [x] Empty live responses without errors do not incorrectly reuse stale cache
- [x] Cache fallback is explicit in search result metadata

## Lessons Learned

A small adapter-level fallback solves the practical outage case without introducing mirror
infrastructure complexity.
