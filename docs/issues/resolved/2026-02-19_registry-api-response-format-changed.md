# Registry API response format changed — search_servers returns empty

- **Date**: 2026-02-19
- **Status**: `done`
- **Branch**: `fix/2026-02-19-registry-api-response-format`
- **Priority**: `critical`

## Problem

`search_servers` returns empty results for all queries. The MCP Registry API
(`https://registry.modelcontextprotocol.io/v0.1`) changed its response format
and our client is no longer parsing it correctly.

The API works fine when accessed directly via HTTP — the bug is in our parser.

## Context

- **Module**: `src/mcp_tap/registry/client.py`
- **Discovered by**: Manual testing of v0.2.4

Three breaking changes in the API response:

### 1. Server data wrapper
Each item in `servers[]` is now `{"server": {...}, "_meta": {...}}` instead of
the server fields being at the top level. Our `_parse_server` receives the
wrapper and gets empty strings for all `.get()` calls.

### 2. `_meta` restructured
Was: `{"isOfficial": true, "updatedAt": "..."}`
Now: `{"io.modelcontextprotocol.registry/official": {"status": "active", "publishedAt": "...", "updatedAt": "...", "isLatest": true}}`

### 3. `remotes` replaces `packages` for some servers
Some servers now use `remotes` (with `type`, `url`, `headers`) instead of
`packages` (with `registryType`, `identifier`, `environmentVariables`).
Both formats coexist in the current API.

### 4. `get_server` endpoint changed
Old: `GET /servers/{name}` → no longer exists (404)
New: `GET /servers/{name}/versions/{version}` (name must be URL-encoded)

## Root Cause

API schema evolved (likely schema version `2025-09-29` based on `$schema` field
in responses). Our client was written against the previous format.

## Solution

Updated `RegistryClient` to handle all 4 API changes:

1. **Wrapper**: Added `_parse_entry()` that unwraps `{"server": {...}, "_meta": {...}}`
   before passing to `_parse_server()`. Falls back to flat format for backward compat.
2. **`_meta`**: Added `_extract_is_official()` and `_extract_updated_at()` that handle
   both the new namespaced format (`io.modelcontextprotocol.registry/official`) and the
   legacy flat format.
3. **`remotes`**: Added `_parse_remotes()` that converts `remotes` entries to `PackageInfo`
   objects. `packages` takes precedence when both are present.
4. **`get_server`**: Changed endpoint to `/servers/{name}/versions/latest` with proper
   URL-encoding via `urllib.parse.quote`.
5. **`transport` field**: Added `_parse_transport()` to handle both string (`"stdio"`)
   and dict (`{"type": "stdio"}`) formats.

## Files Changed

- `src/mcp_tap/registry/client.py` — Fix parser for new API response format
- `tests/test_registry.py` — Added 15 new tests covering all format variations

## Verification

- [x] Tests pass: `pytest tests/` — 498 passed
- [x] Linter passes: `ruff check src/ tests/`
- [x] `search_servers("postgres")` returns 3 results against live API
- [x] `get_server` uses correct versioned endpoint with URL-encoding

## Lessons Learned

- The MCP Registry API evolves without versioning the response schema. Our parser should
  be resilient to field format changes (string vs dict, flat vs nested).
- Always test against the live API during development — unit tests with mocked data
  can mask API drift.
