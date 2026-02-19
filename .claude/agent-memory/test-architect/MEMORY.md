# Test Architect Memory — mcp-tap

## Testing Setup
- pytest + pytest-asyncio (asyncio_mode="auto")
- Test dir: `tests/`
- Run: `pytest tests/`
- Linter: `ruff check src/ tests/`
- Current: 119 tests passing (test_config, test_registry, test_models, test_scanner)
- Mock all external I/O (httpx, subprocess, filesystem)
- Target: >80% coverage on new code

## Project Conventions
- `from __future__ import annotations` in ALL files
- All dataclasses frozen=True, slots=True
- Ruff rules: E, F, W, I, UP, B, SIM, RUF (import sorting enforced via I001)
- Unused unpacked vars must use `_` prefix (RUF059)
- Line length: 100 chars
- Python target: 3.11+

## Test Patterns Established
- Test classes grouped by component (e.g., TestParsePackageJson, TestScanFullPythonProject)
- Fixtures stored in `tests/fixtures/` as realistic project directories
- `tmp_path` fixture used for tests needing writable temp directories
- Async test methods work directly (no decorator needed; asyncio_mode="auto")
- Private functions tested directly via import (e.g., `_parse_package_json`)

## Fixture Projects Available
- `tests/fixtures/python_fastapi_project/` — pyproject.toml, docker-compose.yml, .env.example, .github/
- `tests/fixtures/node_express_project/` — package.json, docker-compose.yml, .env
- `tests/fixtures/minimal_project/` — requirements.txt, Makefile
- `tests/fixtures/empty_project/` — empty directory

## Known Edge Cases
- `_normalize_python_dep()` does NOT strip leading whitespace before regex split
  (callers strip lines beforehand, so this is by design, not a bug)
- Docker image matching uses substring search (`fragment in image_name`)
- Env-pattern-detected techs get confidence=0.7 (lower than file-based detection)
- `recommend_servers()` always adds filesystem-mcp recommendation

## Scanner Module Structure
- `src/mcp_tap/scanner/detector.py` — parsers + scan_project()
- `src/mcp_tap/scanner/recommendations.py` — TECHNOLOGY_SERVER_MAP + recommend_servers()
- `src/mcp_tap/models.py` — DetectedTechnology, ProjectProfile, ServerRecommendation, TechnologyCategory
- `src/mcp_tap/errors.py` — ScanError
