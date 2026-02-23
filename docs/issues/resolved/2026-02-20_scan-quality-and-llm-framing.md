# Scan quality gap for Python-only projects + LLM framing problem

- **Date**: 2026-02-20
- **Status**: `done`
- **Branch**: `fix/2026-02-20-scan-quality-llm-framing`
- **Priority**: `high`

## Problem

When `scan_project` is run on a simple Python library/CLI project (e.g. mcp-tap itself), it
produces 0 recommendations and near-zero useful `suggested_searches`. This happens because:

1. None of the 6 stack archetypes cover "Python library / CLI tool" projects.
2. The `summary` field says "No MCP server recommendations for this stack" when `rec_count == 0`,
   causing the LLM to interpret the scan as a failure and improvise its own search queries.
3. The `self_check` instruction is too passive — it doesn't explicitly tell the LLM how to frame
   the multi-step `scan → search` workflow to the user.
4. The server-level instructions have no narrative guidance section.

Observed in a real Claude Code session: the agent made 16+ manual searches (including irrelevant
ones like "macos", "think", "raycast") and narrated them as: "O scan não gerou recomendações
automáticas. Deixa eu buscar MCPs que possam agregar valor real." — making mcp-tap look broken.

## Context

- Modules affected: `scanner/archetypes.py`, `tools/scan.py`, `server.py`
- Discovered via real-world test session with mcp-tap scanning itself
- The `scan → search → inspect` multi-step workflow IS the product, but the LLM's commentary
  exposed it as "manual compensation for a failed scan"

## Root Cause

**Structural**: No archetype covers simple Python library/CLI projects. mcp-tap detects Python
+ pytest + hatchling but triggers zero of the 6 archetypes (all require databases, cloud, or
SaaS services). Result: empty `suggested_searches`.

**Messaging**: When `rec_count == 0`, `_build_summary` emits "No MCP server recommendations for
this stack." — a dead-end message that gives the LLM no next step. The `self_check` says "check
suggested_searches" but doesn't tell the LLM how to narrate the workflow.

## Solution

1. **`scanner/archetypes.py`**: Add `python_library` archetype (Python + build backend + test
   framework → min_groups 2) with `extra_queries = ["notifications", "pypi", "documentation",
   "testing"]`.

2. **`tools/scan.py`**: Fix `_build_summary` to detect when `rec_count == 0` but
   `suggested_searches` is non-empty, emitting "Extended registry discovery recommended via N
   search queries" instead. Strengthen `self_check` with explicit narrative framing instructions.

3. **`server.py`**: Add "Narrative guidance" section to FastMCP instructions telling the LLM
   to never say "the scan found nothing" and to frame the multi-step workflow as intentional.

## Files Changed

- `src/mcp_tap/scanner/archetypes.py` — Added `python_library` archetype
- `src/mcp_tap/tools/scan.py` — Fixed `_build_summary`, strengthened `self_check`
- `src/mcp_tap/server.py` — Added narrative guidance to instructions

## Verification

- [ ] Tests pass: `pytest tests/`
- [ ] Linter passes: `ruff check src/ tests/`
- [ ] `detect_archetypes` returns `python_library` for a Python + pytest + hatchling project
- [ ] `_build_summary` with 0 recs + non-empty suggested_searches emits extended discovery text
