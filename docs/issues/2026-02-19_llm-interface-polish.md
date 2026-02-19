# LLM Interface Polish — Tool Descriptions + Server Instructions

- **Date**: 2026-02-19
- **Status**: `open`
- **Branch**: `feature/2026-02-19-llm-polish`
- **Priority**: `medium`
- **Issue**: #8

## Problem

The `server.py` instructions field is a single generic sentence. Tool docstrings are minimal. The LLM is the user's interface — if descriptions are bad, the LLM will call tools wrong, pass bad arguments, or miss the recommended workflow (scan → search → configure → test).

## Context

- The LLM reads `instructions` and tool descriptions to decide how to use mcp-tap
- Good instructions dramatically improve UX without changing any logic
- Should guide the LLM to: start with scan_project, then recommend, then configure
- Error messages must be clear and actionable for LLM consumption

## Scope

1. **Update `server.py` instructions**:
   - Describe the recommended workflow: scan → configure → health check
   - Explain when to use each tool
   - Hint at self-healing behavior (retry on failure)

2. **Audit every tool docstring**:
   - Each tool function must have a clear, LLM-friendly docstring
   - Describe parameters with types and defaults
   - Describe what the tool returns
   - Include usage examples in natural language

3. **Audit error messages**:
   - Every error in `errors.py` should be actionable
   - Format: "What happened. What to do about it."
   - No stack traces, no internal jargon

4. **Tool parameter descriptions**:
   - Add `description` to FastMCP tool parameters where supported
   - Clear explanation of optional vs required params

## Root Cause

Initial implementation focused on functionality, not LLM UX.

## Solution

(Fill after implementation)

## Files Changed

(Fill after implementation)

## Verification

- [ ] Linter passes: `ruff check src/ tests/`
- [ ] Every tool has a multi-line docstring with workflow context
- [ ] `server.py` instructions describe the scan → configure → health workflow
- [ ] Manual test: an LLM correctly follows the recommended workflow
