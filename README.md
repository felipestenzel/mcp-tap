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

<!-- tabs: uvx (recommended), npx -->

**With uvx** (recommended):

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

**With npx**:

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
# With uvx (recommended)
claude mcp add mcp-tap -- uvx mcp-tap

# With npx
claude mcp add mcp-tap -- npx -y mcp-tap
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

Or use `npx` — replace `"command": "uvx", "args": ["mcp-tap"]` with `"command": "npx", "args": ["-y", "mcp-tap"]`.

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

Or use `npx` — replace `"command": "uvx", "args": ["mcp-tap"]` with `"command": "npx", "args": ["-y", "mcp-tap"]`.

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
| `scan_project` | Scans your project directory — detects languages, frameworks, databases, CI/CD pipelines — and recommends MCP servers |
| `search_servers` | Searches the MCP Registry with semantic intent rerank (`intent_match_score`), maturity scoring, and project relevance ranking |
| `configure_server` | Installs a package (npm/pip/docker), runs a security gate, validates the connection, and writes config |
| `test_connection` | Spawns a server process, connects via MCP protocol, and lists its tools. Auto-heals on failure |
| `check_health` | Tests all configured servers concurrently, detects tool conflicts between servers |
| `inspect_server` | Fetches a server's README and extracts configuration hints |
| `list_installed` | Shows all configured servers with secrets masked (layered detection: key names, prefixes, high-entropy) |
| `remove_server` | Removes a server from one or all client configs |
| `verify` | Compares `mcp-tap.lock` against actual config — detects drift |
| `restore` | Recreates server configs from a lockfile (like `npm ci` for MCP) |
| `apply_stack` | Installs a group of servers from a shareable stack profile |

Plus automatic lockfile management on every configure/remove.

## Features

- **Project-aware**: Scans your codebase — including CI/CD configs (GitHub Actions, GitLab CI) — to recommend servers based on your actual stack
- **Security gate**: Blocks suspicious install commands, archived repos, and known-risky patterns before installing
- **Lockfile**: `mcp-tap.lock` tracks exact versions and hashes of all your MCP servers. Reproducible setups across machines
- **Stacks**: Shareable server profiles — install a complete Data Science, Web Dev, or DevOps stack in one command
- **Multi-client**: Configure Claude Desktop, Claude Code, Cursor, and Windsurf — all at once or individually
- **Auto-healing**: Failed connections are automatically diagnosed and fixed when possible
- **Tool conflict detection**: Warns when two servers expose overlapping tools that could confuse the LLM
- **Connection validation**: Every install is verified with a real MCP connection test
- **Secrets masked**: `list_installed` never exposes environment variable values
- **Recommendation quality gate**: Offline benchmark (`precision@k`, `acceptance_rate`) keeps recommendation quality stable in CI
- **Production feedback loop (opt-in)**: Privacy-safe telemetry (`recommendations_shown`, accepted/rejected/ignored) with version-segmented quality trends
- **Semantic rerank**: Broad queries (for example `error monitoring`) are reranked by intent match, not only popularity

## Requirements

- Python 3.11+ with [`uv`](https://docs.astral.sh/uv/) (recommended), **or**
- Node.js 18+ (the npm package is a thin wrapper that calls the Python package via `uvx`/`pipx`)
- Officially tested in CI on Python 3.11, 3.12, 3.13, and 3.14

## Quality Gate

Run the recommendation benchmark locally:

```bash
uv run python -m mcp_tap.benchmark.recommendation
```

Dataset: `src/mcp_tap/benchmark/recommendation_dataset_v1.json`.

## Production Feedback Loop (Opt-In)

Enable telemetry explicitly before collecting production recommendation feedback:

```bash
export MCP_TAP_TELEMETRY_OPT_IN=true
export MCP_TAP_TELEMETRY_FILE=.mcp-tap/recommendation_feedback.jsonl
```

Generate a quality report from collected events:

```bash
uv run python -m mcp_tap.benchmark.production_feedback --events .mcp-tap/recommendation_feedback.jsonl --top-k 3
```

The telemetry payload is privacy-safe by default:
- project path is stored as hash fingerprint (no raw path)
- no source code, secrets, or env var values are recorded
- release trends include drift warnings/failures between versions

## License

MIT
