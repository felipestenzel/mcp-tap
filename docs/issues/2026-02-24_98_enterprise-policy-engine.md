# Enterprise Policy Engine (Allow/Deny/Audit)

- **Date**: 2026-02-24
- **Issue**: #98
- **Status**: `open`
- **Branch**: `feature/2026-02-24-enterprise-roadmap-issues`
- **Priority**: `critical`

## Problem

mcp-tap applies one global behavior for all clients and projects. There is no policy-as-code
layer to control whether a given operation is allowed, denied, or only audited.

This blocks enterprise adoption where teams need deterministic governance for:
- which MCP servers can be configured
- which operations are allowed per client/scope
- auditable decision logs for compliance and incident response

## Context

- Affected modules:
  - `src/mcp_tap/tools/configure.py`
  - `src/mcp_tap/tools/remove.py`
  - `src/mcp_tap/tools/restore.py`
  - `src/mcp_tap/tools/stack.py`
- Current security gate evaluates package risk, but not organization policy intent.
- Context7 references considered for hardening patterns:
  - OPA policy deployment + decision logging patterns.

## Root Cause

Authorization/governance concerns are not modeled as a first-class decision boundary.
Rules are implicit in tool logic instead of declarative policy evaluated per request.

## Solution

Implement a policy engine with deterministic `allow` / `deny` / `audit` outcomes.

### Phase 1 (MVP)

1. Introduce policy file format v1 (`.mcp-tap.policy.yaml`):
   - Rule id, matchers, effect, reason, precedence.
2. Add evaluator pipeline:
   - Normalize request context (operation, client, project fingerprint, server identity).
   - Evaluate rules with deterministic precedence (deny > allow > audit).
3. Integrate checks in destructive/critical operations:
   - `configure_server`, `remove_server`, `restore`, `apply_stack`.
4. Add decision logging (JSONL):
   - Include matched rule id, effect, reason code, request fingerprint.
5. Add rollout modes:
   - `audit-only`, `warn`, `enforce (fail-closed)`.

### Phase 2

- Policy bundles and signed distribution integration.
- Per-team overrides and scoped policy inheritance.

## Files Changed

- `docs/issues/2026-02-24_98_enterprise-policy-engine.md` — tracking spec for implementation

## Verification

- [ ] Tests pass: `uv run pytest tests/ -q`
- [ ] Linter passes: `uv run ruff check src/ tests/`
- [ ] Rule precedence is deterministic and covered by tests
- [ ] Denied operations are blocked with explicit, actionable errors
- [ ] Decision logs contain rule id and request fingerprint
- [ ] Fail-closed behavior verified for invalid policy in enforce mode

## Lessons Learned

(Complete after implementation)
