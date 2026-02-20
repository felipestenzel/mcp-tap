"""Helpers for extracting AppContext from FastMCP Context."""

from __future__ import annotations

from typing import TYPE_CHECKING

from mcp.server.fastmcp import Context

if TYPE_CHECKING:
    from mcp_tap.server import AppContext


def get_context(ctx: Context) -> AppContext:
    """Extract AppContext from FastMCP's lifespan context.

    Raises TypeError if the lifespan context is not an AppContext instance.
    This catches misconfiguration early with a clear error message.
    """
    from mcp_tap.server import AppContext

    app = ctx.request_context.lifespan_context
    if not isinstance(app, AppContext):
        msg = (
            f"Expected AppContext in lifespan_context, got {type(app).__name__}. "
            "Is the server configured with app_lifespan?"
        )
        raise TypeError(msg)
    return app
