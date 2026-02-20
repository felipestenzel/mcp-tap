# mcp-tap

**The last MCP server you install by hand.**

mcp-tap lives inside your AI assistant. Ask it to find, install, and configure
any MCP server — by talking to it. No more editing JSON files. No more
Googling environment variables.

> This is a thin Node.js wrapper that delegates to the Python package
> ([PyPI: mcp-tap](https://pypi.org/project/mcp-tap/)). It lets you use
> `npx mcp-tap` if you prefer npm-style tooling.

## Install

### Claude Desktop

Add to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "mcp-tap": {
      "command": "npx",
      "args": ["-y", "mcp-tap"]
    }
  }
}
```

### Claude Code

```bash
claude mcp add mcp-tap -- npx -y mcp-tap
```

### Cursor

Add to `.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "mcp-tap": {
      "command": "npx",
      "args": ["-y", "mcp-tap"]
    }
  }
}
```

### Windsurf

Add to `~/.codeium/windsurf/mcp_config.json`:

```json
{
  "mcpServers": {
    "mcp-tap": {
      "command": "npx",
      "args": ["-y", "mcp-tap"]
    }
  }
}
```

## How it works

This wrapper resolves the Python runtime in order:

1. **uvx** (preferred) — uv's tool runner, fast and isolated
2. **pipx run** — common Python tool runner
3. **python -m mcp_tap** — requires prior `pip install mcp-tap`

## What can mcp-tap do?

| You say | mcp-tap does |
|---------|-------------|
| "Scan my project" | Detects your tech stack, recommends MCP servers |
| "Find me an MCP for PostgreSQL" | Searches the registry, compares options |
| "Set it up" | Installs, configures, validates the connection |
| "Are my servers working?" | Health-checks every server concurrently |
| "Lock my MCP setup" | Creates `mcp-tap.lock` for reproducible configs |

## 12 Tools

`scan_project` · `search_servers` · `configure_server` · `test_connection` ·
`check_health` · `inspect_server` · `list_installed` · `remove_server` ·
`verify` · `restore` · `apply_stack`

Plus automatic lockfile management on configure/remove.

## Requirements

- Python 3.11+ (via [uv](https://docs.astral.sh/uv/), pipx, or system Python)

## Links

- **GitHub**: https://github.com/felipestenzel/mcp-tap
- **PyPI**: https://pypi.org/project/mcp-tap/
- **License**: MIT
