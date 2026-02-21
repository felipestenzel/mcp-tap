# Clean Architecture Designer Memory -- mcp-tap

## Architecture Audit (2026-02-19, updated 2026-02-20)

### Structure
- Hexagonal (ports & adapters), 12 MCP tools, ~30 source modules
- Domain: `models.py` (frozen DCs + StrEnums) + `errors.py` (exception tree)
- Ports: 8 Protocols across packages (RegistryClientPort, ConnectionTesterPort, etc.)
- Adapters: `registry/`, `config/`, `installer/`, `connection/`, `scanner/`, `evaluation/`, `inspector/`, `healing/`, `security/`
- Application: `tools/` (12 MCP tools)
- Composition root: `server.py` -- `AppContext` frozen DC with 8 injected adapters
- Dependency direction: tools -> models <- adapters (mostly correct)

### Key Patterns
- `AppContext` in server.py holds all Tier B (stateful/IO) adapters
- Tools extract AppContext via `get_context(ctx)` from `tools/_helpers.py`
- Tier A (stateless) adapters imported directly (no DI wrapping)
- `scanner/recommendations.py` is SYNC -- needs async for registry bridge
- `tools/scan.py` does NOT currently access AppContext (unlike search/configure/etc.)

### Remaining Violations
1. `RegistryClient` dataclass missing `frozen=True, slots=True`
2. `ServerRecommendation.priority` is `str` not `StrEnum`
3. `_parse_env_vars` in configure tool breaks on values containing commas
4. Some magic strings remain (status fields, tier values)

### Dynamic Discovery Engine Design (2026-02-20)
- Issue: `docs/issues/2026-02-20_dynamic-discovery-engine.md`
- 3 Layers: L1=expand static map, L2=async registry bridge, L3=hints+archetypes
- New domain models: `RecommendationSource(StrEnum)`, `HintType(StrEnum)`, `DiscoveryHint`, `StackArchetype`
- Modified: `ServerRecommendation` gets `source` + `confidence`; `ProjectProfile` gets `discovery_hints` + `archetypes`
- New port: `RecommendationEnginePort` in `scanner/base.py`
- Key decision: Pass `RegistryClientPort` (existing port) into `recommend_servers()` -- NOT concrete adapter
- New modules: `scanner/archetypes.py` (pure), `scanner/hints.py` (pure)
- Async migration: Only 2 files (`recommendations.py` + `detector.py`); small blast radius
- Wiring: `tools/scan.py` extracts `app.registry` from AppContext (same as `tools/search.py`)
- Fallback: 5s timeout on registry queries, empty list on failure, static always available
- No changes to server.py: AppContext already has `registry: RegistryClientPort`

### Tests: 933 passing
- Patch-heavy in tool tests -- partially mitigated by AppContext DI
- `tools/scan.py` tests will need update to mock AppContext when registry bridge is wired
