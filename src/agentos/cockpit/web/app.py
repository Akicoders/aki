"""FastAPI application factory and uvicorn launcher for the cockpit web UI."""

from __future__ import annotations

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from agentos.cockpit.web.routes import router
from agentos.cockpit.web.settings import WebServerSettings


def create_app() -> FastAPI:
    """Build the read-only cockpit web application."""
    app = FastAPI(title="Aki Cockpit")
    app.include_router(router)

    @app.exception_handler(Exception)
    async def _unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(status_code=500, content={"detail": "internal server error"})

    return app


def run_server(settings: WebServerSettings) -> None:
    """Serve the cockpit web application over HTTP using uvicorn."""
    uvicorn.run(create_app(), host=settings.host, port=settings.port)
