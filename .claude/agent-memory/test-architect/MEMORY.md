# Test Architect Memory -- mcp-tap

## Testing Setup
- pytest + pytest-asyncio (asyncio_mode="auto")
- Test dir: `tests/`
- Run: `pytest tests/`
- Linter: `ruff check src/ tests/`
- Current: 240 tests passing (config, registry, models, scanner, scoring, tools: scan/configure/health/search)
- Mock all external I/O (httpx, subprocess, filesystem)
- Target: >80% coverage on new code

## Project Conventions
- `from __future__ import annotations` in ALL files
- All dataclasses frozen=True, slots=True
- Ruff rules: E, F, W, I, UP, B, SIM, RUF (import sorting enforced via I001)
- Unused unpacked vars must use `_` prefix (RUF059)
- Line length: 100 chars
- Python target: 3.11+
- IMPORTANT: VS Code linter auto-removes unused imports between Edit calls. When adding imports + new code, use Write to replace the entire file atomically -- do NOT do two separate edits (import then code)

## Test Patterns Established
- Test classes grouped by component (e.g., TestParsePackageJson, TestScanFullPythonProject)
- Fixtures stored in `tests/fixtures/` as realistic project directories
- `tmp_path` fixture used for tests needing writable temp directories
- Async test methods work directly (no decorator needed; asyncio_mode="auto")
- Private functions tested directly via import (e.g., `_parse_package_json`, `_parse_env_vars`)
- MCP Context mocked with: `ctx = MagicMock(); ctx.info = AsyncMock(); ctx.error = AsyncMock()`
- For search tool context: also set `ctx.request_context.lifespan_context.registry`
- Tool functions return `dict[str, object]` (serialized via `dataclasses.asdict`)
- Patch targets at the module where imported, not where defined

## Fixture Projects Available
- `tests/fixtures/python_fastapi_project/` -- pyproject.toml, docker-compose.yml, .env.example, .github/
- `tests/fixtures/node_express_project/` -- package.json, docker-compose.yml, .env
- `tests/fixtures/minimal_project/` -- requirements.txt, Makefile
- `tests/fixtures/empty_project/` -- empty directory

## Known Edge Cases
- `_normalize_python_dep()` does NOT strip leading whitespace before regex split
- Docker image matching uses substring search (`fragment in image_name`)
- Env-pattern-detected techs get confidence=0.7 (lower than file-based detection)
- `recommend_servers()` always adds filesystem-mcp recommendation
- Health check timeout clamped to 5-60 seconds via `max(5, min(timeout_seconds, 60))`
- Health "timeout" status distinguished by "did not respond within" substring in error
- `_scan_project_safe` returns None on any exception (graceful degradation for search)

## Tools Module Structure
- `src/mcp_tap/tools/scan.py` -- scan_project tool (calls scanner, cross-refs installed)
- `src/mcp_tap/tools/configure.py` -- configure_server tool (install -> write config -> validate)
- `src/mcp_tap/tools/health.py` -- check_health tool (batch health check via asyncio.gather)
- `src/mcp_tap/tools/search.py` -- search_servers tool (registry search + context-aware scoring)
- `src/mcp_tap/scanner/scoring.py` -- score_result + relevance_sort_key helpers
- `src/mcp_tap/errors.py` -- McpTapError hierarchy

## Mock Patterns for Tools
- Installer: `MagicMock()` with `install=AsyncMock(return_value=InstallResult(...))` and `build_server_command=MagicMock(return_value=(cmd, args))`
- Connection tester: `AsyncMock(return_value=ConnectionTestResult(...))`
- Config detection: `patch("mcp_tap.tools.X.detect_clients", return_value=[ConfigLocation(...)])`
- Config writer: `patch("mcp_tap.tools.X.write_server_config")` -- verify called/not called
- For scan tool: patch `_get_installed_server_names` to control installed set
- For health tool: patch parse_servers, read_config, detect_clients, test_server_connection
- For search tool: mock registry via ctx.request_context.lifespan_context.registry.search
- For search context-aware: patch `mcp_tap.tools.search._scan_project_safe`

## Health Check Models
- ServerHealth: name, status ("healthy"/"unhealthy"/"timeout"), tools_count, tools, error
- HealthReport: client, config_file, total, healthy, unhealthy, servers
- check_health returns asdict(HealthReport) | message for no-servers/no-client cases

## ConfigureResult Model
- Fields: success, server_name, config_file, message, config_written, install_status, tools_discovered, validation_passed
- install_status values: "installed", "already_available", "skipped", "failed"
- config_written from `ServerConfig.to_dict()` -- omits env when empty

## Scoring Module
- score_result(name, desc, profile) -> (relevance, reason)
- Pass 1: exact tech name match -> "high"
- Pass 2: category keyword match -> "medium"
- No match -> "low" with empty reason
- Empty profile -> always "low"
- relevance_sort_key: high=0, medium=1, low=2, unknown=99
