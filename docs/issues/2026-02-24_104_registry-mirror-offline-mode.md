# Registry Mirror Cache And Offline Discovery Mode

- **Date**: 2026-02-24
- **Issue**: #104
- **Status**: `open`
- **Branch**: `feature/2026-02-24-enterprise-roadmap-issues`
- **Priority**: `high`

## Problem

Discovery quality depends on live registry availability. Outages or network constraints can block
search/recommendation workflows.

## Context

- Current behavior: aggregated online search (official + Smithery).
- Missing:
  - durable local cache with provenance
  - explicit offline mode
  - safe reconciliation after reconnect

## Root Cause

No persistent mirror/cache strategy is available in the registry adapter path.

## Solution

Add local mirror cache and explicit offline discovery path with staleness signaling.

### Phase 1 (MVP)

1. Persist registry responses with provenance + timestamp.
2. Add TTL/staleness policy and cache health indicators.
3. Add `offline` mode path for `search_servers`.
4. Add reconciliation command to refresh cache safely.

### Phase 2

- Background periodic reconcile worker.
- Scoped cache partitions per environment/team.

## Files Changed

- `docs/issues/2026-02-24_104_registry-mirror-offline-mode.md` — tracking spec for implementation

## Verification

- [ ] Tests pass: `uv run pytest tests/ -q`
- [ ] Linter passes: `uv run ruff check src/ tests/`
- [ ] Offline search works with cache-only mode
- [ ] Staleness is explicit in result metadata
- [ ] Reconcile refreshes cache without corrupting existing entries
- [ ] Fallback behavior is deterministic during upstream outage simulation

## Lessons Learned

(Complete after implementation)
