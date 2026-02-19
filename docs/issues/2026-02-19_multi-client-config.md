# Multi-Client Config Support + Project-Scoped Configs

- **Date**: 2026-02-19
- **Status**: `open`
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
   - `.claude/mcp_servers.json` (Claude Code project config)
   - Add `scope` parameter: "user" (global) or "project" (cwd)
   - Default to "project" when detected, fallback to "user"

4. **Tests**:
   - Multi-client configure + remove
   - Project-scoped vs user-scoped paths

## Root Cause

Initial implementation assumed single-client usage.

## Solution

(Fill after implementation)

## Files Changed

(Fill after implementation)

## Verification

- [ ] Tests pass: `pytest tests/`
- [ ] Linter passes: `ruff check src/ tests/`
- [ ] Configure writes to multiple clients in one call
- [ ] Project-scoped configs work for Cursor and Claude Code
