# Native HTTP server config support (streamable-http, SSE)

- **Date**: 2026-02-21
- **Status**: `in_progress`
- **Branch**: `feature/2026-02-21-streamable-http-support`
- **Priority**: `high`

## Problem

`configure_server` for HTTP transport servers (e.g. `https://mcp.vercel.com`) currently uses
`mcp-remote` as a bridge, but:
1. The running server may be a cached older version that doesn't include this fix
2. Claude Code supports native HTTP config: `{"type": "http", "url": "..."}` — no mcp-remote needed
3. Servers with OAuth (Vercel, Figma) timeout/401 before any validation can happen
4. Reachability failures should NEVER block config from being written

## Root Cause

Single code path for all transports. No concept of client capability (does it support HTTP natively?).
No HTTP-specific validation. mcp-remote is unreliable for OAuth-gated servers.

## Solution

- `HttpServerConfig` dataclass (native `{"type":"http","url":"..."}` format)
- Client capability detection: Claude Code → native; others → mcp-remote fallback
- `HttpReachabilityChecker`: HEAD/GET check, 401=reachable (OAuth), never blocks write
- `configure_server` HTTP path: detect → capability → write native config → HTTP check → clear message
- `list_installed` + `check_health` aware of HTTP servers
- All scenarios pre-anticipated: OAuth, unreachable, SSE, multi-client

## Files Changed

- `src/mcp_tap/models.py`
- `src/mcp_tap/config/reader.py`
- `src/mcp_tap/config/detection.py`
- `src/mcp_tap/config/writer.py`
- `src/mcp_tap/connection/base.py`
- `src/mcp_tap/connection/tester.py`
- `src/mcp_tap/server.py`
- `src/mcp_tap/tools/configure.py`
- `src/mcp_tap/tools/list.py`
- `src/mcp_tap/tools/health.py`
- `src/mcp_tap/lockfile/writer.py`

## Verification

- [ ] `pytest tests/` — all tests pass
- [ ] `ruff check src/ tests/ && ruff format --check src/ tests/` — clean
- [ ] Claude Code + Vercel MCP URL → native `{"type":"http","url":"..."}` written to config
- [ ] Cursor + URL → mcp-remote fallback
- [ ] 401 response → success=True (reachable), validation_passed=True
- [ ] Unreachable server → success=True (config written), validation_passed=False, message mentions OAuth + restart
- [ ] `list_installed` shows `url` instead of `command` for HTTP servers
- [ ] `check_health` uses reachability check for HTTP servers
