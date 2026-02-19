# Test Suite Hardening + CI Pipeline

- **Date**: 2026-02-19
- **Status**: `done`
- **Branch**: `feature/2026-02-19-test-suite-ci`
- **Priority**: `high`
- **Issue**: #6

## Problem

Current test coverage is limited to models, config read/write, and registry parsing (20 tests). No tests for: any of the 5+ tools, installers, connection tester, scanner. No CI pipeline — regressions can ship silently.

## Context

- After Issues #1-5, the codebase will have 7+ tools and multiple modules
- Need to lock down quality before launch
- CI is a launch prerequisite — repos without green badges look abandoned
- Use `test-architect` agent for test generation

## Scope

### Tests to Add

1. **Tool tests** (`tests/test_tools/`):
   - `test_search.py` — mock registry, verify result structure
   - `test_configure.py` — mock installer + tester + filesystem, verify full flow
   - `test_scan.py` — mock filesystem with fixture projects
   - `test_health.py` — mock multiple server configs
   - `test_list.py` — mock config reader, verify secret masking
   - `test_remove.py` — mock config reader/writer

2. **Scanner tests** (`tests/test_scanner.py`):
   - Fixture directories with sample `package.json`, `pyproject.toml`, `docker-compose.yml`, `.env`
   - Test each file parser individually
   - Test recommendation mapping

3. **Installer tests** (`tests/test_installers.py`):
   - Mock subprocess calls
   - Test npm/pip/docker install + uninstall
   - Test resolver picks correct installer

4. **Connection tests** (`tests/test_connection.py`):
   - Mock MCP client session
   - Test success path (tools returned)
   - Test timeout and error paths

### CI Pipeline

5. **GitHub Actions** (`.github/workflows/ci.yml`):
   - Trigger: push to main, PRs
   - Matrix: Python 3.11, 3.12, 3.13
   - Steps: install deps → ruff check → ruff format --check → pytest
   - Badge in README

### Fixtures

6. **`tests/fixtures/`** directory:
   - `sample_project/` — mixed project with package.json, pyproject.toml, docker-compose.yml, .env
   - `sample_configs/` — client config files for testing read/write

## Root Cause

Tests were only written for the foundation layer during initial development.

## Solution

Added 62 new tests across 5 new test files covering all previously untested modules:

- **test_tools_list.py** (13 tests): `_mask_env` secret masking (5 tests) + `list_installed` tool (8 tests) covering explicit client, auto-detect, no client, empty config, secrets masking, multiple servers, and error paths.
- **test_tools_remove.py** (8 tests): Successful removal (explicit + auto-detect), no client, server not found, error paths, config file in result, restart message.
- **test_tools_test.py** (8 tests): Happy path (explicit + auto-detect), no client, server not found, connection failure, timeout clamping (min/max), error paths.
- **test_installers.py** (28 tests): NpmInstaller (7), PipInstaller (9), DockerInstaller (5), resolve_installer (6) — covering is_available, install/uninstall, build_server_command, version handling, and resolver error paths.
- **test_connection.py** (5 tests): Happy path with mocked MCP session, timeout error, command not found, generic exception, empty env→None.

Also:
- Created `.github/workflows/ci.yml` with lint job + test matrix (Python 3.11/3.12/3.13) using uv.
- Added `[dependency-groups] dev` to pyproject.toml for CI reproducibility.
- Ran `ruff format` on 19 previously unformatted files.
- Added CI badge to README.md.

Total test suite: **302 tests** (240 existing + 62 new).

## Files Changed

- `tests/test_tools_list.py` — NEW (13 tests)
- `tests/test_tools_remove.py` — NEW (8 tests)
- `tests/test_tools_test.py` — NEW (8 tests)
- `tests/test_installers.py` — NEW (28 tests)
- `tests/test_connection.py` — NEW (5 tests)
- `.github/workflows/ci.yml` — NEW (CI pipeline)
- `pyproject.toml` — Added `[dependency-groups]` dev section
- `uv.lock` — Regenerated with dev deps
- `README.md` — Added CI badge
- `docs/issues/2026-02-19_scan-project-tool.md` — Status → done
- `docs/issues/2026-02-19_e2e-install-flow.md` — Status → done
- 19 files reformatted by `ruff format`

## Verification

- [x] `pytest tests/` passes — 302 tests in 0.45s
- [x] `ruff check src/ tests/` clean
- [x] `ruff format --check src/ tests/` clean
- [x] GitHub Actions CI pipeline created
- [x] All 7 tools have happy-path + error-path tests
