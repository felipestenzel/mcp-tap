# Auto GitHub Token Fallback + Maturity Degradation Transparency

- **Date**: 2026-02-25
- **Issue**: #110
- **Status**: `done`
- **Branch**: `fix/2026-02-25-github-maturity-autotoken`
- **Priority**: `high`

## Problem

`search_servers` maturity scoring degrades when GitHub API rate-limit is hit without token, and
users currently need manual `GITHUB_TOKEN` setup to recover full quality.

## Context

- `src/mcp_tap/evaluation/github.py` supports `GITHUB_TOKEN`, cache and rate-limit backoff.
- `src/mcp_tap/tools/search.py` uses maturity in composite ranking.
- When maturity metadata is unavailable, ranking can be unfairly penalized.

## Root Cause

- Auth source is single-path (env var only) and not auto-healed from local `gh` auth context.
- Maturity degradation state is implicit (missing maturity fields), not explicit in results.
- Composite weights keep fixed maturity weight even when that signal is unavailable.

## Solution

Implemented all planned items:

1. Added non-persistent auth fallback in GitHub evaluation:
   - token resolution order: `GITHUB_TOKEN` -> `gh auth token`
   - in-memory runtime status exposure (`has_auth`, `auth_source`, `rate_limited`,
     `rate_limit_reset_seconds`)
2. Added explicit maturity availability metadata in `search_servers` results for GitHub repos:
   - `maturity_signal_available`
   - `maturity_status`
   - `maturity_unavailable_reason`
   - `maturity_auth_source`
3. Rebalanced composite scoring when maturity is unavailable:
   - maturity weight is redistributed to other signals
   - no unfair zero-penalty when GitHub metadata is missing
4. Added one clear `ctx.info` warning per search call when degradation is detected.
5. Added regression tests for fallback auth, runtime status, degradation annotation and
   rebalanced scoring behavior.

## Files Changed

- `src/mcp_tap/evaluation/github.py` — token fallback + runtime status + improved rate-limit hints.
- `src/mcp_tap/tools/search.py` — degradation annotation + warning + maturity weight rebalance.
- `tests/test_evaluation.py` — token resolution/runtime status test coverage.
- `tests/test_tools_search.py` — degradation annotation/warning and composite rebalance tests.
- `docs/issues/resolved/2026-02-25_110_github-maturity-autotoken.md` — final issue record.

## Verification

- [x] Baseline tests pass: `uv run pytest tests/ -q`
- [x] New tests pass for token fallback and degraded metadata
- [x] Composite scoring remains deterministic
- [x] Linter/format checks pass (`uv run ruff check src/ tests/`)
- [x] Formatter check passes (`uv run ruff format --check src/ tests/`)

## Lessons Learned

Making maturity degradation explicit in payloads prevents LLM-side ambiguity, while deterministic
weight rebalance keeps ranking quality stable during external API quota pressure.
