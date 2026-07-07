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
    import anyio
    import asyncio
    import logging
    from agentos.skills.scheduler import run_task_dispatcher
    from agentos.memory.repository import MemoryRepository
    from agentos.qwen.client import close_qwen_client

    app = create_mcp_server(handlers=handlers)

    async def main_with_dispatcher():
        async def background_dispatcher():
            repo = MemoryRepository()
            while True:
                try:
                    await run_task_dispatcher(repo, print_callback=None)
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logging.getLogger(__name__).error(f"Error in background task dispatcher: {e}")
                await asyncio.sleep(30)

        dispatcher_task = asyncio.create_task(background_dispatcher())
        try:
            await app.run_stdio_async()
        finally:
            dispatcher_task.cancel()
            try:
                await dispatcher_task
            except asyncio.CancelledError:
                pass
            await close_qwen_client()

    return anyio.run(main_with_dispatcher)
