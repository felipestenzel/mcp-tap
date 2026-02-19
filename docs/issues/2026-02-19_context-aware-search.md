# Context-Aware Search — Project-Informed Results

- **Date**: 2026-02-19
- **Status**: `open`
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

(Fill after implementation)

## Files Changed

(Fill after implementation)

## Verification

- [ ] Tests pass: `pytest tests/`
- [ ] Linter passes: `ruff check src/ tests/`
- [ ] Searching "database" with a Python+Postgres project ranks postgres-mcp first
- [ ] Backward compatible: search without project_path works as before
