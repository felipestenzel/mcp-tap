# Dynamic Discovery Engine — "You didn't know you needed this"

- **Date**: 2026-02-20
- **Status**: `done`
- **Branch**: `feature/2026-02-20-dynamic-discovery`
- **Priority**: `high`

## Problem

`scan_project` detects ~30 technologies but only recommends from a **hardcoded map of 13 servers**. The MCP Registry has hundreds of servers. We're leaving massive value on the table.

**Quantified gap:**
- 24 unique technologies detected by scanner
- 17 of 24 produce **zero recommendations**
- Entire categories missing: productivity (Notion, Jira, Linear), observability (Sentry, Datadog), cloud (GCP, Azure full), AI/ML (OpenAI, HuggingFace), payments (Stripe), auth (Clerk, Auth0)
- Technologies like Docker, Terraform, Ansible are detected in CI/CD but never recommended

The `search_servers` tool queries the registry dynamically — but `scan_project` doesn't use it. Two disconnected worlds.

## Context

- Affected modules: `scanner/`, `tools/scan.py`, `tools/search.py`, `registry/`
- Architecture: hexagonal — `RegistryClientPort` already supports async queries
- The MCP ecosystem is growing fast — new servers daily
- Competitors will emerge; discovery quality is the moat

## Key Insight: The LLM Is Already There

mcp-tap runs inside an LLM client (Claude, GPT, Cursor, Windsurf). The host LLM has:
- World knowledge about technologies, services, and workflows
- Reasoning ability to connect "you have Sentry SDK → you care about error monitoring → here's a server for that"
- Conversational ability to ask the user follow-up questions

**We should NOT try to replicate LLM reasoning in Python scoring logic.** Instead, we should give the LLM **richer data and structured hints** so IT can make better recommendations. Our job is to be the LLM's eyes into the MCP ecosystem, not its brain.

## Solution: Three-Layer Discovery

### Layer 1 — Expand Static Map (Quick Win, High Confidence)

Expand `TECHNOLOGY_SERVER_MAP` from 13 to ~30-40 entries. Add:
- GCP, Azure cloud servers
- Docker, Terraform, Ansible infrastructure servers
- Sentry, Datadog observability servers
- Notion, Linear, Jira productivity servers
- Stripe, Supabase, Firebase SaaS servers

Also expand **dependency detection** with `@org/` prefix patterns:
```python
# ~30 regex patterns cover 90% of service SDKs
"@sentry/" → sentry
"@stripe/" → stripe
"@supabase/" → supabase
"@clerk/" → clerk
"@auth0/" → auth0
"@datadog/" → datadog
"@notionhq/" → notion
"@linear/" → linear
```

These are curated, high-confidence, editorial-control recommendations.

### Layer 2 — Dynamic Registry Bridge (The Power Move)

For each detected technology that **has no static mapping**, query the registry dynamically:

```python
async def recommend_servers(profile, client, registry_client):
    recommendations = []

    # Layer 1: static map (fast, curated)
    for tech in profile.technologies:
        if tech.name in TECHNOLOGY_SERVER_MAP:
            recommendations.append(static_recommendation(tech))
        else:
            # Layer 2: dynamic query (async, broader)
            results = await registry_client.search(tech.name, limit=5)
            if results:
                recommendations.append(dynamic_recommendation(tech, results))

    return recommendations
```

Dynamic results get a `source: "registry"` tag (vs `source: "curated"`) so the LLM can weigh confidence differently.

### Layer 3 — Discovery Hints (The Killer Differentiator)

This is where we leverage the host LLM. Add a `discovery_hints` field to scan output:

```json
{
  "recommendations": [...],
  "discovery_hints": [
    {
      "type": "workflow_inference",
      "trigger": "sentry SDK detected in dependencies",
      "suggestion": "User cares about error monitoring. Search for 'error tracking' or 'observability' MCP servers.",
      "search_queries": ["sentry", "error monitoring", "observability"]
    },
    {
      "type": "stack_archetype",
      "detected_pattern": "Next.js + Supabase + Stripe",
      "archetype": "SaaS Application",
      "suggestion": "Typical SaaS stacks benefit from auth, payments, and analytics servers.",
      "search_queries": ["authentication", "payments", "analytics"]
    },
    {
      "type": "unmapped_technology",
      "technology": "terraform",
      "confidence": 0.8,
      "suggestion": "Terraform detected in CI/CD workflows but no known MCP server mapped. Search the registry or check community servers.",
      "search_queries": ["terraform", "infrastructure as code"]
    },
    {
      "type": "env_var_hint",
      "variable": "OPENAI_API_KEY",
      "suggestion": "OpenAI API key found. There may be MCP servers for AI model management or prompt engineering.",
      "search_queries": ["openai", "llm", "ai"]
    }
  ]
}
```

**Why this is killer**: The LLM reads these hints and can:
1. Autonomously call `search_servers` for each suggested query
2. Reason about which results are actually useful for this user
3. Ask the user questions like "I see you use Sentry — do you also want Datadog integration?"
4. Connect dots that no static map ever could

The LLM becomes a **discovery partner**, not a passive tool executor.

### Stack Archetypes (Bonus, Layer 3 extension)

Detect common technology combinations and label them:

```python
STACK_ARCHETYPES = {
    "saas_app": {
        "signals": [("next.js", "react", "vue"), ("supabase", "firebase", "auth0"), ("stripe",)],
        "min_matches": 2,
        "label": "SaaS Application",
        "extra_queries": ["authentication", "payments", "analytics", "email"]
    },
    "data_pipeline": {
        "signals": [("postgresql", "mongodb"), ("redis", "rabbitmq", "kafka"), ("python",)],
        "min_matches": 2,
        "label": "Data Pipeline",
        "extra_queries": ["data processing", "etl", "queue", "scheduling"]
    },
    "devops_infra": {
        "signals": [("docker", "kubernetes"), ("terraform", "ansible"), ("aws", "gcp", "azure")],
        "min_matches": 2,
        "label": "DevOps/Infrastructure",
        "extra_queries": ["cloud", "deployment", "monitoring", "logging"]
    }
}
```

## Implementation Plan

### Phase A — Expand Detection + Static Map (Size: S)
1. Add `@org/` prefix patterns to `scanner/detector.py`
2. Expand `TECHNOLOGY_SERVER_MAP` in `scanner/recommendations.py` to ~35 entries
3. Add credential mappings for new services in `scanner/credentials.py`
4. Tests for new detections

### Phase B — Dynamic Registry Bridge (Size: M)
1. Make `recommend_servers()` async (it's currently sync)
2. Add `RegistryClientPort` parameter to recommendation flow
3. Query registry for unmapped technologies
4. Add `source` field to `ServerRecommendation` model
5. Add timeout/fallback (static-only if registry is slow)
6. Tests with mocked registry responses

### Phase C — Discovery Hints + Archetypes (Size: M)
1. Add `DiscoveryHint` dataclass to `models.py`
2. Implement hint generators:
   - `workflow_inference` — dependency → workflow concern → search queries
   - `stack_archetype` — tech combination → archetype label → extra queries
   - `unmapped_technology` — detected tech with no server → suggest search
   - `env_var_hint` — env vars suggesting services → suggest search
3. Add `discovery_hints` to scan output
4. Add `next_actions` field with structured LLM instructions
5. Tests for hint generation

### Phase D — Quality Gate for Dynamic Results (Size: S)
1. Use existing maturity scoring to filter dynamic results
2. Skip archived repos, very low stars, very old last-commit
3. Prefer official servers over community when both exist
4. Add `confidence` field to dynamic recommendations

## Non-Goals (Explicitly Out of Scope)

- **No community intelligence scraping** (awesome-lists, npm search) — too complex for now, registry is growing fast enough
- **No LLM calls from within mcp-tap** — we leverage the HOST LLM, not call one ourselves
- **No breaking changes to existing scan output** — hints and dynamic results are additive fields

## Files Changed

- `src/mcp_tap/models.py` — Add `DiscoveryHint`, `StackArchetype` dataclasses; add `source` field to recommendation
- `src/mcp_tap/scanner/detector.py` — Add `@org/` prefix pattern detection
- `src/mcp_tap/scanner/recommendations.py` — Expand static map; make async; add registry bridge
- `src/mcp_tap/scanner/archetypes.py` — NEW: stack archetype detection
- `src/mcp_tap/scanner/hints.py` — NEW: discovery hint generators
- `src/mcp_tap/scanner/credentials.py` — Expand credential compatibility maps
- `src/mcp_tap/tools/scan.py` — Wire up dynamic discovery + hints in output
- `tests/` — Tests for all new modules

## Verification

- [x] Tests pass: `pytest tests/` — 1085 passed (933 original + 152 new)
- [x] Linter passes: `ruff check src/ tests/` + `ruff format --check`
- [x] `scan_project` outputs discovery_hints, archetypes, suggested_searches
- [x] Archetype detection works (6 archetypes: SaaS, Data Pipeline, DevOps, AI/ML, Monorepo, E-Commerce)
- [x] Dynamic results have `source: "registry"` tag
- [x] Scan still works when registry is unreachable (5s timeout, silent fallback)
- [x] No new dependencies added (uses existing httpx + registry client)

## Lessons Learned

- **The strategic advisor was right about Layer 2 risk** but the architecture designer showed it's manageable with timeouts. Implemented as opt-in with 5s timeout per query.
- **@org/ prefix patterns are the highest-leverage detection change** — 24 patterns cover hundreds of packages with 8 lines of matching logic.
- **Pure function modules (archetypes.py, hints.py) are trivially testable** — zero mocking needed, just pass data in and assert data out.
- **Backward compatibility via defaults** — all new fields on ServerRecommendation and ProjectProfile have defaults, so zero existing tests broke.

## Strategic Notes

**Why this is the right next thing:**
- Discovery quality is the competitive moat — easily the highest-impact feature
- Leveraging the host LLM is a unique advantage that competitors can't easily replicate
- Phases A→B→C are independently shippable — each adds value alone
- No architecture changes needed — hexagonal structure already supports this

**Intelligence split:**
- **mcp-tap (Python)**: detection, registry querying, data enrichment, quality gating
- **Host LLM**: reasoning, connecting dots, conversational discovery, user intent
- We are the LLM's **eyes into the MCP ecosystem**, not its brain
