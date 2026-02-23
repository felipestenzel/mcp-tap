# Multi-Client Config Support + Project-Scoped Configs

- **Date**: 2026-02-19
- **Status**: `done`
- **Branch**: `feature/2026-02-19-multi-client`
- **Priority**: `medium`
- **Issue**: #7

## Problem

`configure_server` only writes to one client at a time. Power users have Claude Desktop AND Cursor AND Windsurf. Also, project-scoped configs (`.cursor/mcp.json` in the project dir) are not supported — only user-scoped global configs.

## Context

- `config/detection.py` already detects all installed clients
- `configure_server` just needs to loop over detected clients or accept a list
- Project-scoped configs are how teams share MCP setups
- Relevant to Tier 2 dotfiles story

## Scope

1. **Update `tools/configure.py`**:
   - Accept `clients` parameter (list or "all")
   - When "all", configure all detected clients
   - Report per-client status in result

2. **Update `tools/remove.py`**:
   - Same multi-client support

3. **Project-scoped config paths**:
   - `.cursor/mcp.json` (Cursor project config)
   - `.mcp.json` (Claude Code project config)
   - `.windsurf/mcp_config.json` (Windsurf project config)
   - Add `scope` parameter: "user" (global) or "project" (cwd)

4. **Tests**:
   - Multi-client configure + remove
   - Project-scoped vs user-scoped paths

## Solution

### config/detection.py
- Added `_PROJECT_CONFIGS` dict mapping clients → project-relative config paths
- Added `resolve_config_locations(clients, scope, project_path)` — resolves one, many, or "all" clients for either user or project scope
- Extended `resolve_config_path()` with `scope` and `project_path` keyword args
- Added private helpers: `_resolve_project_config`, `_all_user_configs`, `_all_project_configs`
- Claude Desktop correctly excluded from project-scoped configs (not supported)

### tools/configure.py
- Renamed `client` → `clients` param (comma-separated, "all", or empty for auto-detect)
- Added `scope` and `project_path` params
- Package install runs once, then config is written to each target client
- Single client returns standard `ConfigureResult`; multi-client adds `per_client_results` list
- Extracted `_configure_single`, `_configure_multi`, `_validate` helper functions

### tools/remove.py
- Same `clients`, `scope`, `project_path` params
- Uses `resolve_config_locations` for client resolution
- Multi-client returns `per_client_results` with per-client removal status
- Correctly reports "not found in any" when server isn't in any config

### Tests (18 new)
- `test_detection.py` — 11 tests for `resolve_config_path` project scope + `resolve_config_locations`
- Updated `test_tools_configure.py` — added 3 multi-client + 1 project-scope tests
- Updated `test_tools_remove.py` — added 4 multi-client + 1 project-scope tests

## Files Changed

- `src/mcp_tap/config/detection.py` — Multi-client + project-scoped resolution
- `src/mcp_tap/tools/configure.py` — Multi-client configure
- `src/mcp_tap/tools/remove.py` — Multi-client remove
- `tests/test_detection.py` — NEW (11 tests)
- `tests/test_tools_configure.py` — Rewritten for new API (added multi-client + project scope)
- `tests/test_tools_remove.py` — Rewritten for new API (added multi-client + project scope)

## Verification

- [x] Tests pass: `pytest tests/` — 320 passed
- [x] Linter passes: `ruff check src/ tests/`
- [x] Configure writes to multiple clients in one call
- [x] Project-scoped configs work for Cursor, Claude Code, and Windsurf
