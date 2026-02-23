# I3 — Conversational Stacks (.mcp-tap.yaml)

- **Date**: 2026-02-19
- **Status**: `done`
- **Branch**: `feature/2026-02-19-conversational-stacks`
- **Priority**: `high`

## Problem

No way to share or reproduce MCP server setups. Users must manually configure
each server one by one. Competitor mcp-compose does manual composition —
mcp-tap should do it intelligently and conversationally.

## Context

- Roadmap item I3 in `docs/issues/2026-02-19_premium-quality-roadmap.md`
- Impact: 8/10 | Effort: M
- Creates network effects (shareable stacks = UGC flywheel)

## Solution

YAML-based stack format + `apply_stack` tool + 3 built-in stacks.

## Files Changed

- `src/mcp_tap/stacks/loader.py` — parser e carregamento de stacks
- `src/mcp_tap/tools/stack.py` — `apply_stack`
- `src/mcp_tap/stacks/presets/*.yaml` — stacks built-in
- `tests/test_stacks.py` — cobertura de parsing e aplicação

## Verification

- [x] Tests pass: `pytest tests/`
- [x] Linter passes: `ruff check src/ tests/`
- [x] apply_stack installs from built-in stack names
- [x] apply_stack installs from custom YAML file path
- [x] 3 built-in stacks: data-science, web-dev, devops
