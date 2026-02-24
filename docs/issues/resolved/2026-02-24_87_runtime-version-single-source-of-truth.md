# Runtime Version: Single Source of Truth

- **Date**: 2026-02-24
- **Issue**: #87
- **Status**: `done`
- **Branch**: `fix/2026-02-24-runtime-version-source-of-truth`
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

Implemented single-source runtime version resolution:

1. `src/mcp_tap/__init__.py` now resolves version from installed distribution metadata:
   - `importlib.metadata.version("mcp-tap")`
2. Added deterministic fallback when distribution metadata is unavailable:
   - `_LOCAL_VERSION_FALLBACK = "0.0.0+local"`
3. Removed hardcoded legacy runtime version (`0.1.0`).
4. Updated release smoke test to validate against installed distribution metadata.
5. Added dedicated version tests for both installed and fallback code paths.

## Files Changed

- `src/mcp_tap/__init__.py` — dynamic runtime version resolution
- `tests/smoke_test.py` — align version assertion with packaging reality
- `tests/test_version.py` — fallback/install-path coverage
- `docs/issues/2026-02-24_87_runtime-version-single-source-of-truth.md` — issue tracking

## Verification

- [x] Tests pass: `pytest tests/`
- [x] Linter passes: `ruff check src/ tests/`
- [x] `mcp_tap.__version__` matches installed distribution version
- [x] Local source execution fallback documented and tested

Validation executed:
- `uv run ruff check src/ tests/` -> `All checks passed!`
- `uv run ruff format --check src/ tests/` -> `120 files already formatted`
- `uv run pytest tests/test_version.py -q` -> `2 passed`
- `uv run pytest tests/ -q` -> `1273 passed`
- `uv run python tests/smoke_test.py` -> `mcp-tap 0.6.6 smoke test passed`

## Lessons Learned

(Complete after delivery)

## References

- Python `importlib.metadata`:
  - https://docs.python.org/3/library/importlib.metadata.html
- Python packaging metadata:
  - https://packaging.python.org/en/latest/specifications/core-metadata/
