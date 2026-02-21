# Orchestration Architect Memory -- mcp-tap

## Project: mcp-tap (MCP meta-server)

## Implementation Patterns Learned

### Making sync functions async (breaking change)
When converting `recommend_servers` from sync to async:
1. ALL callers must be updated with `await` (detector.py, tests)
2. Test methods calling it must become `async def` (pytest-asyncio handles the rest)
3. The function signature change propagates: detector.py -> tools/scan.py -> base.py port
4. This was a ~33-test breakage that was fully mechanical to fix

### Dynamic Discovery Engine Architecture
- `scanner/archetypes.py` - pure function, no I/O, detects project patterns from tech combinations
- `scanner/hints.py` - pure function, generates search suggestions from unmapped techs/env vars/archetypes
- Both follow hexagonal architecture: domain logic only, imported by application layer (tools/scan.py)
- Registry bridge: optional async parameter in recommend_servers, timeout-protected, silent fallback

### Testing Patterns
- Mock registry with `unittest.mock.AsyncMock` for dynamic registry tests
- Timeout test: use `asyncio.sleep(10)` in mock, relies on `asyncio.wait_for(timeout=5)` in prod code
- Parametrize heavily for map expansion tests (21 Python deps, 17 server map entries, etc.)
- Each test file targets ~100-150 tests; avoid mega test files

### Task Decomposition for Feature Implementation
- 3-phase approach works well: Data (maps/static), Logic (models/functions), Integration (async/wiring)
- Phase dependencies are natural: models before logic, logic before wiring
- Running tests after each phase catches regressions immediately
- Always run `ruff check` AND `ruff format` -- both are checked in CI
