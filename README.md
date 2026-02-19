# mcp-tap

**The last MCP server you install by hand.**

mcp-tap lives inside your AI assistant. Ask it to find, install, and configure
any MCP server — by talking to it. No more editing JSON files. No more
Googling environment variables. No more "why won't this connect?"

> "Find me an MCP for PostgreSQL."

That's it. mcp-tap searches the registry, installs the package, generates the
config, validates the connection — all through conversation.

## Before mcp-tap

1. Google "MCP server for postgres"
2. Find 4 competing packages, compare stars and last commit dates
3. Pick one, read the README
4. Figure out the right `command`, `args`, and `env` values
5. Manually edit `claude_desktop_config.json` (or `mcp.json`, or `mcp_config.json`...)
6. Realize you need a `POSTGRES_CONNECTION_STRING` environment variable
7. Find your connection string, add it to the config, restart the client
8. Get "connection refused", debug for 20 minutes
9. Finally works. Repeat for every server. Repeat for every client.

## After mcp-tap

```
You: "Set up MCP servers for my project."

mcp-tap: I scanned your project and found:
  - PostgreSQL (from docker-compose.yml)
  - Slack (SLACK_BOT_TOKEN in your .env)
  - GitHub (detected .github/ directory)

  I recommend 3 servers. Want me to install them?

You: "Yes, all of them."

mcp-tap: Done. All connections verified. 35 new tools available.
```

## Install

You install mcp-tap once. It installs everything else.

### Claude Desktop

Add to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "mcp-tap": {
      "command": "uvx",
      "args": ["mcp-tap"]
    }
  }
}
```

### Claude Code

```bash
claude mcp add mcp-tap -- uvx mcp-tap
```

### Cursor

Add to `.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "mcp-tap": {
      "command": "uvx",
      "args": ["mcp-tap"]
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
      "command": "uvx",
      "args": ["mcp-tap"]
    }
  }
}
```

## What can it do?

| You say | mcp-tap does |
|---------|-------------|
| "Scan my project and recommend MCP servers" | Detects your tech stack, shows what's missing |
| "Find me an MCP for PostgreSQL" | Searches the registry, compares options |
| "Set up the official postgres server" | Installs, configures, validates the connection |
| "Set it up on all my clients" | Configures Claude Desktop, Cursor, and Windsurf at once |
| "What MCP servers do I have?" | Lists all configured servers across clients |
| "Are my MCP servers working?" | Health-checks every server concurrently |
| "Test my postgres connection" | Spawns the server, connects, lists available tools |
| "Remove the slack MCP" | Removes from config cleanly |

## Tools

| Tool | What it does |
|------|-------------|
| `scan_project` | Scans your project directory, detects languages/frameworks/databases, recommends MCP servers |
| `search_servers` | Searches the MCP Registry by keyword, optionally ranked by project relevance |
| `configure_server` | Installs a package (npm/pip/docker) and writes config to one or all clients |
| `test_connection` | Spawns a server process, connects via MCP, and lists its tools |
| `check_health` | Tests all configured servers concurrently, reports healthy/unhealthy/timeout |
| `list_installed` | Shows all configured servers with their commands and environment variables (secrets masked) |
| `remove_server` | Removes a server from one or all client configs |

## Features

- **Project-aware**: Scans your codebase to recommend servers based on your actual stack
- **Multi-client**: Configure Claude Desktop, Claude Code, Cursor, and Windsurf — all at once or individually
- **Project-scoped configs**: Use `scope="project"` to write `.mcp.json` for team-shared setups
- **Connection validation**: Every install is verified with a real MCP connection test
- **Health monitoring**: Check all your servers in one command
- **Secrets masked**: `list_installed` never exposes environment variable values

## Requirements

- Python 3.11+
- [`uv`](https://docs.astral.sh/uv/) (recommended) or `pip`

## License

MIT
