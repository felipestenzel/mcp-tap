# Python Craftsman Memory — mcp-tap

## Project
- mcp-tap: Python 3.11+ MCP meta-server
- Build: hatchling | Linter: ruff (line-length=100)
- All dataclasses: `frozen=True, slots=True`
- All I/O: async (httpx, asyncio subprocess)
- Imports: always `from __future__ import annotations`
- `PackageInstaller` Protocol in `installer/base.py`
