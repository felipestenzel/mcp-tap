# mcp-tap — Project Rules

> **The last MCP server you install by hand.**
> Python 3.11+ | FastMCP | Hexagonal Architecture | MIT License

---

## MANDATORY RULES FOR ALL CODE AGENTS

**These rules apply to ANY code agent working on this project. No exceptions.**

### Before Implementing (Pre-flight)

1. **Check existing issues**: Read `docs/issues/` to verify if the problem was already documented or resolved
2. **Check MEMORY.md**: Read `~/.claude/projects/.../memory/MEMORY.md` for context and lessons learned
3. **Check agent memories**: Read relevant `.claude/agent-memory/<agent>/MEMORY.md` for specialized context
4. **Create issue**: Document the problem in `docs/issues/YYYY-MM-DD_slug.md` using `docs/issues/_TEMPLATE.md` BEFORE starting implementation
5. **Create feature branch**: ALWAYS create a branch before starting any work. NEVER commit directly to `main`.
   - Feature: `feature/YYYY-MM-DD-description`
   - Fix: `fix/YYYY-MM-DD-description`
   - Refactor: `refactor/YYYY-MM-DD-description`
   - Register the branch name in the issue doc (Branch field)
6. **Run baseline tests**: `pytest tests/` to know the current state before touching code
7. **Use Context7**: ALWAYS use MCP Context7 (`resolve-library-id` + `query-docs`) to validate best practices and latest versions of libraries before implementing

### During Implementation

8. **Follow hexagonal architecture strictly**:
   - `models.py` — Frozen dataclasses, StrEnums (domain layer, ZERO dependencies)
   - `errors.py` — Exception hierarchy (domain layer, ZERO dependencies)
   - `registry/`, `config/`, `installer/`, `connection/` — Adapters (infrastructure layer)
   - `tools/` — Use cases / entry points (application layer)
   - `server.py` — Composition root (wiring only, no business logic)
   - Protocols in `base.py` files define ports — implementations are adapters
   - **Direction of dependency**: tools → models/errors ← adapters. Adapters NEVER import tools.

9. **Code quality standards**:
   - ALL dataclasses MUST be `frozen=True, slots=True`
   - ALL functions that do I/O MUST be `async`
   - Type hints on ALL function signatures (PEP 604 style: `str | None`)
   - Ruff compliance: `ruff check src/ tests/` must pass
   - Error messages written for LLM consumption — clear, actionable, no stack traces
   - NEVER use `shell=True` in subprocess calls
   - NEVER store secrets in code or config files committed to git

10. **Testing requirements**:
    - Every new module MUST have corresponding tests in `tests/`
    - Use `pytest` + `pytest-asyncio` (asyncio_mode = "auto")
    - Test the happy path AND at least one error path per function
    - Mock external I/O (httpx, subprocess, filesystem) — tests must run offline
    - Target: >80% coverage on new code

11. **File organization**:
    - New source files ALWAYS in `src/mcp_tap/{appropriate_package}/`
    - New tools ALWAYS in `src/mcp_tap/tools/` and registered in `server.py`
    - Edit existing files when possible instead of creating new ones
    - Each package MUST have `__init__.py`

### After Implementing (Post-flight)

12. **Run tests**: `pytest tests/` — confirm nothing broke
13. **Run linter**: `ruff check src/ tests/` — confirm no violations
14. **Update the issue**: Status to `done`, fill "Solution", "Files Changed", and "Verification" sections
15. **Update affected docs**: ARCHITECTURE.md, README.md, etc.
16. **Update MEMORY.md**: If there was a significant discovery or lesson learned

### Context Window Handoff (INVIOLABLE RULE)

**When context window usage reaches ~95% (less than 5% remaining), you MUST:**

1. **Stop at a safe point** — never mid-edit, mid-refactor, or in a broken state. Ensure tests pass or at least the code compiles.
2. **Commit any pending work** to the current feature branch (even if incomplete, with a `WIP:` prefix).
3. **Create a handoff document** at `docs/handoff/YYYY-MM-DD_HHMM_session-description.md` using the template at `docs/handoff/_TEMPLATE.md`. This document MUST contain:
   - What was accomplished this session
   - Exactly where we stopped (file, function, line if relevant)
   - What to do next (step-by-step to resume)
   - Open questions or blockers
   - All files modified this session
4. **Update the issue doc** with current status if one is in progress.
5. **Inform the user** that context is running low and the handoff doc was created.

This rule is **non-negotiable**. A lost session with no handoff is unrecoverable work. The handoff doc IS the continuity guarantee.

Handoff docs are **temporary** — delete them once the next session successfully resumes.

### Conventions

- **Language**: Code in English. Comments in English. Docs in English. Agent communication in Portuguese (BR).
- **Branch naming**: `feature/YYYY-MM-DD-description` or `fix/YYYY-MM-DD-description`
- **Issue naming**: `docs/issues/YYYY-MM-DD_descriptive-slug.md`
- **Commit messages**: English, format `Add/Update/Fix/Remove [component]: [description]`. NEVER include Co-Authored-By or any Claude/AI attribution. All commits must be authored solely by `felipestenzel`.
- **Issue template**: Always use `docs/issues/_TEMPLATE.md` as base
- **Imports**: Use `from __future__ import annotations` in ALL files
- **Line length**: 100 characters (configured in ruff)
- **Python target**: 3.11+ (no walrus operator avoidance needed, use modern syntax)

---

## Architecture Overview

```
src/mcp_tap/
├── server.py              # Composition root (FastMCP wiring)
├── models.py              # Domain models (frozen dataclasses + StrEnums)
├── errors.py              # Exception hierarchy
├── registry/
│   └── client.py          # MCP Registry API adapter (httpx)
├── config/
│   ├── detection.py       # Auto-detect MCP clients on system
│   ├── reader.py          # Read client config files (JSON)
│   └── writer.py          # Atomic writes to config files
├── installer/
│   ├── base.py            # PackageInstaller Protocol (port)
│   ├── npm.py             # npx adapter
│   ├── pip.py             # uvx/pip adapter
│   ├── docker.py          # docker adapter
│   ├── resolver.py        # Registry type → installer mapping
│   └── subprocess.py      # Safe async subprocess wrapper
├── connection/
│   └── tester.py          # MCP SDK client: spawn → connect → list_tools
└── tools/                 # Application layer (MCP tool entry points)
    ├── search.py           # search_servers
    ├── configure.py        # configure_server
    ├── test.py             # test_connection
    ├── list.py             # list_installed
    └── remove.py           # remove_server
```

---

## Agent Workflow

When using specialized agents, ALWAYS:
1. Check which custom agents exist in `.claude/agents/` before starting
2. Launch agents in parallel for independent tasks
3. Use the most specific agent for the task (e.g., `test-architect` for tests, `clean-architecture-designer` for architecture)
4. Use `Context7` MCP to validate library versions and best practices

### Agent Selection Guide

| Task | Agent |
|------|-------|
| Writing new Python code | `python-craftsman` |
| Architecture/structure changes | `clean-architecture-designer` |
| Writing/improving tests | `test-architect` |
| Debugging errors | `debug-detective` |
| Performance issues | `perf-optimizer` |
| Code cleanup | `refactoring-specialist` |
| CI/CD pipeline | `cicd-deployment-architect` |
| Experimental features | `innovation-lab` |
| Strategic decisions | `product-strategy-advisor` |

---

## Key Dependencies

| Package | Purpose | Min Version |
|---------|---------|-------------|
| `mcp` | MCP SDK (FastMCP server) | >=1.12.0 |
| `httpx` | Async HTTP client | >=0.27.0 |
| `pytest` | Testing framework | dev |
| `pytest-asyncio` | Async test support | dev |
| `ruff` | Linter + formatter | dev |

---

## Quick Commands

```bash
# Run tests
pytest tests/

# Run linter
ruff check src/ tests/

# Run server locally
python -m mcp_tap

# Run with uvx
uvx mcp-tap
```
