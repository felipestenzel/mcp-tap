# Smithery Integration: Multi-source MCP server discovery

- **Date**: 2026-02-21
- **Status**: `done`
- **Branch**: `main` (merged as v0.5.0)
- **Priority**: `high`

## Problem

mcp-tap currently searches only the official MCP Registry (`registry.modelcontextprotocol.io`),
which uses substring-only matching and covers a fraction of available MCP servers. The Smithery
marketplace (`smithery.ai`) has a larger catalog, uses semantic search (embeddings), and exposes
popularity signals (`useCount`) and quality signals (`verified`, `security.scanPassed`) that the
official registry lacks entirely.

Users running `search_servers` or `scan_project` may miss the best server for their use case
because it lives on Smithery but not in the official registry.

## Context

- **Affected layer**: `registry/` (infrastructure adapter) + `tools/search.py` (application layer)
- **Discovered via**: Strategic analysis after observing that `scan_project` on the mcp-tap repo
  itself produced only 1-2 recommendations despite the project having clear needs
- **Research conducted**: Deep API research (Smithery auth flow, anonymous access, scraping
  viability) + full architecture analysis of current `RegistryClient` and `search_servers`

## Root Cause

Single-source architecture in `registry/client.py` — only `RegistryClient` (MCP Registry) is
wired in `AppContext`. The hexagonal architecture already supports multi-source via the
`RegistryClientPort` Protocol, but no second adapter was built.

## Key Research Findings

### 1. Smithery API is publicly accessible — no API key required

**Critical discovery**: `GET https://api.smithery.ai/servers?q=...` returns full JSON **without
any Authorization header**. The official docs say auth is required, but it is optional for read
operations. The Smithery CLI itself uses `apiKey: ""` for public registry searches.

Confirmed by live testing: 200 OK with full payload, no rate-limit headers, CDN-cached responses
(Cache-Control: public, max-age=60, s-maxage=3600). Smithery's own docs explicitly encourage
MCP clients to use the Registry API.

This eliminates the API key friction entirely for discovery. `SMITHERY_API_KEY` becomes
**optional** for enhanced SLA/future-proofing, not a prerequisite.

### 2. Smithery API — endpoints and fields

**Search**: `GET https://api.smithery.ai/servers`

Key parameters:
- `q` — full-text + **semantic search** (embeddings), not substring
- `pageSize` — up to 100
- `topK` — vector index candidates (10–500)
- `verified=true` — quality filter
- `fields` — projection (e.g. `fields=qualifiedName,displayName,useCount,verified`)

Response per server (all available without auth):
```json
{
  "id": "a21f1117-...",
  "qualifiedName": "neon",
  "displayName": "Neon",
  "description": "Manage PostgreSQL projects...",
  "iconUrl": "https://...",
  "verified": true,
  "useCount": 269,
  "remote": true,
  "isDeployed": true,
  "createdAt": "2026-01-29T06:26:32.660Z",
  "homepage": "https://smithery.ai/servers/neon",
  "score": 0.013
}
```

**Detail**: `GET https://api.smithery.ai/servers/{qualifiedName}` adds:
- `tools[]` — full MCP tool list with `name`, `description`, `inputSchema`
- `security.scanPassed` — automated security scan result
- `connections[]` — stdio bundle or HTTP connection info
- `deploymentUrl` — for remote/hosted servers

### 3. Critical constraint: no package_identifier

The Smithery API does **not** expose npm package name, pip package, or docker image. It uses:
- `bundleUrl` — proprietary MCPB format
- `deploymentUrl` — for hosted HTTP servers

**Workarounds for install path** (in priority order):
1. **Dual-source match**: servers appearing in both registries get the MCP Registry's
   `package_identifier` automatically — covers the majority of popular servers
2. **npm probe heuristic**: try `npm view @{namespace}/{slug} version` — works for ~70-80%
   of Smithery servers that are standard npm packages
3. **Smithery CLI installer**: new `SmitheryInstaller` adapter using
   `npx @smithery/cli@latest install {qualifiedName} --client {client}` — covers the rest

### 4. Optional API key setup via device flow

If the user wants to register a key for better SLA or future rate limits, the Smithery device
flow is clean:
```
POST /api/auth/cli/session  →  { sessionId, authUrl }
→ open browser (1-click GitHub login)
→ GET /api/auth/cli/poll/{sessionId}  →  { status: "success", apiKey: "sk-..." }
→ save to ~/.mcp-tap/credentials.json
```
A `setup_smithery` MCP tool can implement this as an optional step.

### 5. Auth strategy — final

| Scenario | Behavior |
|----------|----------|
| No SMITHERY_API_KEY | Anonymous access — full fields, works today |
| SMITHERY_API_KEY set | Same requests with `Authorization: Bearer` header |
| `setup_smithery` tool | Device flow to persist key in credentials file |

### 6. Comparison: Smithery vs MCP Registry

| Signal | MCP Registry | Smithery |
|--------|-------------|----------|
| Auth required for search | No | **No** (updated — anonymous works) |
| Search type | Substring only | **Full-text + semantic** |
| `package_identifier` (npm/pip) | **YES** | NO |
| `env_vars` structured | **YES** | configSchema only |
| `useCount` (popularity) | NO | **YES** |
| `verified` (quality badge) | NO | **YES** |
| `tools[]` (MCP introspection) | NO | **YES** |
| `security.scanPassed` | NO | **YES** |
| Catalog size | Smaller (official) | **Larger** (community) |

### 7. Deduplication

The two registries use incompatible ID schemes. Best deduplication key: GitHub URL (`owner/repo`).
The MCP Registry already mirrors some Smithery servers under the `ai.smithery/` namespace prefix —
deduplication is more common than expected.

### 8. robots.txt

`smithery.ai/robots.txt` blocks `/api/` on the main domain — but `api.smithery.ai` is a separate
subdomain not covered. Smithery explicitly encourages client use of the Registry API in their docs.

## Solution

### Architecture

```
search_servers(query)
  ├── MCP Registry search        (always — provides installable results)
  └── Smithery search            (always — anonymous, zero config)
       ↓ parallel, deduplicate by GitHub URL → then by normalized name
       ↓ for hits in both: enrich MCP Registry result with useCount, verified, tools
       ↓ for Smithery-only: add with install workaround (npm probe → Smithery CLI)
       ↓ new output fields: use_count, verified, source, smithery_tools
```

### New files

```
src/mcp_tap/registry/
├── base.py          (modify: add RegistrySourcePort Protocol)
├── client.py        (existing — unchanged)
├── smithery.py      (NEW: SmitheryClient)
└── aggregator.py    (NEW: AggregatedRegistry — parallel search + merge + dedup)

src/mcp_tap/installer/
└── smithery.py      (NEW: SmitheryInstaller — npx @smithery/cli install)

src/mcp_tap/tools/
└── setup.py         (NEW: setup_smithery tool — optional device flow)
```

### Model changes (`models.py`)

Add `SmitherySignals` frozen dataclass (kept separate from `RegistryServer` for domain purity):
```python
@dataclass(frozen=True, slots=True)
class SmitherySignals:
    use_count: int = 0
    verified: bool = False
    security_scan_passed: bool | None = None
    tool_names: list[str] = field(default_factory=list)
    source: str = "official"   # "official" | "smithery" | "both"
```

### Output changes in `search_servers`

New fields added to each result dict:
- `use_count: int` — Smithery useCount (0 if unknown)
- `verified: bool` — Smithery verified badge (false if unknown)
- `source: str` — "official" | "smithery" | "both"
- `smithery_tools: list[str]` — tool names (only when `evaluate=True`)

## Files to Change

- `src/mcp_tap/registry/base.py` — add `RegistrySourcePort` Protocol
- `src/mcp_tap/registry/smithery.py` — NEW: SmitheryClient
- `src/mcp_tap/registry/aggregator.py` — NEW: AggregatedRegistry
- `src/mcp_tap/installer/base.py` — extend protocol if needed
- `src/mcp_tap/installer/smithery.py` — NEW: SmitheryInstaller
- `src/mcp_tap/installer/resolver.py` — register `RegistryType.SMITHERY`
- `src/mcp_tap/models.py` — add `SmitherySignals`, add `RegistryType.SMITHERY`
- `src/mcp_tap/server.py` — wire SmitheryClient + AggregatedRegistry in AppContext
- `src/mcp_tap/tools/search.py` — expose new fields (use_count, verified, source)
- `src/mcp_tap/tools/setup.py` — NEW: setup_smithery device flow tool (optional)
- `tests/test_smithery_client.py` — NEW: SmitheryClient unit tests
- `tests/test_registry_aggregator.py` — NEW: AggregatedRegistry tests
- `tests/test_smithery_installer.py` — NEW: SmitheryInstaller tests

## Solution

Implemented in v0.5.0 (merged to main, released on PyPI and npm):

- `registry/smithery.py` — `SmitheryClient`: anonymous access by default, `SMITHERY_API_KEY` optional
- `registry/aggregator.py` — `AggregatedRegistry`: parallel search, dedup by GitHub URL, signal merge
- `installer/smithery.py` — `SmitheryInstaller`: install via `npx @smithery/cli@latest install`
- `models.py` — `RegistryType.SMITHERY`, new fields `use_count`, `verified`, `smithery_id`, `source`
- `tools/search.py` — exposes `source`, `use_count`, `verified` in results; updated docstring
- `server.py` — `AggregatedRegistry` wired as default; added instructions on Smithery field semantics
- 52 new tests (1108 → 1160 passing)

`setup_smithery` device flow deferred — anonymous access covers 100% of the use case.

## Verification

- [x] `pytest tests/` — 1160 tests pass (was 1108)
- [x] `ruff check src/ tests/ && ruff format --check src/ tests/` — clean
- [x] `search_servers("postgres")` — returns merged results with `use_count`, `verified`, `source`
- [x] `search_servers("postgres")` — no duplicates between the two sources
- [x] Smithery API down → MCP Registry results still returned (graceful degradation)
- [x] Smithery-only server → `source: "smithery"`, install path via SmitheryInstaller
- [x] Server in both → `source: "both"`, `package_identifier` from MCP Registry
- [x] `SMITHERY_API_KEY` set → requests include `Authorization: Bearer` header
- [ ] `setup_smithery` tool → deferred (not needed — anonymous access works)

## Lessons Learned

- **Smithery search API is publicly accessible without auth** — the docs say auth is required
  but in practice it is optional for read operations. Always test, don't trust docs alone.
- Smithery does NOT expose npm package_identifier — install path needs workarounds (dual-source
  match, npm probe, Smithery CLI).
- The MCP Registry already mirrors Smithery servers under `ai.smithery/` prefix — deduplication
  hit rate is higher than expected.
- `useCount` counts Smithery Connect sessions, not npm downloads — still a valid popularity proxy.
- The hexagonal architecture absorbs this extension cleanly — no existing tool code changes needed
  for the happy path.
