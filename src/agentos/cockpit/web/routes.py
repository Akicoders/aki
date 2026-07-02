"""Read-only HTTP routes for the cockpit web UI."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from agentos.cli.cockpit import ProjectRef, build_cockpit_snapshot
from agentos.cockpit import registry
from agentos.cockpit.audit.base import AuditContext, merge_findings, run_registered_passes
from agentos.cockpit.audit.passes import PASS_REGISTRY
from agentos.cockpit.audit.report import persist_audit, render_markdown
from agentos.memory.models import ProjectRefRecord

router = APIRouter()

_TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))


@router.get("/health")
def health() -> dict:
    """Confirm the server is running and can reach the cockpit domain layer."""
    return {"status": "ok"}


@router.get("/api/projects")
def list_projects() -> list[ProjectRefRecord]:
    """Return the registered projects, unmodified from the domain layer."""
    return registry.list_projects()


@router.get("/", response_class=HTMLResponse)
def project_list_page(request: Request) -> HTMLResponse:
    """Render the registered projects as a server-side HTML page."""
    projects = registry.list_projects()
    return templates.TemplateResponse(
        request=request,
        name="project_list.html",
        context={"projects": projects},
    )


@router.get("/project/{key}", response_class=HTMLResponse)
def project_detail_page(request: Request, key: str) -> HTMLResponse:
    """Render the 4-panel cockpit drill-down for a single registered project."""
    record = next((entry for entry in registry.list_projects() if entry.key == key), None)
    if record is None:
        return templates.TemplateResponse(
            request=request,
            name="not_found.html",
            context={"key": key},
            status_code=404,
        )

    project = ProjectRef(key=record.key, root_path=Path(record.root_path), source=record.source)
    snapshot = build_cockpit_snapshot(project, record_open=False)
    return templates.TemplateResponse(
        request=request,
        name="project_detail.html",
        context={"snapshot": snapshot},
    )


@router.get("/project/{key}/audit", response_class=HTMLResponse)
def project_audit_page(request: Request, key: str) -> HTMLResponse:
    """Render an in-memory, read-only audit report for a single registered project.

    Reuses the audit domain layer's run/render path (`run_registered_passes` +
    `render_markdown`) without ever calling `persist_audit` — this endpoint MUST
    NOT trigger a new persisted audit run or any autofix action.
    """
    record = next((entry for entry in registry.list_projects() if entry.key == key), None)
    if record is None:
        return templates.TemplateResponse(
            request=request,
            name="not_found.html",
            context={"key": key},
            status_code=404,
        )

    project = ProjectRef(key=record.key, root_path=Path(record.root_path), source=record.source)
    generated_at = datetime.now()
    ctx = AuditContext(project=project, root_path=project.root_path, generated_at=generated_at)
    pass_results = run_registered_passes(ctx, PASS_REGISTRY)
    findings = merge_findings(pass_results)
    report_markdown = render_markdown(project.key, project.root_path, generated_at, findings)
    return templates.TemplateResponse(
        request=request,
        name="audit_report.html",
        context={"key": key, "report_markdown": report_markdown},
    )
