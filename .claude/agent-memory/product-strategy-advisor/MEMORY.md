# Product Strategy Advisor Memory -- mcp-tap

## Product
- mcp-tap: "The last MCP server you install by hand"
- Meta-MCP server for discovering, installing, configuring MCP servers
- Target: viral open-source adoption
- Differentiator: lives INSIDE the AI assistant (not CLI/web)
- See `docs/CREATIVE_BRIEF.md` for full strategy

## Codebase State (2026-02-19)
- Language: Python (despite creative brief recommending TypeScript first)
- Framework: FastMCP (mcp>=1.12.0), httpx for HTTP
- Build: hatchling, published as mcp-tap on PyPI
- Architecture: hexagonal (ports & adapters), clean layer separation
- 5 tools implemented: search_servers, configure_server, test_connection, list_installed, remove_server
- MISSING: scan_project (the headline differentiator!) -- not built at all
- MISSING: self-healing / retry logic
- MISSING: health check (batch test all servers)
- Tests: 3 test files (config, models, registry parsing) -- no tool-level integration tests
- No CI/CD pipeline yet
- Supported clients: Claude Desktop, Claude Code, Cursor, Windsurf

## Key Architecture Files
- `/src/mcp_tap/server.py` -- composition root, FastMCP wiring
- `/src/mcp_tap/models.py` -- frozen dataclasses, zero deps
- `/src/mcp_tap/errors.py` -- exception hierarchy
- `/src/mcp_tap/tools/` -- 5 tool implementations
- `/src/mcp_tap/registry/client.py` -- MCP Registry API client
- `/src/mcp_tap/config/` -- detection, reader, writer (atomic writes)
- `/src/mcp_tap/installer/` -- npm, pip, docker + resolver + subprocess
- `/src/mcp_tap/connection/tester.py` -- spawn + list_tools() validation

## Strategic Insights
- The product's #1 differentiator (scan_project) is the only Tier 1 feature NOT built
- What IS built is solid: clean architecture, atomic writes, protocol-based ports
- The existing 5 tools are essentially a CLI package manager re-wrapped as MCP tools
- Without scan_project, mcp-tap is NOT differentiated from competitors
- Self-healing is the #2 differentiator and also not built
- configure_server does NOT call install() -- it only writes config, doesn't verify package exists
- test_connection exists but no "check_health" batch tool
- No scan_project tool means the killer demo from the creative brief is impossible

## Build Order Recommendation (Tier 1)
See conversation from 2026-02-19 for detailed issue-by-issue breakdown.
Priority: scan_project first (differentiator), then end-to-end install flow, then self-healing.
