# Performance Optimizer Memory -- mcp-tap

## Project: mcp-tap (Python async MCP server)
- httpx for HTTP, asyncio subprocess for process management
- FastMCP server framework, hexagonal architecture
- 8 MCP tools: scan_project, search_servers, configure_server, test_connection, check_health, inspect_server, list_installed, remove_server

## Architecture Audit (2026-02-19)
See `audit-findings.md` for full details.

### Critical Findings
1. Config file race condition in `config/writer.py` -- no file locking, shared `.tmp` path
2. GitHub API 60/hr rate limit with no caching, no rate limiting in `evaluation/github.py`
3. Subprocess children may survive parent kill in `installer/subprocess.py`
4. `check_health` spawns ALL servers simultaneously with no concurrency limit

### High Findings
5. No HTTP retry logic anywhere (registry, GitHub, README fetches)
6. Healing loop can spawn up to 7 processes per server
7. Config reader uses blocking I/O in async context
8. `_apply_maturity` in search deduplicates but still fetches per-URL

### Key File Paths
- HTTP client lifecycle: `server.py:app_lifespan`
- Subprocess wrapper: `installer/subprocess.py:run_command`
- Config write: `config/writer.py:_atomic_write`
- Connection test: `connection/tester.py:test_server_connection`
- Health check: `tools/health.py:_check_all_servers`
- GitHub API: `evaluation/github.py:fetch_repo_metadata`
- Healing loop: `healing/retry.py:heal_and_retry`
