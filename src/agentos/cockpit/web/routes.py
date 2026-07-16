"""Read-only HTTP routes for the cockpit web UI."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
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
def project_list_page(request: Request, show_temp: bool = False) -> HTMLResponse:
    """Render the registered projects as a server-side HTML page."""
    projects = registry.list_projects()

    filtered_projects = []
    for p in projects:
        is_temp = p.root_path.startswith("/tmp") or "/tmp/" in p.root_path
        if is_temp and not show_temp:
            continue
        filtered_projects.append(p)

    project_data = []
    total_sdd_artifacts = 0
    clean_git_count = 0
    healthy_count = 0

    for record in filtered_projects:
        project = ProjectRef(key=record.key, root_path=Path(record.root_path), source=record.source)
        try:
            snapshot = build_cockpit_snapshot(project, record_open=False)
        except Exception:
            snapshot = None

        if snapshot:
            is_healthy = not any(c.status == "failing" for c in snapshot.health_checks)
            if is_healthy:
                healthy_count += 1

            if snapshot.git_summary.is_dirty is False:
                clean_git_count += 1

            total_sdd_artifacts += len(snapshot.sdd_summary.found_artifacts)

            project_data.append({
                "record": record,
                "snapshot": snapshot,
                "git_status": "clean" if snapshot.git_summary.is_dirty is False else ("dirty" if snapshot.git_summary.is_dirty is True else "unknown"),
                "sdd_completeness": snapshot.sdd_summary.completeness,
                "test_health": next((c.status for c in snapshot.health_checks if c.id == "tests"), "unknown")
            })
        else:
            project_data.append({
                "record": record,
                "snapshot": None,
                "git_status": "unknown",
                "sdd_completeness": "0/4",
                "test_health": "unknown"
            })

    total_projects = len(filtered_projects)
    avg_sdd_completeness = 0.0
    if total_projects > 0:
        avg_sdd_completeness = (total_sdd_artifacts / (4 * total_projects)) * 100

    metrics = {
        "total_projects": total_projects,
        "healthy_projects": healthy_count,
        "avg_sdd_completeness": round(avg_sdd_completeness, 1),
        "clean_git": clean_git_count,
    }

    return templates.TemplateResponse(
        request=request,
        name="project_list.html",
        context={
            "project_data": project_data,
            "metrics": metrics,
            "show_temp": show_temp,
        },
    )


@router.get("/project/delete")
def delete_project_route(root_path: str) -> RedirectResponse:
    """Delete a project from the registry and redirect back to the home page."""
    registry.delete_project(root_path)
    return RedirectResponse(url="/", status_code=303)



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
def project_audit_page(request: Request, key: str, mode: str = "deep") -> HTMLResponse:
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
    
    # Filter passes: exclude slow 'tests' pass in 'simple' mode
    active_passes = PASS_REGISTRY
    if mode == "simple":
        active_passes = [p for p in PASS_REGISTRY if p.id != "tests"]
        
    pass_results = run_registered_passes(ctx, active_passes)
    findings = merge_findings(pass_results)
    report_markdown = render_markdown(project.key, project.root_path, generated_at, findings)
    return templates.TemplateResponse(
        request=request,
        name="audit_report.html",
        context={"key": key, "report_markdown": report_markdown, "mode": mode},
    )


def parse_tasks_checklist(content: str) -> list[dict]:
    import re
    tasks = []
    if not content:
        return tasks
    # Match lines like "- [ ] Title" or "- [x] Title"
    pattern = re.compile(r'^\s*-\s+\[([ xX])\]\s+(.+)$')
    for line in content.splitlines():
        match = pattern.match(line)
        if match:
            done = match.group(1).lower() == 'x'
            title = match.group(2).strip()
            tasks.append({"done": done, "title": title})
    return tasks


@router.get("/project/{key}/sdd", response_class=HTMLResponse)
def project_sdd_page(request: Request, key: str) -> HTMLResponse:
    """Render the SDD Hub tabbed interface for a single registered project."""
    record = next((entry for entry in registry.list_projects() if entry.key == key), None)
    if record is None:
        return templates.TemplateResponse(
            request=request,
            name="not_found.html",
            context={"key": key},
            status_code=404,
        )

    from agentos.sdd.detector import detect_sdd_artifacts
    sdd_status = detect_sdd_artifacts(Path(record.root_path))
    
    proposal_content = None
    spec_content = None
    design_content = None
    tasks_content = None
    tasks_list = []

    if sdd_status.has_sdd and sdd_status.sdd_dir:
        sdd_dir_path = Path(record.root_path) / sdd_status.sdd_dir
        
        proposal_file = sdd_dir_path / "proposal.md"
        if proposal_file.is_file():
            proposal_content = proposal_file.read_text(encoding="utf-8")
            
        spec_file = sdd_dir_path / "spec.md"
        if spec_file.is_file():
            spec_content = spec_file.read_text(encoding="utf-8")
            
        design_file = sdd_dir_path / "design.md"
        if design_file.is_file():
            design_content = design_file.read_text(encoding="utf-8")
            
        tasks_file = sdd_dir_path / "tasks.md"
        if tasks_file.is_file():
            tasks_content = tasks_file.read_text(encoding="utf-8")
            tasks_list = parse_tasks_checklist(tasks_content)

    return templates.TemplateResponse(
        request=request,
        name="sdd_hub.html",
        context={
            "key": key,
            "sdd_status": sdd_status,
            "proposal_content": proposal_content,
            "spec_content": spec_content,
            "design_content": design_content,
            "tasks_list": tasks_list,
        },
    )


@router.get("/scanner", response_class=HTMLResponse)
def project_scanner_page(
    request: Request, 
    target_dir: str = "/home/akidev/proyects",
    action: str | None = None,
    register_path: str | None = None,
    register_key: str | None = None,
) -> HTMLResponse:
    """Render the directory discovery scanner and register projects via GET endpoints."""
    message = None
    if action == "register" and register_path and register_key:
        try:
            registry.upsert_project(register_key, Path(register_path), source="scanner")
            message = f"Successfully registered project '{register_key}' at '{register_path}'"
        except Exception as e:
            message = f"Error registering project: {str(e)}"

    scanned_dirs = []
    target_path = Path(target_dir).expanduser().resolve()
    if target_path.is_dir():
        for child in target_path.iterdir():
            if child.is_dir():
                if child.name.startswith('.'):
                    continue
                
                # Check Git
                has_git = (child / ".git").is_dir()
                
                # Check SDD
                has_sdd = False
                for sdd_dir in ("docs/sdd", ".sdd", "openspec"):
                    if (child / sdd_dir).is_dir():
                        has_sdd = True
                        break
                
                # Check Tests
                has_tests = False
                if (child / "tests").is_dir() or (child / "test").is_dir() or (child / "pytest.ini").is_file():
                    has_tests = True
                else:
                    # Optimize check: search without entering huge virtualenv or node_modules
                    for path in child.iterdir():
                        if path.name in (".venv", "venv", "node_modules", ".git") or path.name.startswith('.'):
                            continue
                        if path.name.startswith("test_") and path.suffix == ".py":
                            has_tests = True
                            break
                        if path.is_dir():
                            try:
                                for sub in path.iterdir():
                                    if sub.name.startswith("test_") and sub.suffix == ".py":
                                        has_tests = True
                                        break
                            except OSError:
                                pass
                        if has_tests:
                            break

                # Check if registered
                registered_projects = registry.list_projects()
                is_registered = any(
                    Path(p.root_path).resolve() == child.resolve()
                    for p in registered_projects
                )
                
                scanned_dirs.append({
                    "name": child.name,
                    "path": str(child.resolve()),
                    "has_git": has_git,
                    "has_sdd": has_sdd,
                    "has_tests": has_tests,
                    "is_registered": is_registered,
                })

    # Sort scanned dirs alphabetically
    scanned_dirs.sort(key=lambda x: x["name"])

    return templates.TemplateResponse(
        request=request,
        name="scanner.html",
        context={
            "target_dir": target_dir,
            "scanned_dirs": scanned_dirs,
            "message": message,
        },
    )
