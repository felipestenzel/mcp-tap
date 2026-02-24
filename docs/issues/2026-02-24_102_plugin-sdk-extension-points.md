# Plugin SDK For Enterprise Extension Points

- **Date**: 2026-02-24
- **Issue**: #102
- **Status**: `open`
- **Branch**: `feature/2026-02-24-enterprise-roadmap-issues`
- **Priority**: `high`

## Problem

Organizations need custom logic (private registries, custom scoring, compliance checks).
Today this usually requires forking core mcp-tap, which is costly and fragile.

## Context

- Core is already modular with ports/adapters.
- Missing: stable external extension API with runtime guardrails.

## Root Cause

No plugin lifecycle contract exists (versioning, discovery, loading, isolation, diagnostics).

## Solution

Add plugin SDK with strict compatibility and failure isolation.

### Phase 1 (MVP)

1. Define plugin API contracts v1:
   - source providers
   - ranking enrichers
   - policy hooks
2. Implement plugin loader + compatibility validator.
3. Add runtime isolation guardrails:
   - timeout limits
   - exception containment
   - fallback to core behavior.
4. Expose plugin diagnostics for supportability.

### Phase 2

- Signed plugin manifests.
- Policy-governed plugin allowlist.

## Files Changed

- `docs/issues/2026-02-24_102_plugin-sdk-extension-points.md` — tracking spec for implementation

## Verification

- [ ] Tests pass: `uv run pytest tests/ -q`
- [ ] Linter passes: `uv run ruff check src/ tests/`
- [ ] Plugin API contracts are versioned and documented
- [ ] Incompatible plugin versions are rejected with clear errors
- [ ] Plugin failures do not break core tool execution
- [ ] Reference plugins prove end-to-end extension paths

## Lessons Learned

(Complete after implementation)
