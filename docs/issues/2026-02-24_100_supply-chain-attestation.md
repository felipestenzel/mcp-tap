# Lockfile Integrity MVP (Minimal Supply-Chain Hardening)

- **Date**: 2026-02-24
- **Issue**: #100
- **Status**: `open`
- **Branch**: `feature/2026-02-24-enterprise-roadmap-issues`
- **Priority**: `medium`

## Problem

`mcp-tap.lock` is reproducible but does not provide optional cryptographic integrity checks.

## Context

- Current baseline already includes security gate and drift verification.
- Full SBOM/attestation pipeline is too heavy for current project stage.

## Root Cause

The original proposal was enterprise-grade from day one.

## Solution

Re-scoped to a **minimal local MVP**:

1. Add optional lockfile signature command (`sign-lockfile` style utility).
2. Add optional verify command/check (`verify-lockfile-signature`).
3. Add strict opt-in flag for `restore`/`configure` to require valid signature.
4. Keep default behavior unchanged (non-strict remains current flow).

Out of scope for this issue:
- SBOM generation
- in-toto/SLSA end-to-end provenance platform
- remote trust-store service

## Files Changed

- `docs/issues/2026-02-24_100_supply-chain-attestation.md` — reduced to MVP scope.

## Verification

- [ ] Tests pass: `uv run pytest tests/`
- [ ] Linter passes: `uv run ruff check src/ tests/`
- [ ] Invalid signature is blocked in strict mode
- [ ] Non-strict mode remains backward compatible

## Lessons Learned

Security improvements should be incremental and opt-in by default.
