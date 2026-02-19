# Product Strategy Advisor Memory -- mcp-tap

## Product
- mcp-tap: "The last MCP server you install by hand"
- Meta-MCP server for discovering, installing, configuring MCP servers
- Target: viral open-source adoption
- Differentiator: lives INSIDE the AI assistant (not CLI/web)
- See `docs/CREATIVE_BRIEF.md` for full strategy

## Codebase State (2026-02-19, UPDATED)
- Language: Python 3.11+ | Framework: FastMCP (mcp>=1.12.0), httpx
- Build: hatchling, published as mcp-tap on PyPI (v0.2.4)
- Architecture: hexagonal, clean layer separation, 5,089 LOC in src/
- ALL 8 tools implemented (scan_project, search_servers, configure_server, test_connection, check_health, inspect_server, list_installed, remove_server)
- Self-healing: BUILT (healing/ module with classifier, fixer, retry loop)
- Maturity scoring: BUILT (evaluation/ module with GitHub API signals)
- Credential mapping: BUILT (scanner/credentials.py)
- Inspector/README extraction: BUILT (inspector/ module)
- Native capability filtering: BUILT (per-client redundancy detection)
- Tests: 498 passing across 21 test files
- Supported clients: Claude Desktop, Claude Code, Cursor, Windsurf

## Competitive Landscape (2026-02-19)
- mcp-installer (anaisbetts): 1,504 stars, DEAD (last push 2024-11-26)
- mcpm.sh (pathintegral-institute): 891 stars, active CLI, profiles/router
- Smithery CLI: 501 stars, web registry + CLI + managed hosting
- Composio: Managed platform, 250+ servers, enterprise play
- Glama: Hosted gateway model
- mcp-tap: 0 stars, 0 forks (repo created same day as all development)

## Critical Facts
- ALL 31 commits from same day (2026-02-19) -- entire project built in one session
- Already hit breaking API change (Registry API format shifted, fixed same day)
- Feature-complete MVP but ZERO users/adoption
- "Inside the assistant" positioning IS genuinely unique vs CLI competitors
- MCP ecosystem: 5,800+ servers, >50% low-quality

## Key Risk: Platform Dependency on MCP Registry API (unversioned, already broke once)
