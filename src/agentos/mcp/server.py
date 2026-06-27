"""MCP stdio server for Aki memory tools."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from agentos.mcp.tools import MemoryToolHandlers, tool_callables


def create_mcp_server(handlers: MemoryToolHandlers | None = None) -> FastMCP:
    """Create a FastMCP server with all MVP memory tools registered."""
    app = FastMCP("aki-memory")
    resolved_handlers = handlers or MemoryToolHandlers()

    for name, handler in tool_callables(resolved_handlers).items():
        app.tool(name=name)(handler)

    return app


def run_mcp_server(handlers: MemoryToolHandlers | None = None) -> Any:
    """Run the MCP server over stdio."""
    return create_mcp_server(handlers=handlers).run(transport="stdio")
