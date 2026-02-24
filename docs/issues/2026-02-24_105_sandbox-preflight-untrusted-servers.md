# Sandbox Preflight For Untrusted MCP Servers

- **Date**: 2026-02-24
- **Issue**: #105
- **Status**: `open`
- **Branch**: `feature/2026-02-24-enterprise-roadmap-issues`
- **Priority**: `critical`

## Problem

Security gate reduces obvious risk, but unknown packages can still be executed directly during
connection validation. High-assurance environments need constrained preflight execution.

## Context

- Existing controls:
  - security gate signal checks
  - install/validation safeguards
- Missing:
  - runtime sandbox boundary before config write for low-trust candidates
  - explicit risk classification report from constrained execution

## Root Cause

Trust classification is currently static at install metadata level; runtime behavior under constraints
is not validated as a separate security gate.

## Solution

Add sandbox preflight execution path for untrusted/low-confidence candidates.

### Phase 1 (MVP)

1. Trust level classifier for candidate servers.
2. Sandbox runner abstraction with resource/time constraints.
3. Preflight result evaluator (`pass`, `warn`, `block`).
4. Integrate preflight before final config write in `configure_server`.
5. Emit machine-readable preflight report.

### Phase 2

- Policy-based routing to sandbox strictness profiles.
- Cross-platform backend strategy hardening.

## Files Changed

- `docs/issues/2026-02-24_105_sandbox-preflight-untrusted-servers.md` — tracking spec for implementation

## Verification

- [ ] Tests pass: `uv run pytest tests/ -q`
- [ ] Linter passes: `uv run ruff check src/ tests/`
- [ ] Low-trust candidates are routed to sandbox path automatically
- [ ] Strict mode blocks configure when sandbox preflight fails
- [ ] Backend-unavailable fallback is explicit and policy-controlled
- [ ] Reports include constraints, observed behavior, and final decision

## Lessons Learned

(Complete after implementation)
