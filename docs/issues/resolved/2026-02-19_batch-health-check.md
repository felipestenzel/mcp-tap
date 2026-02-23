# Batch Health Check Tool (check_health)

- **Date**: 2026-02-19
- **Status**: `done`
- **Branch**: `feature/2026-02-19-health-check`
- **Priority**: `high`
- **Issue**: #4

## Problem

Users can only test one server at a time with `test_connection`. There is no "What's broken?" overview. The creative brief promises: `"Check my MCP servers."` → health report for ALL installed servers.

## Context

- `test_connection` already spawns a server and probes it via MCP protocol — works for single servers
- Need a new tool that runs health checks on ALL configured servers concurrently
- This is also a prerequisite for future self-healing (need to know what's broken first)
- Should use `asyncio.gather` for concurrent checks

## Scope

1. **New tool** (`tools/health.py`):
   - Parameter: `client` (optional, auto-detect if not specified)
   - Reads all configured servers from client config
   - Runs `test_server_connection()` on each concurrently (`asyncio.gather`)
   - Returns summary: server name, status (healthy/unhealthy/timeout), tool count, error message
   - Add `HealthReport` and `ServerHealth` models to `models.py`

2. **Register in `server.py`**:
   - `readOnlyHint=True`
   - Docstring: "Check the health of all installed MCP servers"

3. **New models**:
   - `ServerHealth(name, status, tools_count, error)`
   - `HealthReport(client, total, healthy, unhealthy, servers)`

4. **Tests**:
   - Mock multiple server configs
   - Test mixed results (some healthy, some failing)
   - Test empty config (no servers)

## Root Cause

N/A — greenfield feature

## Solution

Implemented `check_health` tool in `tools/health.py` that:
1. Detects the MCP client (or accepts explicit `client` parameter)
2. Reads all configured servers from the client config
3. Runs `test_server_connection()` on each server concurrently via `asyncio.gather`
4. Returns a `HealthReport` dict with total/healthy/unhealthy counts and per-server details
5. Classifies server status as "healthy", "unhealthy", or "timeout" based on connection test result
6. Handles edge cases: no client detected, no servers configured, timeout clamping (5-60s)

Added `ServerHealth` and `HealthReport` frozen dataclasses to `models.py`.

## Files Changed

- `src/mcp_tap/models.py` — Added `ServerHealth` and `HealthReport` dataclasses
- `src/mcp_tap/tools/health.py` — New file: `check_health`, `_check_all_servers`, `_check_single_server`
- `src/mcp_tap/server.py` — Imported and registered `check_health` with `readOnlyHint=True`
- `tests/test_tools_health.py` — New file: 19 tests covering all paths

## Verification

- [x] Tests pass: `pytest tests/` (234 passed)
- [x] Linter passes: `ruff check src/ tests/`
- [x] Tool registered in `server.py` with `readOnlyHint=True`
- [x] Concurrent execution via `asyncio.gather` with `return_exceptions=True`
