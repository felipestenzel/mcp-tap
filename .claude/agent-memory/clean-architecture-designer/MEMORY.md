# Clean Architecture Designer Memory — mcp-tap

## Architecture
- Hexagonal (ports & adapters)
- Domain: `models.py` (frozen DCs) + `errors.py` (exception tree)
- Ports: Protocol classes in `base.py` files
- Adapters: `registry/`, `config/`, `installer/`, `connection/`
- Application: `tools/` (5 MCP tools)
- Composition root: `server.py` (wiring only)
- Dependency direction: tools → domain ← adapters
