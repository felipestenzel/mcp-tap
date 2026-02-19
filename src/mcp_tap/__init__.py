"""mcp-tap: The last MCP server you install by hand."""

__version__ = "0.1.0"


def main() -> None:
    """Entry point for `mcp-tap` CLI."""
    from mcp_tap.server import mcp

    mcp.run(transport="stdio")
