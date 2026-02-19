# mcp-tap Architecture

## Overview

mcp-tap is a **meta-MCP server** — an MCP server that manages other MCP servers. It follows **hexagonal architecture** (ports & adapters) to keep domain logic independent of infrastructure details.

## Layer Diagram

```
                    ┌─────────────────────────────────┐
                    │         MCP Protocol             │
                    │    (FastMCP transport layer)      │
                    └──────────────┬──────────────────┘
                                   │
                    ┌──────────────▼──────────────────┐
                    │      server.py (Composition)     │
                    │    Wires tools + adapters         │
                    └──────────────┬──────────────────┘
                                   │
              ┌────────────────────┼────────────────────┐
              │                    │                     │
   ┌──────────▼──────┐  ┌────────▼────────┐  ┌────────▼────────┐
   │  tools/ (App)    │  │  models.py      │  │  errors.py      │
   │  search          │  │  (Domain)       │  │  (Domain)       │
   │  configure       │  │  Frozen DCs     │  │  Exception tree │
   │  test            │  │  StrEnums       │  │                 │
   │  list            │  │  Zero deps      │  │  Zero deps      │
   │  remove          │  └────────▲────────┘  └────────▲────────┘
   └──────────┬──────┘           │                     │
              │            ┌─────┴─────────────────────┘
              │            │
   ┌──────────▼──────────▼─────────────────────────────┐
   │           Infrastructure Adapters                   │
   │                                                     │
   │  registry/client.py    — MCP Registry API (httpx)   │
   │  config/detection.py   — Auto-detect MCP clients    │
   │  config/reader.py      — Read JSON config files     │
   │  config/writer.py      — Atomic write config files  │
   │  installer/npm.py      — npx zero-install           │
   │  installer/pip.py      — uvx/pip install            │
   │  installer/docker.py   — docker pull                │
   │  installer/resolver.py — Type → installer mapping   │
   │  installer/subprocess.py — Safe async subprocess    │
   │  connection/tester.py  — MCP SDK client test        │
   └───────────────────────────────────────────────────┘
```

## Dependency Rules

1. **Domain layer** (`models.py`, `errors.py`) has ZERO external imports
2. **Application layer** (`tools/`) imports domain + adapters
3. **Infrastructure layer** (`registry/`, `config/`, `installer/`, `connection/`) imports domain only
4. **Composition root** (`server.py`) wires everything together — only file that imports across layers
5. Adapters implement **Protocols** defined in `base.py` — these are the ports

## Key Design Decisions

### Frozen Dataclasses
All domain models use `@dataclass(frozen=True, slots=True)`. This guarantees:
- Immutability after construction
- Memory efficiency (slots)
- Safe for concurrent use

### Protocol-Based Ports
`PackageInstaller` is a `Protocol` class, not an ABC. This means:
- No inheritance required — structural subtyping
- Easy to mock in tests
- New installers just implement the interface

### Atomic Config Writes
`config/writer.py` writes to a temp file then uses `os.replace()` for atomic swap. This prevents:
- Corrupt configs from interrupted writes
- Partial JSON files

### Safe Subprocess Execution
`installer/subprocess.py` wraps `asyncio.create_subprocess_exec` with:
- NEVER `shell=True`
- Timeout enforcement
- stdout/stderr capture
- Clean error messages for LLM consumption

### Tool Annotations
Each MCP tool has explicit `ToolAnnotations`:
- `readOnlyHint=True` for search, list, test (safe operations)
- `destructiveHint=True` for configure, remove (modifies filesystem)

## Data Flow: Install a Server

```
User asks → LLM calls configure_server tool
  → search MCP Registry (registry/client.py)
  → resolve installer (installer/resolver.py)
  → install package (installer/npm.py | pip.py | docker.py)
  → detect client (config/detection.py)
  → read existing config (config/reader.py)
  → merge new server entry
  → atomic write config (config/writer.py)
  → return ConfigureResult to LLM
```

## Supported MCP Clients

| Client | Config Location | Scope |
|--------|----------------|-------|
| Claude Desktop | `~/Library/Application Support/Claude/claude_desktop_config.json` | User |
| Claude Code | `.claude/mcp_servers.json` | Project |
| Cursor | `.cursor/mcp.json` | Project |
| Windsurf | `~/.windsurf/mcp.json` | User |
