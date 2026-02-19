# Python Craftsman Memory — mcp-tap

## Project
- mcp-tap: Python 3.11+ MCP meta-server
- Build: hatchling | Linter: ruff (line-length=100)
- All dataclasses: `frozen=True, slots=True`
- All I/O: async (httpx, asyncio subprocess)
- Imports: always `from __future__ import annotations`
- `PackageInstaller` Protocol in `installer/base.py`

## Ruff / Linting
- ruff not in PATH by default — use `uv run ruff check ...` or install via `uv pip install ruff`
- ruff enforces single blank line between imports block and first code (not double blank)
- Target Python 3.11: cannot use `type X = ...` (PEP 695) — use plain assignment for TypeAlias
- ruff selects: E, F, W, I, UP, B, SIM, RUF

## Architecture Patterns
- Domain models in `models.py` (zero deps), errors in `errors.py`
- Scanner package: `scanner/{__init__, detector, recommendations}.py`
- `scan_project(path: str) -> ProjectProfile` is the scanner public entry point
- All parsers return `tuple[list[DetectedTechnology], list[str]]` (techs, env_vars)
- Parsers run concurrently via `asyncio.gather(return_exceptions=True)`
- File reads use `asyncio.to_thread(filepath.read_text, encoding="utf-8")`
- Docker-compose parsed via regex (no PyYAML dep)
- `tomllib` from stdlib for TOML (Python 3.11+)
- Use `dataclasses.replace()` for immutable updates on frozen dataclasses

## Tool Patterns
- Tools in `tools/` return `dict[str, object]` (serialized via `dataclasses.asdict`)
- Every tool has a `ctx: Context` param; app context accessed via `ctx.request_context.lifespan_context`
- Error handling: `McpTapError` -> return error dict; `Exception` -> `ctx.error()` + return error dict
- Config reading pattern: `detect_clients()` or `resolve_config_path(MCPClient(client))` -> `read_config()` -> `parse_servers()`
- `test_server_connection()` in `connection/tester.py` is the shared connection test primitive
- Batch operations use `asyncio.gather(*tasks, return_exceptions=True)` and handle `BaseException` results
- `zip()` requires `strict=True` per ruff B905 rule
- Scanner module: `scanner/scoring.py` added for context-aware search relevance scoring

## Test Patterns
- Mock Context: `ctx = MagicMock(); ctx.info = AsyncMock(); ctx.error = AsyncMock()`
- Use `@patch("mcp_tap.tools.<module>.<dependency>")` for mocking
- Fixture directories in `tests/fixtures/` (python_fastapi_project, node_express, etc.)
- `asyncio_mode = "auto"` in pyproject.toml — no need for `@pytest.mark.asyncio`
- VS Code auto-linter may modify files during editing — always re-check imports after edits

## Conventions
- Commit messages: English, no Co-Authored-By (per CLAUDE.md)
- Comments/code in English, agent communication in Portuguese (BR)
- Branch naming: `feature/YYYY-MM-DD-description`
- Line length: 100 chars
