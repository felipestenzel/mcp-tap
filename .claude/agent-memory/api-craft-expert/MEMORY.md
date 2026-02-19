# API Craft Expert Memory — mcp-tap

## Project: mcp-tap (MCP server, not REST API)
- Exposes tools via MCP protocol (FastMCP), not HTTP endpoints
- 5 tools: search_servers, configure_server, test_connection, list_installed, remove_server
- Tool annotations: readOnlyHint and destructiveHint properly set
