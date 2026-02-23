# HTTP config per-client: native config for capable clients, mcp-remote for the rest

- **Date**: 2026-02-23
- **Status**: `done`
- **Branch**: `feature/2026-02-23-http-config-per-client`
- **Priority**: `high`

## Problem

When `configure_server` is called for an HTTP transport server with multiple clients
(e.g. `clients="claude_code,cursor"`), the config format is chosen by
`_all_locations_support_http_native()` — if **any** client does not support native HTTP,
**all** clients fall back to `mcp-remote`. Claude Code, which supports native HTTP config
(`{"type":"http","url":"..."}`), unnecessarily gets the heavier mcp-remote bridge.

## Context

- Affected layer: `tools/configure.py` — `_build_http_server_config`, `_configure_http_multi`
- Discovered during architecture review of v0.6.0/v0.6.1 HTTP native config feature
- The capability registry (`HTTP_NATIVE_CLIENTS = frozenset({MCPClient.CLAUDE_CODE})`) already
  tracks which clients support native HTTP, but the multi-client write path ignores per-client
  capability

Current behavior (`configure.py:500-505`):
```python
def _build_http_server_config(url, env, locations, registry_type):
    if _all_locations_support_http_native(locations):   # all-or-nothing
        return HttpServerConfig(url=url, ...)
    return ServerConfig(command="npx", args=("-y", "mcp-remote", url), ...)
```

Expected behavior: each client receives the best config it can handle.

## Root Cause

`_build_http_server_config` returns a **single** config object reused for all clients.
`_configure_http_multi` writes that same object to every target. The architecture must be
changed to allow per-location config selection.

## Solution

Replaced the all-or-nothing `_build_http_server_config(locations)` with
`_build_http_server_config_for_location(location)` which decides the format per client.
`_configure_http_single` and `_configure_http_multi` now call the per-location builder
internally. `_configure_http_multi` writes distinct configs per client and exposes
`config_written` in each `per_client_results` entry. The security gate in the HTTP path
now always passes `command=""` (URL is the security surface, not the mcp-remote command).
`_all_locations_support_http_native` removed (no longer needed).

High-level approach:
- Remove `_build_http_server_config` (single shared config)
- Add `_build_http_server_config_for_location(url, env, location, registry_type)` — returns
  the best config for a given `ConfigLocation`
- Update `_configure_http_multi` to call the per-location builder and write distinct configs
- `_configure_http_single` already receives a single location; pass it through the same
  per-location builder for consistency
- `per_client_results` in the response should include the `config_written` for each client
  so the caller can see which format was applied

## Files Changed

- `src/mcp_tap/tools/configure.py` — refactor HTTP config builder + multi-client write loop

## Verification

- [x] Tests pass: `pytest tests/` → 1232 passed
- [x] Linter passes: `ruff check src/ tests/ && ruff format --check src/ tests/`
- [x] `clients="claude_code,cursor"` → Claude Code gets `{"type":"http","url":"..."}`,
      Cursor gets `{"command":"npx","args":["-y","mcp-remote","<url>"]}` (new test covers this)
- [x] `clients="claude_code"` only → still native (no regression)
- [x] `clients="cursor"` only → still mcp-remote (no regression)
- [x] `clients="claude_desktop,windsurf"` → both get mcp-remote (no regression)

## Lessons Learned

(Optional)
