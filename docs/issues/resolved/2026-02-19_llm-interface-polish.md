# LLM Interface Polish — Tool Descriptions + Server Instructions

- **Date**: 2026-02-19
- **Status**: `done`
- **Branch**: `feature/2026-02-19-llm-polish`
- **Priority**: `medium`
- **Issue**: #8

## Problem

The `server.py` instructions field is a single generic sentence. Tool docstrings are minimal. The LLM is the user's interface — if descriptions are bad, the LLM will call tools wrong, pass bad arguments, or miss the recommended workflow (scan → search → configure → test).

## Solution

### server.py instructions (complete rewrite)
- Structured with markdown headers: "Recommended workflow", "Other tools", "Tips"
- Describes the 4-step workflow: scan_project → search_servers → configure_server → check_health
- Explains when to use each tool and how they connect
- Includes troubleshooting tips (validation failures, reinstall flow)
- Lists supported clients

### Tool docstrings (all 7 tools polished)
- **scan_project**: Added "This is the best starting point" guidance, detailed return schema
- **search_servers**: Added "use configure_server with results" guidance, return schema
- **configure_server**: Added "This is the main action tool" guidance, cross-references to search_servers/scan_project for getting package_identifier, env_vars_required note
- **test_connection**: Added "use after configure_server" context, list_installed for names, timeout guidance
- **check_health**: Added "use after configure_server" context, reinstall tip for unhealthy servers
- **list_installed**: Added workflow context (use before configure/remove), secret masking note
- **remove_server**: Added restart reminder, list_installed reference, clients="all" tip

### errors.py
- Audited: already follows "What happened. What to do about it" format at call sites
- No changes needed

## Files Changed

- `src/mcp_tap/server.py` — Rewritten instructions with workflow guidance
- `src/mcp_tap/tools/scan.py` — Enhanced docstring
- `src/mcp_tap/tools/search.py` — Enhanced docstring
- `src/mcp_tap/tools/configure.py` — Enhanced docstring
- `src/mcp_tap/tools/test.py` — Enhanced docstring
- `src/mcp_tap/tools/health.py` — Enhanced docstring
- `src/mcp_tap/tools/list.py` — Enhanced docstring
- `src/mcp_tap/tools/remove.py` — Enhanced docstring

## Verification

- [x] Linter passes: `ruff check src/ tests/`
- [x] Every tool has a multi-line docstring with workflow context
- [x] `server.py` instructions describe the scan → configure → health workflow
- [x] Tests still pass: 320 tests
