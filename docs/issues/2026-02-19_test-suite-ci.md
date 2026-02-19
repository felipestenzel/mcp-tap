# Test Suite Hardening + CI Pipeline

- **Date**: 2026-02-19
- **Status**: `open`
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

(Fill after implementation)

## Files Changed

(Fill after implementation)

## Verification

- [ ] `pytest tests/` passes with >80% coverage on new code
- [ ] `ruff check src/ tests/` clean
- [ ] GitHub Actions CI green on main
- [ ] All 5+ tools have at least happy-path + error-path tests
