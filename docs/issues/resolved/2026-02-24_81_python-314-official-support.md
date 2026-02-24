# Official Python 3.14 Support (CI + Metadata)

- **Date**: 2026-02-24
- **Issue**: #81
- **Status**: `done`
- **Branch**: `feature/2026-02-24-python-314-official-support`
- **Priority**: `medium`

## Problem

Python 3.14 is already viable in local runs, but the project does not yet declare
official support consistently in package metadata and CI.

## Context

- Project metadata (`pyproject.toml`) currently lists Python 3.11, 3.12, and 3.13 classifiers.
- CI matrix currently runs tests on Python 3.11, 3.12, and 3.13 only.
- Local validation already showed full test suite passing on Python 3.14.

## Root Cause

Official support hardening was not completed after runtime validation.
Compatibility exists in practice but is not fully codified in release/CI signals.

## Solution

Implemented official Python 3.14 support declarations without changing runtime behavior:

1. Added Python 3.14 classifier in `pyproject.toml`.
2. Extended CI matrix to run tests on Python 3.14 in `.github/workflows/ci.yml`.
3. Updated README requirements section to explicitly state official CI coverage for Python
   3.11/3.12/3.13/3.14.

## Files Changed

- `pyproject.toml` — added `Programming Language :: Python :: 3.14` classifier
- `.github/workflows/ci.yml` — added Python `3.14` to test matrix
- `README.md` — documented official CI-tested Python versions
- `docs/issues/2026-02-24_81_python-314-official-support.md` — issue tracking doc

## Verification

- [x] Tests pass: `pytest tests/`
- [x] Linter passes: `ruff check src/ tests/`
- [x] CI matrix includes Python 3.14 and runs green
- [x] Package metadata includes Python 3.14 classifier

Validation executed:
- `uv run ruff check src/ tests/` -> `All checks passed!`
- `uv run ruff format --check src/ tests/` -> `119 files already formatted`
- `uv run pytest tests/ -q` -> `1268 passed`
- `uv run --python 3.11 pytest tests/ -q` -> `1268 passed`

## Lessons Learned

(Optional)
