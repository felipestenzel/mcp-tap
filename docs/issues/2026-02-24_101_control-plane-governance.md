# Optional Control Plane For Governance And Fleet Visibility

- **Date**: 2026-02-24
- **Issue**: #101
- **Status**: `open`
- **Branch**: `feature/2026-02-24-enterprise-roadmap-issues`
- **Priority**: `high`

## Problem

mcp-tap is local-first, but enterprise teams need centralized governance and observability across
many projects and clients.

## Context

- Local capabilities are strong (scan/search/configure/verify/restore).
- Missing for team scale:
  - centralized policy/config bundle management
  - fleet-level health/drift telemetry
  - rollout channels (stable/canary) at organization scope

## Root Cause

No remote coordination layer exists. Every installation behaves as an isolated node with no shared
control-plane contract.

## Solution

Implement optional control-plane integration without degrading local-first reliability.

### Phase 1 (MVP)

1. Define control-plane API contract (self-hostable).
2. Add project enrollment and identity model.
3. Build pull-based bundle sync with signature verification.
4. Add resilient local cache and last-known-good fallback.
5. Add batched telemetry export (health/drift/recommendation outcomes).

### Reliability Constraints

- Local execution must continue when control plane is down.
- Control-plane mode must be opt-in.

## Files Changed

- `docs/issues/2026-02-24_101_control-plane-governance.md` — tracking spec for implementation

## Verification

- [ ] Tests pass: `uv run pytest tests/ -q`
- [ ] Linter passes: `uv run ruff check src/ tests/`
- [ ] Enrollment and signed bundle sync work in integration tests
- [ ] Offline fallback uses last-known-good bundle without blocking local operations
- [ ] Telemetry export queue handles retries and backpressure safely
- [ ] Rollout channel assignment affects loaded bundle version deterministically

## Lessons Learned

(Complete after implementation)
