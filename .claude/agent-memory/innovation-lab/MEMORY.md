# Innovation Lab Memory -- mcp-tap

## Project: mcp-tap (MCP meta-server)
- v0.3.3, Python 3.11+, FastMCP, hexagonal architecture
- 12 tools: scan_project, search_servers, configure_server, test_connection, check_health, inspect_server, list_installed, remove_server, verify, restore, apply_stack + lockfile hooks

## Strategic Research (2026-02-19)

### Ecosystem State (Feb 2026)
- ~20,000 MCP servers exist, 17+ registries/directories
- Official MCP Registry launched preview Sep 2025
- Key competitors: mcp-sync (cross-client sync), mcp-compose (Docker orchestration), MetaMCP (aggregator/gateway), Docker MCP Gateway (official), mcp-scan/Snyk (security)
- Observability: Sentry, Datadog, Grafana, Moesif all have MCP monitoring
- Security: OWASP MCP Top 10 published, mcp-scan, MCPGuard, Enkrypt exist
- See `strategic-research-2026-02.md` for full analysis

### Category-Defining Position
mcp-tap = "npm for MCP" (not just a registry). Complete lifecycle manager from inside the conversation.
Differentiation: conversational, project-aware, self-healing, NO context switching.

### Prioritized Features (VERDE = Build)
1. **MCP Lockfile** (`mcp-tap.lock`) -- reproducibility + security (OWASP MCP03/04). NO competitor does this. First mover = defines format. Effort: M.
2. **Security Gate at Install** -- warnings during configure_server (repo age, credential type, open security issues, OWASP checks). Effort: M.
3. **Workflow Understanding** -- extend scan_project with git history, CI config, dotfiles analysis. Effort: M.
4. **Stacks/Profiles** (`.mcp-tap.yaml`) -- named server bundles, conversational creation, exportable. Effort: M.
5. **Tool Conflict Detection** -- detect duplicate tool names across installed servers. Effort: S.

### Monitored (AMARELO)
- Zero-touch autopilot (needs MCP spec evolution for server-initiated requests)
- Context budget optimization (needs usage telemetry or proxy position)
- Meta-aggregation of registries (saturated market)
- Sync check / diff between clients (mcp-sync exists)

### Rejected (VERMELHO)
- Full observability/proxy (compete with Sentry/Datadog/Grafana -- wrong positioning)
- Bidirectional cross-client sync (mcp-sync already solves this well)
- Custom rating system (too many registries already, effort disproportionate to gain)

### Proposed Roadmap
- v0.3: Lockfile + Security Gate
- v0.4: Stacks + Workflow Understanding
- v0.5: Conflict Detection + Context Budget

## Discovery Pipeline Analysis (2026-02-20)
- Current bottleneck: TECHNOLOGY_SERVER_MAP has 13 entries, scanner detects 24 tech names, 17 have NO recommendations
- Registry has hundreds of servers, search API only supports substring matching (no tags/categories)
- Common services in registry but NOT detected: sentry, stripe, supabase, firebase, notion, linear, figma, datadog, vercel
- Key architectural insight: recommend_servers() is sync, pure static lookup. Making it async + injecting RegistryClientPort unlocks dynamic search.
- LLM-in-the-loop strategy: return `discovery_hints` and `next_actions` in scan output to guide autonomous follow-up searches
- See detailed analysis in conversation from 2026-02-20
- Priority build order: (1) dynamic registry bridge, (2) LLM discovery hints, (3) workflow inference, (4) archetype detection, (5) publisher pattern detection, (6) progressive discovery, (7) community intelligence
- Archetypes to detect: "Next.js SaaS", "Python API Backend", "Data Pipeline", "Infrastructure Heavy"
- Pattern-based publisher detection via @org/ prefixes covers ~90% of common services without hardcoding each package

## Dynamic Discovery Engine Deep Dive (2026-02-20)
- Full analysis at: `docs/experiments/2026-02-20_dynamic-discovery-deep-dive.md`
- Current state: 94 detection patterns, 13 recommendation entries, 17/24 techs unmapped
- Proposed: 350+ detection patterns, 50+ recommendation entries
- 6 key expansion areas: @org/ prefix matching (30 patterns), expanded Python deps (+30), platform file detection (+47), directory detection (+15), env var patterns (+29), scripts mining (+19)
- 10 stack archetypes defined: SaaS, API Backend, Data Pipeline, DevOps, AI/ML, Monorepo, JAMStack, Mobile Backend, E-Commerce, Docs/Knowledge
- 8 discovery hint types (up from 4): workflow_inference, stack_archetype, unmapped_technology, env_var_hint, deployment_target, missing_complement, file_structure_hint, monorepo_workspace
- Wild ideas that work: confidence stacking (probability union), package.json scripts mining, next_actions choreography, missing complement hints
- Registry API observed returning empty results (2026-02-20) -- confirms need for robust static map
- Phase order: (1) detection expansion, (2) static map expansion, (3) hints+archetypes, (4) dynamic bridge
- All new model fields are additive with defaults -- backward compatible
- Implementation: ~350 lines of new detection patterns, ~200 lines archetypes, ~300 lines hints

## Lockfile Spec Decisions (2026-02-19)
- Spec at: `docs/specs/mcp-tap-lockfile-v1.md`
- Format: JSON (ecosystem alignment, no new deps)
- File: `mcp-tap.lock` in project root, COMMITTED to git
- `env_keys` only (NEVER values) -- enforced at model level
- `tools_hash` = sha256 of sorted pipe-joined tool names for fast drift detection
- `integrity` = sha256 of package (npm registry, PyPI JSON API, OCI manifest)
- Lockfile updated as side effect of existing tools (configure, remove, health, test)
- New tools planned: `restore` (recreate setup) + `verify` (drift detection)
- New package: `src/mcp_tap/lockfile/` (reader, writer, hasher, differ)
- 3-phase implementation: Core -> Verification -> Restore
- v1 is advisory (warn on drift), v2 adds strict mode (`--frozen`)
- Prior art studied: npm package-lock.json, deno.lock, Terraform .terraform.lock.hcl
