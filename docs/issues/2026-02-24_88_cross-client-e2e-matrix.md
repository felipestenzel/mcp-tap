# Cross-Client E2E Compatibility Matrix

- **Date**: 2026-02-24
- **Issue**: #88
- **Status**: `open`
- **Branch**: `feature/2026-02-24-quality-gap-issues`
- **Priority**: `high`

## Problem

Current coverage is strong in unit/integration/release checks, but we still lack a robust,
continuous end-to-end matrix focused on client-specific compatibility paths.

Risk: regressions can pass current tests while breaking one client path (`claude_code`, `cursor`,
`windsurf`) due to transport/config differences.

## Context

- Affected modules:
  - `src/mcp_tap/tools/configure.py`
  - `src/mcp_tap/tools/verify.py`
  - `src/mcp_tap/tools/health.py`
  - client detection/config reader/writer adapters
- Prior work added matrix foundations and release validation, but not full workflow E2E per client
  as a permanent quality gate.

## Root Cause

Compatibility logic is spread across transport, config serialization, and drift verification layers.
Without a true workflow matrix per client, cross-layer regressions can be missed.

## Solution

Add a dedicated E2E matrix suite with full client workflows:

1. For each client profile (`claude_code`, `cursor`, `windsurf`):
   - configure server
   - verify lockfile/config drift
   - run health check
   - cleanup/remove
2. Cover transport scenarios:
   - native HTTP path
   - fallback (`mcp-remote`) path
   - mixed multi-client path in one operation
3. Add CI matrix job with clear failure artifacts/logs
4. Define optional scheduled/manual real-client validation if hosted CI cannot reproduce all
   environment constraints

## Files Changed

- `tests/test_release_client_matrix.py` (or new `tests/e2e_clients/`) — expanded E2E suite
- `.github/workflows/ci.yml` — E2E matrix lane(s)
- `docs/issues/2026-02-24_88_cross-client-e2e-matrix.md` — issue tracking

## Verification

- [ ] Tests pass: `pytest tests/`
- [ ] Linter passes: `ruff check src/ tests/`
- [ ] E2E matrix covers all three clients
- [ ] Mixed-client transport scenario validated in CI
- [ ] CI blocks merge on client compatibility regressions

## Lessons Learned

(Complete after delivery)

## References

- GitHub Actions matrix jobs:
  - https://docs.github.com/actions/using-jobs/using-a-matrix-for-your-jobs
