# Plugin SDK For Enterprise Extension Points

- **Date**: 2026-02-24
- **Issue**: #102
- **Status**: `open`
- **Branch**: `feature/2026-02-24-enterprise-roadmap-issues`
- **Priority**: `low`

## Problem

An SDK could let third parties extend mcp-tap without forking.

## Context

- There is currently no validated external plugin ecosystem.
- Existing architecture already has extension seams via ports/adapters.
- A public SDK adds compatibility burden (versioning, support policy, stability guarantees).

## Root Cause

SDK scope was proposed before real integration demand existed.

## Solution

Decision on 2026-02-24: **deferred to icebox**.

Reopen criteria:
1. At least one external integrator request with concrete use case.
2. Stable extension contract proposal with backward compatibility policy.
3. Proof that adapter-level extension is insufficient.

## Files Changed

- `docs/issues/2026-02-24_102_plugin-sdk-extension-points.md` — re-scoped as icebox.

## Verification

- [x] Deferred decision documented.
- [x] Reopen criteria documented.

## Lessons Learned

Avoid long-term API surface commitments before user pull.
