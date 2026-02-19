# Test Architect Memory -- mcp-tap

## Testing Setup
- pytest + pytest-asyncio (asyncio_mode="auto")
- Test dir: `tests/`
- Run: `pytest tests/`
- Linter: `ruff check src/ tests/`
- Current: 405 tests passing (config, registry, models, scanner, scoring, tools, healing)
- Mock all external I/O (httpx, subprocess, filesystem)
- Target: >80% coverage on new code

## Project Conventions
- `from __future__ import annotations` in ALL files
- All dataclasses frozen=True, slots=True
- Ruff rules: E, F, W, I, UP, B, SIM, RUF (import sorting enforced via I001)
- Unused unpacked vars must use `_` prefix (RUF059)
- RUF012: Mutable class attributes need ClassVar annotation. Use tuples for module-level parametrize data.
- Line length: 100 chars
- Python target: 3.11+
- IMPORTANT: VS Code linter auto-removes unused imports between Edit calls. When adding imports + new code, use Write to replace the entire file atomically -- do NOT do two separate edits (import then code)

## Test Patterns Established
- Test classes grouped by component (e.g., TestClassifier, TestFixer, TestRetryLoop)
- Fixtures stored in `tests/fixtures/` as realistic project directories
- `tmp_path` fixture used for tests needing writable temp directories
- Async test methods work directly (no decorator needed; asyncio_mode="auto")
- Private functions tested directly via import (e.g., `_parse_package_json`, `_parse_env_vars`)
- MCP Context mocked with: `ctx = MagicMock(); ctx.info = AsyncMock(); ctx.error = AsyncMock()`
- For search tool context: also set `ctx.request_context.lifespan_context.registry`
- Tool functions return `dict[str, object]` (serialized via `dataclasses.asdict`)
- Patch targets at the module where imported, not where defined

## Healing Module Tests (tests/test_healing.py)
- 85 tests: classifier (42), fixer (14), retry loop (14), model validation (15)
- Classifier: parametrized across all ErrorCategory values + edge cases
- Fixer: mock `mcp_tap.healing.fixer.shutil.which` for COMMAND_NOT_FOUND
- Retry: mock classify_error, generate_fix, test_server_connection at healing.retry level
- Models: HealingAttempt(diagnosis, fix_applied, success), HealingResult(fixed, attempts, fixed_config, user_action_needed)
- Timeout escalation: [15, 30, 60] for TIMEOUT category
- User-action-required: AUTH, MISSING_ENV, CONN_REFUSED, PERMISSION, UNKNOWN stop immediately

## Parallel Agent Gotcha (Critical)
- When working in parallel with implementation agents, models.py can change mid-session
- Python import cache may differ from file-on-disk content
- Always verify runtime fields: `python -c "from mcp_tap.models import X; print(list(X.__dataclass_fields__.keys()))"`
- Write tests atomically using Write tool to avoid partial state from concurrent modifications
- Read source files immediately before writing tests, not at session start

## Fixture Projects Available
- `tests/fixtures/python_fastapi_project/` -- pyproject.toml, docker-compose.yml, .env.example
- `tests/fixtures/node_express_project/` -- package.json, docker-compose.yml, .env
- `tests/fixtures/minimal_project/` -- requirements.txt, Makefile
- `tests/fixtures/empty_project/` -- empty directory

## Known Edge Cases
- Classifier env var detection requires uppercase [A-Z][A-Z0-9_]{2,} token in error message
- `_normalize_python_dep()` does NOT strip leading whitespace before regex split
- Docker image matching uses substring search (`fragment in image_name`)
- Env-pattern-detected techs get confidence=0.7 (lower than file-based detection)
- `recommend_servers()` always adds filesystem-mcp recommendation
- Health check timeout clamped to 5-60 seconds
- `_scan_project_safe` returns None on any exception

## Tools Module Structure
- `src/mcp_tap/tools/scan.py` -- scan_project tool
- `src/mcp_tap/tools/configure.py` -- configure_server tool
- `src/mcp_tap/tools/health.py` -- check_health tool
- `src/mcp_tap/tools/search.py` -- search_servers tool
- `src/mcp_tap/healing/` -- classifier.py, fixer.py, retry.py (self-healing module)
- `src/mcp_tap/scanner/scoring.py` -- score_result + relevance_sort_key
- `src/mcp_tap/errors.py` -- McpTapError hierarchy

## Mock Patterns for Tools
- Installer: `MagicMock()` with `install=AsyncMock(return_value=InstallResult(...))`
- Connection tester: `AsyncMock(return_value=ConnectionTestResult(...))`
- Config detection: `patch("mcp_tap.tools.X.detect_clients", ...)`
- For healing retry: patch `mcp_tap.healing.retry.test_server_connection`
- For healing fixer: patch `mcp_tap.healing.fixer.shutil.which`
- For healing classifier: just construct ConnectionTestResult directly (pure function)
