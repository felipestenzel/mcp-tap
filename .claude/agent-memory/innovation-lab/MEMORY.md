# Innovation Lab Memory -- mcp-tap

## Project: mcp-tap (MCP meta-server)
- v0.2.4, Python 3.11+, FastMCP, hexagonal architecture
- 8 tools: scan_project, search_servers, configure_server, test_connection, check_health, inspect_server, list_installed, remove_server

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
