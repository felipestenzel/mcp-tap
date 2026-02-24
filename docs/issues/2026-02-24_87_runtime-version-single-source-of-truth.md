# Runtime Version: Single Source of Truth

- **Date**: 2026-02-24
- **Issue**: #87
- **Status**: `open`
- **Branch**: `feature/2026-02-24-quality-gap-issues`
- **Priority**: `high`

## Problem

Runtime version reporting is inconsistent with published package versions.

Current mismatch observed:
- `pyproject.toml` / release tags / package registries reflect current versions (e.g. 0.6.x)
- `src/mcp_tap/__init__.py` still hardcodes `__version__ = "0.1.0"`

This weakens runtime traceability and release diagnostics.

## Context

- Module affected: `src/mcp_tap/__init__.py`
- Release and publish workflows are healthy, but version introspection in runtime is stale
- Smoke tests currently tolerate this legacy mismatch and should be corrected

## Root Cause

Version metadata is maintained in release files (`pyproject.toml`, npm wrapper), but runtime
`__version__` remained hardcoded from early project stage.

## Solution

Implement single-source runtime version resolution:

1. Resolve package version through `importlib.metadata.version("mcp-tap")` when installed
2. Define deterministic fallback for local/source execution where metadata is unavailable
3. Remove hardcoded legacy constant from runtime path
4. Update smoke tests to validate runtime version behavior robustly

## Files Changed

- `src/mcp_tap/__init__.py` — dynamic runtime version resolution
- `tests/smoke_test.py` — align version assertion with packaging reality
- `tests/test_models.py` or dedicated version test module — fallback/install-path coverage
- `docs/issues/2026-02-24_87_runtime-version-single-source-of-truth.md` — issue tracking

## Verification

- [ ] Tests pass: `pytest tests/`
- [ ] Linter passes: `ruff check src/ tests/`
- [ ] `mcp_tap.__version__` matches installed distribution version
- [ ] Local source execution fallback documented and tested

## Lessons Learned

(Complete after delivery)

## References

- Python `importlib.metadata`:
  - https://docs.python.org/3/library/importlib.metadata.html
- Python packaging metadata:
  - https://packaging.python.org/en/latest/specifications/core-metadata/
