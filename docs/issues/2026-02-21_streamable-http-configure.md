# Streamable-HTTP server support in configure_server

- **Date**: 2026-02-21
- **Status**: `in_progress`
- **Branch**: `feature/2026-02-21-streamable-http-support`
- **Priority**: `high`

## Problem

`configure_server` assumes every server is a local process (npm/pip/docker). When a user tries
to install a streamable-HTTP server (e.g. `https://mcp.vercel.com`), the tool attempts to
`npm install` the URL, which fails immediately. The user gets an error with no path forward.

Streamable-HTTP servers are remote — they need no local install. The correct config is:
```json
{ "command": "npx", "args": ["-y", "mcp-remote", "https://mcp.vercel.com"] }
```
via the `mcp-remote` npm bridge, which works in all MCP clients (stdio wrapper around HTTP).

## Context

- Affected layer: `tools/configure.py` (application layer)
- Discovered via: real test with Vercel MCP (`transport: "streamable-http"`, `package_identifier:
  "https://mcp.vercel.com"`) returned by `search_servers`
- The user should NOT need to know any of this — just say "instala o Vercel MCP" and it works

## Root Cause

`configure_server` has a single code path: install package → validate spawn → write stdio config.
No detection of HTTP transport. The `package_identifier` for HTTP servers is a URL, not a package name.

## Solution

Auto-detect HTTP transport from `package_identifier` (starts with `https://` or `http://`).
When detected:
1. **Skip install** — no package to install
2. **Build `mcp-remote` command** — `npx -y mcp-remote <url>` as the `ServerConfig`
3. **Validate normally** — the connection tester spawns `mcp-remote` and connects to the remote
4. **Write normal stdio config** — same format, zero changes to `config/writer.py` or `models.py`

This keeps the blast radius minimal and fully transparent to the user.

## Files Changed

- `src/mcp_tap/tools/configure.py` — add `_is_http_transport()` + HTTP fast-path before install
- `tests/test_configure_http.py` — new test file for HTTP transport path

## Verification

- [ ] `pytest tests/` — all tests pass
- [ ] `ruff check src/ tests/ && ruff format --check src/ tests/` — clean
- [ ] `configure_server("vercel", "https://mcp.vercel.com", registry_type="npm")` → installs via mcp-remote
- [ ] `configure_server("vercel", "https://mcp.vercel.com", registry_type="streamable-http")` → same
- [ ] Normal npm server → unchanged behavior
