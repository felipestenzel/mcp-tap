# Supply Chain Attestation And Lockfile Signing

- **Date**: 2026-02-24
- **Issue**: #100
- **Status**: `open`
- **Branch**: `feature/2026-02-24-enterprise-roadmap-issues`
- **Priority**: `critical`

## Problem

`mcp-tap.lock` ensures reproducibility, but it does not yet provide cryptographic trust on
artifact provenance by default. Enterprise environments need verifiable supply chain guarantees.

## Context

- Current lockfile capabilities:
  - canonical server identity
  - drift detection and restore
- Missing capabilities:
  - lockfile signature verification
  - attestation/provenance verification before restore/configure in strict mode
- Context7 references considered:
  - in-toto verification CLI/API practices for signed metadata validation.

## Root Cause

Integrity and provenance are not enforced as first-class constraints in install/restore flows.
There is no strict policy boundary to block untrusted artifact state.

## Solution

Add signing and verification pipeline for lockfiles and release attestations.

### Phase 1 (MVP)

1. Lockfile signature block schema:
   - signer id, algorithm, timestamp, signature value.
2. Local verification command and strict mode integration.
3. Strict enforcement path in `configure_server` and `restore`.
4. Machine-readable verification report output.

### Phase 2

- Policy enforcement integration (enforce signed-only for selected scopes).
- Provenance trust store and key rotation workflow.

## Files Changed

- `docs/issues/2026-02-24_100_supply-chain-attestation.md` — tracking spec for implementation

## Verification

- [ ] Tests pass: `uv run pytest tests/ -q`
- [ ] Linter passes: `uv run ruff check src/ tests/`
- [ ] Tampered lockfile signatures are detected and blocked in strict mode
- [ ] Missing/invalid provenance blocks strict-mode restore/configure
- [ ] Verification report includes signer, claims checked, and failure reason
- [ ] Backward compatibility: non-strict mode behavior preserved

## Lessons Learned

(Complete after implementation)
