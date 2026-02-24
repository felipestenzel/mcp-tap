# scan_project MCP Tool

- **Date**: 2026-02-19
- **Status**: `done`
- **Branch**: `feature/2026-02-19-scan-project-tool`
- **Priority**: `critical`
- **Issue**: #2

## Problem

The scanner engine (Issue #1) produces a `ProjectProfile`, but there is no MCP tool exposing it to the AI assistant. The LLM needs a `scan_project` tool to trigger project analysis and get recommendations.

## Context

- Depends on Issue #1 (scanner engine)
- This is the entry point to the entire "set up my project" flow
- Without this tool registered, the demo from the creative brief cannot run
- Should be `readOnlyHint=True` (only reads filesystem, never modifies)

## Scope

1. **New tool** (`tools/scan.py`):
   - Parameter: `path` (string, defaults to current working directory)
   - Calls `scanner.detect()` to get `ProjectProfile`
   - Calls `scanner.recommend()` to get recommended servers
   - Cross-references with `list_installed` to show "already have" vs "missing"
   - Returns structured dict: detected stack, recommended servers, already installed

2. **Register in `server.py`**:
   - `readOnlyHint=True`
   - Clear docstring for LLM: "Scan a project directory to detect your tech stack and recommend MCP servers"

3. **Tests**:
   - Mock filesystem with fixture project
   - Verify recommendations match detected tech
   - Verify "already installed" filtering works

## Root Cause

N/A — greenfield feature

## Solution

(Fill after implementation)

## Files Changed

(Fill after implementation)

## Verification

- [ ] Tests pass: `pytest tests/`
- [ ] Linter passes: `ruff check src/ tests/`
- [ ] Tool is registered in `server.py` with `readOnlyHint=True`
- [ ] Running against a real project directory returns meaningful recommendations
