# Test Architect Memory — mcp-tap

## Testing Setup
- pytest + pytest-asyncio (asyncio_mode="auto")
- Test dir: `tests/`
- Run: `pytest tests/`
- Current: 20 tests passing (test_config, test_registry, test_models)
- Mock all external I/O (httpx, subprocess, filesystem)
- Target: >80% coverage on new code
