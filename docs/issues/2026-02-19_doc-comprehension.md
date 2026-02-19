# Documentation Comprehension — Extract Config from Server READMEs

- **Date**: 2026-02-19
- **Status**: `done`
- **Branch**: `feature/2026-02-19-v02-roadmap`
- **Priority**: `medium`
- **Issue**: #12

## Problem

`configure_server` depends on the MCP Registry API for structured data (transport, command, args, env vars). When a server is NOT in the registry, or the registry data is incomplete (missing env vars, wrong transport), the tool fails or produces broken configs.

The original issue (adenhq/hive#4527) identifies this as the core "interpretation gap":

> "A CLI tool can run `npm install`. It cannot read an arbitrary README, understand that 'set the GITHUB_TOKEN environment variable with repo scope' means it needs to create a credential entry, infer the transport type from installation instructions, and generate a correct configuration."

Today mcp-tap cannot bridge this gap. It relies entirely on pre-structured registry data.

### Examples of what breaks today

1. **Server not in registry**: User finds `mcp-server-kubernetes` on GitHub. It's not in the MCP Registry. `search_servers` returns nothing. The user must manually figure out command, args, env vars, and transport.

2. **Incomplete registry data**: Registry says a server needs `API_KEY` but the README says it actually needs `API_KEY` AND `API_SECRET` AND `WEBHOOK_URL`. Config is written with only `API_KEY`, validation fails.

3. **Ambiguous transport**: Registry says `stdio` but the server actually supports `streamable-http` on port 3000 and `stdio` only works with specific args. Config is wrong.

## Context

- **Key insight**: mcp-tap runs inside an LLM. The LLM CAN read documentation. What mcp-tap needs is a tool that **fetches** a server's README and returns structured data the LLM can act on.
- **Module affected**: New tool + new module
- **Existing infrastructure**:
  - `SearchResult.repository_url` already has the GitHub URL of each server
  - `configure_server` already accepts all config params (command, args, env_vars, registry_type)
  - The LLM can already reason about documentation — we just need to fetch and pre-process it

## Architecture

### New tool: `inspect_server`

A new MCP tool that fetches a server's documentation and extracts structured configuration hints. This is a **read-only** tool — it doesn't install or configure anything.

```python
async def inspect_server(
    repository_url: str,
    ctx: Context,
) -> dict[str, object]:
    """Fetch an MCP server's documentation and extract configuration details.

    Use this when search_servers returns incomplete data (missing env vars,
    unclear transport) or when you have a GitHub URL for a server not in the
    registry.

    Fetches the README.md from the repository URL and extracts:
    - Install commands (npm, pip, docker)
    - Transport type (stdio, http, sse)
    - Required environment variables with descriptions
    - Command and args patterns
    - Usage examples

    The extracted data may be incomplete or ambiguous — use your judgment
    to fill gaps based on the raw README content also returned.

    Args:
        repository_url: GitHub/GitLab repository URL
            (e.g. "https://github.com/modelcontextprotocol/servers").

    Returns:
        Dict with: extracted_config (structured hints), raw_readme
        (first 5000 chars of README for LLM reasoning), and
        confidence (how much structured data was found).
    """
```

### New module: `src/mcp_tap/inspector/`

```
src/mcp_tap/inspector/
├── __init__.py
├── fetcher.py      # Fetch README from GitHub/GitLab URLs
└── extractor.py    # Regex-based extraction of config hints from README text
```

#### `fetcher.py` — README retrieval

```python
async def fetch_readme(repository_url: str, http_client: httpx.AsyncClient) -> str | None:
    """Fetch README.md from a repository URL.

    Supports:
    - GitHub: converts to raw.githubusercontent.com URL
    - GitLab: converts to raw API URL
    - Direct URLs: fetches as-is

    Returns the raw markdown text, or None if not found.
    """
```

URL conversion logic:
- `https://github.com/owner/repo` → `https://raw.githubusercontent.com/owner/repo/HEAD/README.md`
- `https://github.com/owner/repo/tree/main/packages/server-foo` → `https://raw.githubusercontent.com/owner/repo/main/packages/server-foo/README.md`
- `https://gitlab.com/owner/repo` → `https://gitlab.com/owner/repo/-/raw/main/README.md`

#### `extractor.py` — Pattern-based extraction

Extract structured hints from README markdown using regex patterns. NOT an LLM call — deterministic extraction that provides hints for the LLM to reason about.

```python
@dataclass(frozen=True, slots=True)
class ConfigHints:
    """Structured hints extracted from a server's documentation."""
    install_commands: list[str]           # e.g. ["npx -y @foo/bar", "pip install foo"]
    transport_hints: list[str]            # e.g. ["stdio", "http"]
    env_vars_mentioned: list[EnvVarHint]  # env var names + surrounding context
    command_patterns: list[str]           # e.g. ["npx -y @foo/bar --port 3000"]
    json_config_blocks: list[str]         # any JSON blocks that look like MCP config
    confidence: float                      # 0.0-1.0 based on how many patterns matched

@dataclass(frozen=True, slots=True)
class EnvVarHint:
    name: str
    context: str       # The sentence/line where this var was mentioned
    is_required: bool  # True if context suggests it's required (not optional)
```

Extraction patterns:
1. **Install commands**: Match `npm install`, `npx`, `pip install`, `uvx`, `docker run` in code blocks
2. **Env vars**: Match `[A-Z][A-Z0-9_]+` in code blocks, especially after `env:`, `environment:`, or in `.env` examples
3. **Transport hints**: Match `stdio`, `http`, `sse`, `streamable-http` in text or config blocks
4. **JSON config blocks**: Match JSON blocks containing `"command"`, `"args"`, `"env"` keys
5. **Command patterns**: Match shell commands in code blocks that look like server invocations

### Integration

1. Register `inspect_server` in `server.py` as a read-only tool
2. The LLM workflow becomes:
   - `search_servers("kubernetes")` → finds server but env vars incomplete
   - `inspect_server(repository_url)` → gets README + extracted hints
   - LLM reasons about hints + raw README
   - `configure_server(...)` with correct params

### What this does NOT do

- Does NOT call an LLM to parse the README (that's the host LLM's job)
- Does NOT auto-generate configs from docs (too risky without human review)
- Does NOT replace the Registry API (registry data is preferred when available)
- Does NOT cache READMEs (each fetch is fresh — READMEs change)

## Scope

1. `src/mcp_tap/models.py` — Add `ConfigHints`, `EnvVarHint` dataclasses
2. `src/mcp_tap/inspector/__init__.py` — NEW
3. `src/mcp_tap/inspector/fetcher.py` — NEW: README fetch from GitHub/GitLab
4. `src/mcp_tap/inspector/extractor.py` — NEW: regex-based extraction
5. `src/mcp_tap/tools/inspect.py` — NEW: `inspect_server` tool
6. `src/mcp_tap/server.py` — Register `inspect_server` as read-only tool
7. `tests/test_inspector.py` — NEW: tests for fetcher and extractor

## Test Plan

- [ ] fetcher converts GitHub URLs to raw.githubusercontent.com correctly
- [ ] fetcher converts GitLab URLs correctly
- [ ] fetcher handles monorepo paths (e.g. `github.com/org/repo/tree/main/packages/server-foo`)
- [ ] fetcher returns None for 404s gracefully
- [ ] extractor finds env vars in README code blocks
- [ ] extractor finds install commands (npm, pip, docker)
- [ ] extractor finds transport hints
- [ ] extractor finds JSON config blocks
- [ ] inspect_server returns structured hints + raw README
- [ ] All httpx calls are mocked (tests run offline)
- [ ] All 320+ existing tests still pass

## Root Cause

mcp-tap has no way to fetch or process server documentation. It's a blind spot between "find a server" and "configure it correctly."

## Solution

Implemented `inspector/` module with `fetcher.py` (GitHub/GitLab raw URL conversion + async fetch) and `extractor.py` (regex-based extraction of install commands, env vars, transport hints, command patterns, and JSON config blocks). New `inspect_server` tool registered as read-only in `server.py`. Returns structured `ConfigHints` plus first 5000 chars of raw README for LLM reasoning.

## Files Changed

- `src/mcp_tap/models.py` — Added `EnvVarHint`, `ConfigHints` dataclasses
- `src/mcp_tap/inspector/__init__.py` — NEW
- `src/mcp_tap/inspector/fetcher.py` — NEW: README fetch from GitHub/GitLab
- `src/mcp_tap/inspector/extractor.py` — NEW: regex-based config extraction
- `src/mcp_tap/tools/inspect.py` — NEW: `inspect_server` tool
- `src/mcp_tap/server.py` — Registered `inspect_server` as read-only tool
- `tests/test_inspector.py` — NEW: 22 tests

## Lessons Learned

Filtering env vars by requiring underscores and ignoring common uppercase words (MCP, JSON, README etc.) eliminates most false positives from regex extraction.
