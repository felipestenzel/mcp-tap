# Context-Aware Search — Project-Informed Results

- **Date**: 2026-02-19
- **Status**: `done`
- **Branch**: `feature/2026-02-19-context-aware-search`
- **Priority**: `medium`
- **Issue**: #5

## Problem

`search_servers` returns raw registry results with no awareness of the user's project. Searching "database" returns all database MCP servers equally ranked, even if the user's project clearly uses PostgreSQL. The LLM has to do the mapping manually.

## Context

- Depends on Issue #1 (scanner engine) and Issue #2 (scan_project tool)
- Bridges the gap between "scan my project" and "install the right servers"
- With context-aware search, results are pre-sorted by relevance to the user's stack
- Also an opportunity to enhance the registry client with richer server details

## Scope

1. **Update `tools/search.py`**:
   - Add optional `project_path` parameter
   - When provided, call scanner to get `ProjectProfile`
   - Score/rank results based on technology match
   - Tag results with `relevance` (high/medium/low) and `match_reason`

2. **Scoring logic** (`scanner/scoring.py`):
   - Exact tech match (project has postgres, result is postgres-mcp) → high
   - Category match (project has a database, result is any db-mcp) → medium
   - No match → low
   - Sort: high first, then by is_official, then by updated_at

3. **Tests**:
   - Mock scanner + registry responses
   - Verify scoring puts relevant servers first
   - Verify no-project-path still works (backward compatible)

## Root Cause

search_servers was built as a pure registry passthrough with no intelligence layer.

## Solution

Added optional `project_path` parameter to `search_servers`. When provided:
1. Scans the project via `scan_project()` to get a `ProjectProfile`
2. Scores each search result against detected technologies using `score_result()`
3. Adds `relevance` ("high"/"medium"/"low") and `match_reason` fields to each result
4. Stable-sorts results by relevance (high first, original order preserved within groups)

Created `scanner/scoring.py` with the scoring logic:
- **Exact match**: technology name appears in result name or description -> "high"
- **Category match**: result description contains keywords for a detected category -> "medium"
- **No match**: -> "low"

When `project_path` is not provided, behavior is unchanged (backward compatible).

## Files Changed

- `src/mcp_tap/tools/search.py` — Added `project_path` param, `_apply_project_scoring`, `_scan_project_safe`
- `src/mcp_tap/scanner/scoring.py` — New file: `score_result`, `relevance_sort_key`
- `src/mcp_tap/server.py` — Updated instructions string to mention context-aware search
- `tests/test_scoring.py` — New file: 14 tests for scoring logic
- `tests/test_tools_search.py` — New file: 8 tests for context-aware search tool

## Verification

- [x] Tests pass: `pytest tests/` (234 passed)
- [x] Linter passes: `ruff check src/ tests/`
- [x] Searching "database" with a Python+Postgres project ranks postgres-mcp first
- [x] Backward compatible: search without project_path works as before
