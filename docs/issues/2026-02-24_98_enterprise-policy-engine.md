# Enterprise Policy Engine (Allow/Deny/Audit)

- **Date**: 2026-02-24
- **Issue**: #98
- **Status**: `open`
- **Branch**: `feature/2026-02-24-enterprise-roadmap-issues`
- **Priority**: `low`

## Problem

There is no policy-as-code layer to allow/deny operations by client/server/scope.

## Context

- Current controls are package-risk oriented (`security/gate.py`), not organization policy.
- mcp-tap has no confirmed enterprise tenant requiring this right now.
- Immediate product bottleneck is adoption/distribution, not org governance.

## Root Cause

This was designed for a future enterprise persona before validated demand.

## Solution

Decision on 2026-02-24: **deferred to icebox** until there is explicit demand from real users.

Exit criteria to reopen:
1. At least one team with multi-project governance requirement.
2. Concrete allow/deny policy examples from users.
3. Clear scope that can ship as a local-first MVP (file policy only).

## Files Changed

- `docs/issues/2026-02-24_98_enterprise-policy-engine.md` — scope reduced and moved to icebox.

## Verification

- [x] Deferred decision documented.
- [x] Reopen criteria documented.

## Lessons Learned

Validate persona demand before building governance infrastructure.
