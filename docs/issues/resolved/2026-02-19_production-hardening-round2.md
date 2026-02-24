# Production Hardening Round 2 — HIGH + MEDIUM bugs

- **Date**: 2026-02-19
- **Status**: `done`
- **Branch**: `fix/2026-02-19-production-hardening-r2`
- **Priority**: `high`

## Problem

7 bugs pendentes do roadmap (3 HIGH + 4 MEDIUM) que afetam resiliência e qualidade de produção:

### HIGH
- **H2**: Healing loop spawna até 7 processos por servidor (`tools/configure.py`)
- **H3**: configure_server não é transacional — config escrito mesmo se validação falha
- **H4**: Connection tester cleanup incerto no timeout (`connection/tester.py`)

### MEDIUM
- **M1**: httpx sem limites de pool em `server.py` — precisa `Limits(max_connections=10)`
- **M2**: Config reader é sync em contexto async (`config/reader.py`) — usar `asyncio.to_thread`
- **M3**: Env vars parser quebra com vírgula no valor (`tools/configure.py`)
- **M4**: Import inline em loop (`tools/search.py:151`) — mover para topo

## Context

- Bugs documentados em `docs/issues/2026-02-19_premium-quality-roadmap.md`
- Fase 0 (C1-C4, H1) já corrigidos na sessão anterior
- Esta é a segunda rodada de hardening

## Root Cause

Múltiplos — ver descrição individual de cada bug acima.

## Solution

### H2: Healing loop reduced (max 7 → max 3 processes)
- `heal_and_retry()` default `max_attempts` reduced from 3 to 2
- `_try_heal()` now accepts `original_error` parameter — no longer spawns redundant `test_server_connection` to get a fresh error
- Removed redundant post-heal `test_server_connection` in `_configure_single()` and `_configure_multi()`
- `_validate()` now returns 4-tuple including `ConnectionTestResult` for forwarding

### H3: configure_server is now transactional
- `write_server_config` moved to AFTER validation+healing succeeds
- If validation fails and healing fails: config NOT written, `success=False`
- Clear error message: "Config was NOT written to avoid a broken entry"
- Applied to both `_configure_single()` and `_configure_multi()`

### H4: Connection tester improved cleanup
- Extracted `_run_connection_test()` coroutine for better separation
- Replaced `asyncio.timeout` with `asyncio.wait_for` — sends `CancelledError` into coroutine, properly triggering `__aexit__` cleanup of spawned server process
- Added logging on timeout with process cleanup status
- Combined nested `async with` into single multi-context (ruff SIM117)

### M1: httpx pool limits
- Added `limits=httpx.Limits(max_connections=10, max_keepalive_connections=5)` to `httpx.AsyncClient()` in `app_lifespan`

### M2: Async config reader
- Added `aread_config()` async wrapper using `asyncio.to_thread(read_config, ...)`
- Sync `read_config` preserved unchanged for sync callers

### M3: Env vars parser with commas in values
- Replaced naive `env_vars.split(",")` with `re.split(r",(?=\s*[A-Za-z_][A-Za-z0-9_]*\s*=)", env_vars)`
- Splits only on commas followed by a `KEY=` pattern, preserving commas in values

### M4: Imports moved to top level
- Moved `import asyncio`, `import httpx`, `RegistryType`, `ServerRecommendation` from inline to top of `tools/search.py`

## Files Changed

### Source (modified)
- `src/mcp_tap/tools/configure.py` — H2 (reduced process spawning), H3 (transactional writes), M3 (smart env parser)
- `src/mcp_tap/healing/retry.py` — H2 (max_attempts 3→2)
- `src/mcp_tap/connection/tester.py` — H4 (wait_for + extracted coroutine)
- `src/mcp_tap/server.py` — M1 (httpx pool limits)
- `src/mcp_tap/config/reader.py` — M2 (aread_config async wrapper)
- `src/mcp_tap/tools/search.py` — M4 (imports moved to top)

### Tests (new/modified)
- `tests/test_healing.py` — +4 tests (H2: max attempts, error forwarding)
- `tests/test_tools_configure.py` — +7 tests (H2: no redundant validation, H3: transactional, M3: commas), 2 existing updated for H3
- `tests/test_connection.py` — +3 tests (H4: cleanup, timeout message)
- `tests/test_server.py` — +1 test (M1: pool limits)
- `tests/test_config.py` — +2 tests (M2: aread_config)

## Verification

- [x] Tests pass: `pytest tests/` — 731 passed (714 → 731, +17 new)
- [x] Linter passes: `ruff check src/ tests/` + `ruff format --check`
- [x] H2: Healing max 2 attempts (was 3), no redundant process spawns
- [x] H3: Config NOT written if validation fails, success=False
- [x] H4: Connection tester uses wait_for for proper cancellation cleanup
- [x] M1: httpx with Limits(max_connections=10, max_keepalive_connections=5)
- [x] M2: aread_config async wrapper available
- [x] M3: Env vars with commas in values parsed correctly
- [x] M4: Imports moved to top of search.py
