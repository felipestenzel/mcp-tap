# Strategic Research: mcp-tap Category Definition (Feb 2026)

## Competitor Deep Dive

### mcp-sync (github.com/ztripez/mcp-sync)
- CLI tool for cross-client MCP config sync
- 3-tier config: global (~/.mcp-sync/global.json), project (.mcp.json), tool
- Supports: Claude Desktop, Claude Code, Cline, Roo, VS Code, Cursor, Continue
- Custom client definitions via JSON
- Smart conflict resolution, dry-run mode
- **Overlap with mcp-tap**: Multi-client install already exists in configure_server
- **Verdict**: Don't compete on sync. Recommend as complement.

### mcp-compose (github.com/phildougherty/mcp-compose)
- Docker-compose-style YAML for MCP servers
- HTTP proxy with stdio-to-HTTP translation
- Session management, connection pooling
- Web dashboard, OpenAPI spec generation
- Supports Docker and Podman
- **Overlap with mcp-tap**: Stacks feature planned in Creative Brief
- **Verdict**: Different approach. mcp-compose = infra/DevOps. mcp-tap = conversational/developer.

### MetaMCP (github.com/metatool-ai/metamcp)
- Aggregator + orchestrator + middleware + gateway in Docker
- Tool curation (pick only needed tools)
- Namespace organization, override tool names/descriptions
- Multi-tenant, API key + OAuth auth
- SSE, Streamable HTTP, OpenAPI endpoints
- **Overlap with mcp-tap**: Tool curation (context budget idea)
- **Verdict**: Enterprise gateway. Different market segment.

### mcp-scan / agent-scan (github.com/snyk/agent-scan)
- Security scanner for MCP servers
- Detects: prompt injection, tool poisoning, toxic flows, rug pulls
- Static scanning (connect + analyze tool definitions)
- Dynamic proxy mode (intercept real-time traffic)
- Output: formatted tables or JSON
- Doesn't log actual user data, only metadata
- **Overlap with mcp-tap**: Security gate at install
- **Verdict**: Complementary. mcp-tap does pre-install vetting; mcp-scan does post-install monitoring.

## OWASP MCP Top 10 (relevant to mcp-tap)
- MCP01: Token Mismanagement (static secrets) -- mcp-tap can warn about credential type
- MCP02: Privilege Escalation -- mcp-tap can analyze tool permissions
- MCP03: Tool Poisoning -- lockfile with tools_hash detects changes
- MCP04: Supply Chain Attacks -- lockfile with checksums detects tampering
- MCP05: Command Injection -- out of scope for mcp-tap
- MCP07: Insufficient Auth -- mcp-tap can flag servers without OAuth
- MCP09: Shadow MCP Servers -- mcp-tap's list_installed surfaces all servers

## Key Statistics
- 88% of MCP servers require credentials
- 53% use insecure static long-lived secrets
- 8.5% use OAuth (modern auth)
- 36.7% may have latent SSRF vulnerability
- 20% of tools handle 80% of requests (Pareto in MCP)
- MCPTox research: o1-mini had 72.8% attack success rate via tool poisoning

## Original Ideas (not seen in ecosystem)
1. MCP Lockfile -- nobody does deterministic reproducibility with checksums
2. Security gate at installation point -- scanners are post-install, not pre-install
3. Workflow understanding via git history -- all competitors do static file scanning only
4. Tool conflict detection -- no tool checks for duplicate tool names across servers
5. Context budget reporting -- MetaMCP does curation but nobody reports token cost
