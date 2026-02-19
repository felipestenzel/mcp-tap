# MCP Meta-Server: Creative Brief & Launch Strategy

## Experiment: Naming, Positioning, and Launch Strategy for a Meta-MCP Server

### Problem
The MCP ecosystem has thousands of servers but no good way to discover, install, and configure them from *inside* the AI assistant itself. Existing tools (mcp-get, install-mcp, mcpm, Smithery) are either CLI tools or web registries. None of them live where the user already is: inside the conversation.

### Hypothesis
A meta-MCP server that lives inside the AI assistant can achieve viral open-source adoption by (a) having a killer name, (b) delivering a "zero to hero" demo in 60 seconds, and (c) offering features that only an in-assistant tool can provide (project analysis, conversational setup, self-healing).

---

## 1. NAMING

### Competitive Landscape (taken names)

| Name | Status | What it is |
|------|--------|-----------|
| `mcp-get` | TAKEN (deprecated) | CLI package manager, now points to Smithery |
| `mcp-installer` | TAKEN | Meta-MCP by @anaisbetts, basic install only |
| `mcp-hub` / `mcphub` | TAKEN (multiple) | Gateway/proxy servers, Neovim plugin |
| `mcp-forge` | TAKEN (3 repos!) | Server scaffolding/generation tools |
| `mcpm` / `@mcpm/cli` | TAKEN | CLI package manager with profiles |
| `mcpx` / `@dylibso/mcpx` | TAKEN | XTP MCP server by Dylibso |
| `mcpilot` / `MCPilot` | TAKEN | FastAPI gateway + npm task executor |
| `smithery` | TAKEN | Web registry (7,300+ servers) |
| `install-mcp` | TAKEN | CLI by supermemory.ai |
| `mcp-framework` | TAKEN | Server building framework |
| `fastmcp` | TAKEN | Python server building library |

### Available Names (verified not on npm or PyPI as of 2026-02-19)

#### Tier 1: Strong Recommendations

| Name | npm | pypi | GitHub repo | Why it works |
|------|-----|------|-------------|-------------|
| **`mcp-tap`** | Available | Available | Available | Like "tapping" into a keg of tools. Short. Verb-first ("tap into any tool"). Evokes homebrew's `brew tap`. Unix culture. |
| **`mcp-dock`** | Available | Available | Available | Tools "dock" into your assistant. Short. Visual metaphor (docking bay). Easy to type. Docker-adjacent without confusion. |
| **`mcp-scout`** | Available | Available | web-scout-mcp exists but different | Scouts ahead, finds what you need. Active verb energy. Friendly personality. |

#### Tier 2: Solid Alternatives

| Name | Why it works | Risk |
|------|-------------|------|
| `mcp-pilot` | "Autopilot for MCP setup" | MCPilot exists (FastAPI gateway), could confuse |
| `mcp-plug` | "Plug in any tool" | Slightly generic |
| `mcp-kit` | "Your MCP toolkit" | A bit bland |
| `mcp-brew` | Homebrew parallel | Could imply macOS-only |
| `mcp-shelf` | Tools on a shelf, pick what you need | Less active energy |

#### Tier 3: Bold/Unconventional

| Name | Concept | Risk |
|------|---------|------|
| `toolrack` | A rack of tools you pull from | Loses "MCP" in the name |
| `plumb` | Plumbing -- connecting pipes (MCPs) together | Too obscure? |
| `mcpd` | The MCP daemon -- always running, always ready | Looks like a typo |

### THE RECOMMENDATION: `mcp-tap`

**Why `mcp-tap` wins:**

1. **Verb energy.** "Tap" is active. You tap a resource. You tap into power. It implies unlocking something that was already there.

2. **Homebrew resonance.** Every macOS developer knows `brew tap` -- adding a new source of packages. `mcp-tap` is the same mental model: tap into the MCP ecosystem from inside your assistant.

3. **Short.** 7 characters. Easy to type, easy to say, easy to remember.

4. **Works as a command.** "Hey Claude, use mcp-tap to find me a PostgreSQL server." Natural.

5. **Works as a package name.** `npx mcp-tap` / `uvx mcp-tap` / `pip install mcp-tap` -- all clean.

6. **Works as a repo name.** `github.com/hive-agent-framework/mcp-tap` -- clean URL.

7. **Tagline writes itself.** "Tap into any tool." / "One tap, every tool." / "Tap. Connect. Build."

8. **Not taken anywhere.** Clean on npm, PyPI, and GitHub.

**Runner-up: `mcp-dock`** -- stronger visual metaphor (tools docking into your assistant) but slightly less action-oriented.

---

## 2. README FIRST PAGE

The first 10 seconds determine whether someone stars the repo or closes the tab. Here is the full opening section:

```markdown
# mcp-tap

**The last MCP server you install by hand.**

mcp-tap lives inside your AI assistant. Ask it to find, install, and configure
any MCP server -- by talking to it. No more editing JSON files. No more
Googling environment variables. No more "why won't this connect?"

> "Find me an MCP for PostgreSQL."

That's it. mcp-tap scans your project, searches the registry, reads the docs,
generates the config, collects credentials, installs the server, validates the
connection, and fixes it if something breaks. All through conversation.

## Before mcp-tap

1. Google "MCP server for postgres"
2. Find 4 competing packages, compare stars and last commit dates
3. Pick one, read the README
4. Figure out the right `command`, `args`, and `transport` values
5. Manually edit `claude_desktop_config.json` (or `mcp_servers.json`)
6. Realize you need a `POSTGRES_CONNECTION_STRING` environment variable
7. Figure out the format, find your connection string
8. Add it to the config, restart Claude Desktop
9. Get "connection refused", debug for 20 minutes
10. Finally works. Repeat for every server.

## After mcp-tap

```
You: "Set up MCP servers for my project."

mcp-tap: I scanned your project and found:
  - PostgreSQL (from docker-compose.yml)
  - Slack (SLACK_BOT_TOKEN in your .env)
  - GitHub (detected .github/ directory)

  I recommend 3 servers. Here's why...
  [presents options with tradeoffs]

You: "Install all three."

mcp-tap: Done. 35 new tools available.
  All connections verified.
```

## Install

You install mcp-tap once. It installs everything else.

**Claude Desktop** -- add to `claude_desktop_config.json`:
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

**Cursor / Windsurf / any MCP client:**
```json
{
  "mcp-tap": {
    "command": "npx",
    "args": ["-y", "mcp-tap"]
  }
}
```

That's it. Now ask your assistant: *"What MCP servers should I have?"*

## What can it do?

| You say | mcp-tap does |
|---------|-------------|
| "Find me an MCP for PostgreSQL" | Searches registry, compares options, recommends the best one |
| "Set up my project" | Scans your codebase, recommends servers based on your actual stack |
| "Install the GitHub MCP server" | Installs, configures, validates, and self-heals if it breaks |
| "What MCP servers do I have?" | Lists installed servers with health status |
| "Remove the Notion MCP" | Clean uninstall with config cleanup |
| "Why isn't my Slack MCP working?" | Diagnoses the issue and fixes it |
```

### Design Notes for the README

**What makes this README work:**

- **One-liner hook** -- "The last MCP server you install by hand." This is the kind of line people screenshot and tweet. It is both a promise and a value proposition in 9 words.

- **Before/After** -- The 10-step "Before" list is painfully relatable. Every MCP user has lived this. The 4-line "After" block is the payoff. This contrast does more selling than any feature list.

- **Install in 5 lines** -- Developers want to try things NOW. The install block is copy-paste ready.

- **Conversational examples** -- The "What can it do?" table uses natural language, not CLI flags. This reinforces the core differentiator: you talk to it, you don't type commands.

- **No badges, no logo (initially)** -- Ship the README with pure content. Add badges (npm version, CI status, stars) and a logo after the first release. A README with 12 badges and zero users looks desperate.

- **GIF placement** -- Add a terminal recording (using `vhs` or `asciinema`) showing the demo scenario right after the "After mcp-tap" section. The GIF should be 15-20 seconds, showing: user asks -> mcp-tap scans -> presents recommendations -> installs -> validates. Fast, satisfying.

---

## 3. THE KILLER DEMO (60 seconds)

### Setup
The user has a fresh project: a Python FastAPI app with PostgreSQL (in docker-compose.yml), Slack integration (SLACK_BOT_TOKEN in .env), and a GitHub repo. Zero MCP servers configured.

### The Demo Script

```
[0:00] (Screen: Claude Desktop, empty conversation)
[0:03] User types: "Scan my project and set up any useful MCP servers."

[0:06] mcp-tap responds:
       "Scanning /Users/demo/myproject..."

       "I found:
        - Python 3.12 + FastAPI (from pyproject.toml)
        - PostgreSQL (from docker-compose.yml, port 5432)
        - Slack integration (SLACK_BOT_TOKEN in .env)
        - GitHub repository (detected .github/ and git remote)
        - Redis cache (from docker-compose.yml)

        I recommend 4 MCP servers:"

[0:15] mcp-tap presents a ranked table:
       "1. @modelcontextprotocol/server-postgres (HIGH)
           Why: Direct database queries for your FastAPI app
           Credential: Already have POSTGRES_URL in .env

        2. @modelcontextprotocol/server-slack (HIGH)
           Why: Manage Slack from your assistant
           Credential: Already have SLACK_BOT_TOKEN in .env

        3. @github/github-mcp-server (MEDIUM)
           Why: Manage issues, PRs, code search
           Credential: Need GITHUB_TOKEN (will guide you)

        4. mcp-server-redis (MEDIUM)
           Why: Inspect your Redis cache
           Credential: No auth needed (local Docker)

        I also looked at @alternative/pg-tools but it hasn't been
        updated in 5 months. Skipping.

        Install all 4?"

[0:25] User types: "Yes"

[0:27] mcp-tap: "I need one credential -- your GitHub token.
        Create one here: https://github.com/settings/tokens/new
        Required scopes: repo, read:org
        Paste it when ready:"

[0:32] User pastes token.

[0:34] mcp-tap: "Installing...
        [1/4] postgres-mcp     -- installed, connecting... connected (8 tools)
        [2/4] slack-mcp         -- installed, connecting... connected (12 tools)
        [3/4] github-mcp        -- installed, connecting... connected (15 tools)
        [4/4] redis-mcp         -- installed, connecting... connected (5 tools)

        All 4 servers verified. 40 new tools available.
        Config written to ./mcp_servers.json
        Credentials stored securely."

[0:45] User types: "Query my database for the 5 most recent users."

[0:48] (Claude uses the freshly-installed postgres-mcp to run the query)
       "Here are your 5 most recent users:
        | id | name | email | created_at |
        ..."

[0:55] User types: "Send a Slack message to #engineering about the new deploy."

[0:58] (Claude uses slack-mcp to send the message)
       "Message sent to #engineering."

[1:00] END
```

### Why This Demo Wins

1. **Zero to 40 tools in 45 seconds.** That is the headline number. Put it in the tweet, the blog post, the conference talk.

2. **Immediate proof of value.** The demo does not end at "servers installed." It shows the user *actually using* the tools that were just set up. The database query and Slack message prove the servers work.

3. **Credential reuse.** The demo shows mcp-tap finding 3 out of 4 credentials automatically. The user only has to provide ONE token. This is the "it just works" moment.

4. **The rejection.** "I also looked at @alternative/pg-tools but it hasn't been updated in 5 months. Skipping." This single line proves the agent is *thinking*, not just pattern-matching. It builds trust.

5. **Self-contained.** The entire demo happens in one conversation. No terminal switching, no file editing, no restarts.

---

## 4. VIRAL OPEN-SOURCE FEATURES

### Tier 1: Launch Features (Day 1)

#### 4.1 Project-Aware Setup ("What do I need?")
Scans your codebase and recommends servers. This is the core differentiator and should be the headline feature.

- Reads `package.json`, `pyproject.toml`, `docker-compose.yml`, `.env`, `Makefile`
- Detects languages, frameworks, databases, APIs, cloud providers
- Maps detected stack to MCP servers
- Shows what you already have vs what is missing

**Why it's viral:** Developers love tools that "understand" their project. The moment mcp-tap says "I see you're using PostgreSQL and Slack" -- that is the tweet-worthy moment.

#### 4.2 Self-Healing Connections
When a server fails validation, mcp-tap diagnoses the error, fixes the config, and retries (up to 3 times). No other tool does this.

- Parse error messages (ENOENT, connection refused, auth failed)
- Apply fix (change path, adjust port, regenerate config)
- Retry with the fix
- If unfixable, explain exactly why and what to do manually

**Why it's viral:** "My MCP server broke and mcp-tap fixed it without me doing anything" -- that is a Hacker News comment that gets 200 upvotes.

#### 4.3 Health Check ("What's broken?")
`"Check my MCP servers."` -> mcp-tap connects to each installed server, runs `list_tools()`, and reports status.

**Why it's viral:** Visibility into what is working and what is not. Currently you just get cryptic errors at runtime.

### Tier 2: Growth Features (Month 1-2)

#### 4.4 Setup Profiles (Stacks)
Pre-defined server bundles for common use cases:

```
You: "Set up the data science stack."

mcp-tap: Installing the Data Science stack:
  - jupyter-mcp (notebook execution)
  - postgres-mcp (database queries)
  - filesystem-mcp (file operations)
  - python-mcp (code execution)
```

Proposed stacks:
- **Data Science**: jupyter, postgres, filesystem, python
- **Web Dev**: github, filesystem, postgres/sqlite, browser
- **DevOps**: github, docker, kubernetes, aws/gcp
- **Content**: notion, google-drive, slack, email
- **Research**: web-search, arxiv, filesystem, memory

**Why it's viral:** "Install the X stack" is a one-liner that sets up 4-5 servers. People will share their custom stacks. Community-contributed stacks become a discovery mechanism.

#### 4.5 Community Server Lists
A community-curated `awesome-mcp-tap` registry:

```yaml
# community/data-science.yaml
name: Data Science Stack
author: "@datascientist42"
description: "Everything you need for data analysis in Claude"
servers:
  - name: postgres-mcp
    package: "@modelcontextprotocol/server-postgres"
    why: "Direct SQL queries on your data"
  - name: jupyter-mcp
    package: "mcp-server-jupyter"
    why: "Run and manage Jupyter notebooks"
```

Users can submit PRs to add stacks. This creates a contribution pathway that is much lower friction than contributing code.

**Why it's viral:** User-generated content creates a flywheel. People make stacks -> other people install stacks -> they make their own -> the repo grows.

#### 4.6 Dotfiles Integration
`mcp-tap export` generates a portable config that can live in your dotfiles:

```yaml
# ~/.mcp-tap/profile.yaml
defaults:
  - postgres-mcp
  - github-mcp
  - filesystem-mcp
per_project:
  python:
    - python-mcp
    - jupyter-mcp
  typescript:
    - typescript-mcp
    - eslint-mcp
```

When you clone a new project: `"Hey Claude, set up this project with mcp-tap"` -> it reads your profile AND the project, merging both.

**Why it's viral:** Developers love dotfiles. The `.mcp-tap` directory becomes part of their identity. They share it like they share `.vimrc`.

### Tier 3: Moat Features (Month 3+)

#### 4.7 Project Context Auto-Detection
When mcp-tap detects your project SHOULD have a server but does not:

```
mcp-tap: I noticed you installed a PostgreSQL server but your project
also has Redis in docker-compose.yml. Want me to set up redis-mcp too?
```

This passive recommendation, triggered by project changes, keeps the tool valuable over time.

#### 4.8 Server Version Management
Track which versions you have, notify about updates:

```
mcp-tap: 2 of your MCP servers have updates available:
  - postgres-mcp: 1.2.0 -> 1.3.0 (new: materialized view support)
  - github-mcp: 0.9.0 -> 1.0.0 (breaking: new auth flow)

  Update postgres-mcp? (github-mcp has breaking changes, review first)
```

#### 4.9 MCP Server Ratings
After using a server for a week, mcp-tap asks:

```
You've been using postgres-mcp for 7 days (142 tool calls).
How's it working? (great / ok / problematic)
```

Aggregate ratings feed back into recommendations for other users.

---

## 5. POSITIONING: WHY "INSIDE THE ASSISTANT" WINS

### The Fundamental Insight

CLI tools and web registries exist OUTSIDE the workflow. They require context-switching: leave the conversation, open a terminal, run a command, go back. But the AI assistant is where the developer already IS. The best tool is the one you never have to leave your workflow to use.

### The Three Advantages of Living Inside the Assistant

#### 5.1 Conversational Intent Resolution

**CLI tool:**
```bash
$ mcpm search postgres
# Returns 12 results. You read them. You pick one. You run another command.
```

**Inside the assistant:**
```
"I need to query my Postgres database from Claude."
# mcp-tap understands the INTENT, not just the keyword.
# It knows you want a server that provides query tools,
# not one that monitors Postgres metrics.
```

The assistant has conversational context. It knows what you are trying to do, not just what you typed. A CLI tool gets a string. The assistant gets meaning.

#### 5.2 Project Context Without Extra Steps

**CLI tool:**
```bash
$ mcpm install postgres-mcp
# Installs the package. You still need to:
# - Figure out the config format for YOUR client
# - Find your connection string
# - Add it to the right config file
# - Restart the client
```

**Inside the assistant:**
```
"Set up Postgres."
# mcp-tap already knows:
# - Your project uses PostgreSQL (from docker-compose.yml)
# - Your connection string is in .env as POSTGRES_URL
# - Your client is Claude Desktop (because that's where we are)
# - The config file is at ~/Library/Application Support/Claude/...
# Zero extra information needed from you.
```

The assistant already has the project context. A CLI tool starts from zero every time.

#### 5.3 Self-Healing is Natural

**CLI tool:**
```bash
$ mcpm install slack-mcp
Error: Connection refused
$ # Now what? Google the error? Read the README?
```

**Inside the assistant:**
```
mcp-tap: slack-mcp failed to connect: "Connection refused on port 3000"
  This usually means the server expects HTTP transport but
  I configured it as stdio. Let me fix that...

  [fixes config, retries]

  Connected. 12 tools available.
```

The assistant can READ the error, REASON about it, FIX the config, and RETRY. A CLI tool just prints the error and exits. The feedback loop is what makes "inside the assistant" fundamentally superior.

### Competitive Positioning Matrix

| | Smithery | mcp-get | install-mcp | mcpm | **mcp-tap** |
|--|---------|---------|-------------|------|-----------|
| **Where it lives** | Web browser | Terminal | Terminal | Terminal | Inside the assistant |
| **Discovery** | Browse catalog | Search registry | Manual | Search registry | Scans your project + searches registry |
| **Config generation** | Copy-paste template | Auto-generates basic | Auto-generates basic | Auto-generates basic | Reads docs, generates per YOUR setup |
| **Credential handling** | Manual | Manual | OAuth for remote | Manual | Detects existing, guides for new |
| **Validation** | None | None | None | None | connect() + list_tools() per server |
| **Self-healing** | None | None | None | None | Diagnose -> fix -> retry (3x) |
| **Project analysis** | None | None | None | None | Reads codebase, understands stack |
| **Effort to use** | Leave conversation, open browser | Leave conversation, open terminal | Leave conversation, open terminal | Leave conversation, open terminal | Stay in conversation |

**The one-liner positioning:**

> Smithery is where you browse servers.
> mcpm is how you install them from the terminal.
> **mcp-tap is how you set them up without leaving your conversation.**

---

## 6. LAUNCH STRATEGY

### Pre-Launch (Week -2 to 0)
1. **Build the MVP** -- project scanning + registry search + config generation + install + validate
2. **Record the demo GIF** -- The 60-second demo from Section 3
3. **Write the README** -- The exact content from Section 2
4. **Pick 3 beta testers** -- Find 3 developers who actively use MCP and have complained about setup

### Launch Day
1. **GitHub repo goes public** with the README, demo GIF, and working package
2. **Hacker News post** -- Title: "mcp-tap: The last MCP server you install by hand" (Show HN)
3. **Tweet/post** -- The Before/After comparison, compressed: "10 steps to set up an MCP server. Or one sentence to mcp-tap."
4. **r/ClaudeAI + r/LocalLLaMA** -- Cross-post with the demo GIF
5. **MCP Discord** -- Share in the Model Context Protocol community

### Post-Launch (Week 1-4)
1. **Respond to every issue and PR** within 24 hours
2. **Ship the "stacks" feature** based on what users actually ask for
3. **Create a `CONTRIBUTING.md`** focused on adding community stacks (low-friction contribution)
4. **Add to awesome-mcp-servers** list

### Growth Milestones
- **100 stars**: Ship stacks feature, add to Smithery registry
- **500 stars**: Launch community stacks (`awesome-mcp-tap`)
- **1,000 stars**: Add dotfiles integration, version management
- **5,000 stars**: Community ratings, passive recommendations

---

## 7. TECHNICAL ARCHITECTURE NOTES

### What to Build vs What to Defer

**Build Now (MVP):**
- MCP server with 6 tools: `scan_project`, `search_servers`, `install_server`, `list_installed`, `check_health`, `remove_server`
- Project scanner (file-based, no LLM needed)
- MCP Registry API client
- Config generator for Claude Desktop and Cursor
- Connection validator (start server, call list_tools)
- Basic error diagnosis

**Defer:**
- Self-healing feedback loop (add in v0.2)
- Community stacks (add when there are users)
- Dotfiles integration (add when there are power users)
- Version management (add when servers have versions worth tracking)
- Ratings system (add when there is enough usage data)

### MCP Server Tool Design

```typescript
// The 6 tools mcp-tap exposes:

scan_project(path: string): ProjectProfile
// Scans project files, returns detected stack

search_servers(query: string, project_context?: ProjectProfile): ServerCandidate[]
// Searches MCP Registry + npm/PyPI, optionally using project context

install_server(
  package_name: string,
  client: "claude_desktop" | "cursor" | "custom",
  env_vars?: Record<string, string>
): InstallResult
// Installs package, generates config, writes to client config file

list_installed(client?: string): InstalledServer[]
// Lists currently configured MCP servers with health status

check_health(server_name?: string): HealthReport
// Validates connections to installed servers

remove_server(server_name: string, client?: string): RemoveResult
// Removes server config and optionally uninstalls package
```

### Language Choice

**TypeScript (recommended for MVP):**
- MCP ecosystem is npm-first (`npx` is the standard runner)
- `@modelcontextprotocol/sdk` is TypeScript-native
- Claude Desktop config is JSON -- TS is natural for JSON manipulation
- `npx mcp-tap` just works, no Python environment needed

**Python (for Hive integration):**
- If this is also a Hive agent template, Python is required
- Can ship both: TypeScript MCP server (standalone) + Python agent (Hive template)
- `uvx mcp-tap` for Python-native users

**Recommendation:** Ship TypeScript first for maximum reach, add Python variant later for Hive ecosystem.

---

## VERDICT: PROCEED

### Name: `mcp-tap`
### Tagline: "The last MCP server you install by hand."
### Positioning: The MCP server that lives inside your assistant.

### Why This Will Work

1. **Real pain, real solution.** Every MCP user has wasted 30+ minutes on server setup. This eliminates that pain entirely.

2. **Viral demo.** "Zero to 40 tools in 45 seconds" is a shareable moment. The Before/After comparison is screenshot-worthy.

3. **Network effects.** Community stacks create a contribution flywheel. Each stack added makes the tool more valuable for everyone.

4. **Defensible position.** "Inside the assistant" is not a feature -- it is an architectural position. CLI tools cannot easily replicate project-aware, conversational, self-healing setup because they do not have the LLM context.

5. **Low barrier, high ceiling.** Install in one line, get value in 60 seconds. But power users get stacks, profiles, dotfiles integration, and version management.

### Next Steps

1. Register `mcp-tap` on npm and PyPI (reserve the names)
2. Create GitHub repo at `github.com/<org>/mcp-tap`
3. Build the MVP: scan + search + install + validate (TypeScript)
4. Record the demo GIF
5. Ship the README from Section 2
6. Launch on Hacker News with "Show HN: mcp-tap -- the last MCP server you install by hand"
