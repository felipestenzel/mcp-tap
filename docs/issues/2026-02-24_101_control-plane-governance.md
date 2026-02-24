# Optional Control Plane For Governance And Fleet Visibility

- **Date**: 2026-02-24
- **Issue**: #101
- **Status**: `open`
- **Branch**: `feature/2026-02-24-enterprise-roadmap-issues`
- **Priority**: `low`

## Problem

Large organizations may want centralized governance and fleet visibility.

## Context

- mcp-tap is intentionally local-first.
- A control plane requires a separate operated service (API, auth, tenancy, SLAs).
- This scope is not aligned with current product stage and adoption.

## Root Cause

This request is a separate product track, not a near-term CLI feature.

## Solution

Decision on 2026-02-24: **deferred to icebox**.

Reopen criteria:
1. Confirmed team demand for centralized management.
2. Dedicated operating model (hosting, auth, support).
3. Decision that mcp-tap should include SaaS/self-host control-plane integration.

## Files Changed

- `docs/issues/2026-02-24_101_control-plane-governance.md` — re-scoped as icebox.

## Verification

- [x] Deferred decision documented.
- [x] Reopen criteria documented.

## Lessons Learned

Separate infrastructure products from core local CLI roadmap.
