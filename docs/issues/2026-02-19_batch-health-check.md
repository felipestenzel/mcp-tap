# Batch Health Check Tool (check_health)

- **Date**: 2026-02-19
- **Status**: `open`
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

(Fill after implementation)

## Files Changed

(Fill after implementation)

## Verification

- [ ] Tests pass: `pytest tests/`
- [ ] Linter passes: `ruff check src/ tests/`
- [ ] Tool registered in `server.py` with `readOnlyHint=True`
- [ ] Concurrent execution (not sequential) verified
