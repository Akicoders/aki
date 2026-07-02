"""Read-only HTTP routes for the cockpit web UI."""

from __future__ import annotations

from fastapi import APIRouter

from agentos.cockpit import registry
from agentos.memory.models import ProjectRefRecord

router = APIRouter()


@router.get("/health")
def health() -> dict:
    """Confirm the server is running and can reach the cockpit domain layer."""
    return {"status": "ok"}


@router.get("/api/projects")
def list_projects() -> list[ProjectRefRecord]:
    """Return the registered projects, unmodified from the domain layer."""
    return registry.list_projects()
