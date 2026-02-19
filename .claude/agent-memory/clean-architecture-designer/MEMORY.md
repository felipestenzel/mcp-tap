# Clean Architecture Designer Memory -- mcp-tap

## Architecture Audit (2026-02-19) -- Score: 6.7/10

### Structure
- Hexagonal (ports & adapters), 8 MCP tools, ~20 source modules
- Domain: `models.py` (frozen DCs) + `errors.py` (exception tree)
- Only 1 Port: `PackageInstaller` Protocol in `installer/base.py`
- Adapters: `registry/`, `config/`, `installer/`, `connection/`, `scanner/`, `evaluation/`, `inspector/`, `healing/`
- Application: `tools/` (8 MCP tools)
- Composition root: `server.py` (incomplete -- only wires httpx + RegistryClient)
- Dependency direction: tools -> domain <- adapters (mostly correct)

### Key Violations Found
1. resolver.py L11 shadows Protocol with Union: `PackageInstaller = Npm|Pip|Docker`
2. Tools import concrete adapters directly (no DI via ports)
3. RegistryClient is the only dataclass without `frozen=True, slots=True`
4. 6+ fields use `str` where enums should exist (scope, status, priority, tier)
5. `remove.py` uses `object` type annotation instead of `ConfigLocation`
6. `detection.py` uses lowercase `callable` without generics
7. Client resolution logic duplicated in 4 tools
8. `_parse_env_vars` breaks on values containing commas

### Missing Ports (priority order)
- RegistryPort, ConfigReaderPort/WriterPort, ConnectionTesterPort
- MetadataFetcherPort, ClientDetectorPort, ReadmeFetcherPort

### Tests: 498 passing, 1.42s
- Patch-heavy (3-5 @patch per tool test) -- symptom of missing DI
- No integration tests, no contract tests for Protocol
- Good parametrized coverage on classifier/fixer/models

### Top 5 Recommendations
1. Define Protocols for all adapter boundaries
2. Convert magic strings to enums
3. Build real composition root in server.py
4. Extract shared `resolve_client_location()` helper
5. Add integration tests with real config file fixtures
