from __future__ import annotations

from datetime import datetime

from fastapi.testclient import TestClient

from agentos.cockpit.web.app import create_app, run_server
from agentos.cockpit.web.settings import WebServerSettings
from agentos.memory.models import ProjectRefRecord


def test_health_endpoint_returns_healthy_status():
    client = TestClient(create_app())

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json().get("status") == "ok"


def test_projects_endpoint_returns_registered_projects(monkeypatch):
    record = ProjectRefRecord(
        root_path="/tmp/demo-project",
        key="demo-project",
        source="git",
        last_opened_at=datetime(2026, 7, 1, 10, 0, 0),
    )
    monkeypatch.setattr(
        "agentos.cockpit.web.routes.registry.list_projects",
        lambda: [record],
    )
    client = TestClient(create_app())

    response = client.get("/api/projects")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["key"] == "demo-project"
    assert body[0]["root_path"] == "/tmp/demo-project"


def test_projects_endpoint_returns_empty_array_when_no_projects(monkeypatch):
    monkeypatch.setattr(
        "agentos.cockpit.web.routes.registry.list_projects",
        lambda: [],
    )
    client = TestClient(create_app())

    response = client.get("/api/projects")

    assert response.status_code == 200
    assert response.json() == []


def test_run_server_calls_uvicorn_with_settings(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "agentos.cockpit.web.app.uvicorn.run",
        lambda app, host, port: calls.append((app, host, port)),
    )

    run_server(WebServerSettings(host="127.0.0.1", port=9000))

    assert len(calls) == 1
    app, host, port = calls[0]
    assert host == "127.0.0.1"
    assert port == 9000
    assert app.title == "Aki Cockpit"


def test_unhandled_exception_returns_safe_500(monkeypatch):
    def _boom():
        raise RuntimeError("boom: /home/user/secret/path.py")

    monkeypatch.setattr("agentos.cockpit.web.routes.registry.list_projects", _boom)
    client = TestClient(create_app(), raise_server_exceptions=False)

    response = client.get("/api/projects")

    assert response.status_code == 500
    body = response.json()
    assert body == {"detail": "internal server error"}


def test_no_route_accepts_mutation_verbs():
    app = create_app()
    client = TestClient(app)

    for route in app.routes:
        path = getattr(route, "path", None)
        if path is None:
            continue
        for method in ("POST", "PUT", "PATCH", "DELETE"):
            response = client.request(method, path)
            assert response.status_code in (404, 405), (
                f"{method} {path} unexpectedly returned {response.status_code}"
            )


def test_project_detail_returns_404_for_unknown_project(monkeypatch):
    monkeypatch.setattr(
        "agentos.cockpit.web.routes.registry.list_projects",
        lambda: [],
    )
    client = TestClient(create_app())

    response = client.get("/project/does-not-exist")

    assert response.status_code == 404
    assert "not found" in response.text.lower()


def test_project_detail_returns_panel_data_for_known_project(monkeypatch, tmp_path):
    record = ProjectRefRecord(
        root_path=str(tmp_path),
        key="demo-project",
        source="marker",
        last_opened_at=datetime(2026, 7, 1, 10, 0, 0),
    )
    monkeypatch.setattr(
        "agentos.cockpit.web.routes.registry.list_projects",
        lambda: [record],
    )

    def _fake_snapshot(project, record_open=True):
        assert record_open is False
        from agentos.cli.cockpit import (
            ActionItem,
            CockpitSnapshot,
            GitSummary,
            MemorySummary,
            SDDSummary,
        )

        return CockpitSnapshot(
            project=project,
            generated_at=datetime(2026, 7, 1, 10, 0, 0),
            action_items=[ActionItem("warning", "Fix env", "detail", "aki doctor")],
            health_checks=[],
            memory_summary=MemorySummary(),
            sdd_summary=SDDSummary(
                has_sdd=True,
                sdd_dir=".sdd",
                found_artifacts=["proposal.md"],
                missing_artifacts=[],
                latest_artifact="proposal.md",
                latest_artifact_updated_at=None,
                latest_preview=None,
                next_step="All core SDD artifacts are present.",
            ),
            git_summary=GitSummary(branch="main", is_dirty=False),
        )

    monkeypatch.setattr("agentos.cockpit.web.routes.build_cockpit_snapshot", _fake_snapshot)
    client = TestClient(create_app())

    response = client.get("/project/demo-project")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "demo-project" in response.text
    assert "Action Required" in response.text
    assert "Project Health" in response.text
    assert "Memory" in response.text
    assert "SDD Status" in response.text


def test_audit_report_returns_404_for_unknown_project(monkeypatch):
    monkeypatch.setattr(
        "agentos.cockpit.web.routes.registry.list_projects",
        lambda: [],
    )
    client = TestClient(create_app())

    response = client.get("/project/does-not-exist/audit")

    assert response.status_code == 404


def test_audit_report_renders_findings_without_side_effects(monkeypatch, tmp_path):
    from agentos.cockpit.audit.base import AuditFinding

    record = ProjectRefRecord(
        root_path=str(tmp_path),
        key="demo-project",
        source="marker",
        last_opened_at=datetime(2026, 7, 1, 10, 0, 0),
    )
    monkeypatch.setattr(
        "agentos.cockpit.web.routes.registry.list_projects",
        lambda: [record],
    )

    findings = [
        AuditFinding(
            priority="P1",
            category="security",
            title="Example finding",
            evidence="Some evidence",
            recommendation="Fix it",
        )
    ]

    def _fake_run_registered_passes(ctx, passes):
        return [("stub-pass", findings)]

    persist_calls = []
    autofix_calls = []

    monkeypatch.setattr(
        "agentos.cockpit.web.routes.run_registered_passes",
        _fake_run_registered_passes,
    )
    monkeypatch.setattr(
        "agentos.cockpit.web.routes.persist_audit",
        lambda *a, **k: persist_calls.append((a, k)),
    )

    client = TestClient(create_app())

    response = client.get("/project/demo-project/audit")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "Example finding" in response.text
    assert persist_calls == []
    assert autofix_calls == []


def test_audit_report_unreachable_via_autofix(monkeypatch):
    app = create_app()
    for route in app.routes:
        path = getattr(route, "path", None)
        endpoint = getattr(route, "endpoint", None)
        if endpoint is None:
            continue
        assert "autofix" not in endpoint.__name__.lower()
        assert path is None or "autofix" not in path.lower()


def test_root_lists_registered_projects_as_html(monkeypatch):
    record = ProjectRefRecord(
        root_path="/home/akidev/proyects/demo-project",
        key="demo-project",
        source="git",
        last_opened_at=datetime(2026, 7, 1, 10, 0, 0),
    )
    monkeypatch.setattr(
        "agentos.cockpit.web.routes.registry.list_projects",
        lambda: [record],
    )
    client = TestClient(create_app())

    response = client.get("/")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "demo-project" in response.text


def test_root_filters_temp_projects(monkeypatch):
    temp_record = ProjectRefRecord(
        root_path="/tmp/temp-project",
        key="temp-project",
        source="git",
        last_opened_at=datetime(2026, 7, 1, 10, 0, 0),
    )
    normal_record = ProjectRefRecord(
        root_path="/home/akidev/proyects/normal-project",
        key="normal-project",
        source="git",
        last_opened_at=datetime(2026, 7, 1, 10, 0, 0),
    )
    monkeypatch.setattr(
        "agentos.cockpit.web.routes.registry.list_projects",
        lambda: [temp_record, normal_record],
    )
    client = TestClient(create_app())

    # By default, temp-project should be filtered out
    response = client.get("/")
    assert response.status_code == 200
    assert "normal-project" in response.text
    assert "temp-project" not in response.text

    # With show_temp=true, both should be visible
    response = client.get("/?show_temp=true")
    assert response.status_code == 200
    assert "normal-project" in response.text
    assert "temp-project" in response.text


def test_delete_project_route(monkeypatch):
    deleted_paths = []

    def mock_delete(path):
        deleted_paths.append(str(path))
        return True

    monkeypatch.setattr(
        "agentos.cockpit.web.routes.registry.delete_project",
        mock_delete,
    )
    client = TestClient(create_app())

    response = client.get("/project/delete?root_path=/home/akidev/proyects/to-delete", follow_redirects=False)

    # Verify that it returns 303 Redirect to /
    assert response.status_code == 303
    assert response.headers["location"] == "/"
    assert deleted_paths == ["/home/akidev/proyects/to-delete"]



def test_project_sdd_page_returns_404_for_unknown_project(monkeypatch):
    monkeypatch.setattr(
        "agentos.cockpit.web.routes.registry.list_projects",
        lambda: [],
    )
    client = TestClient(create_app())
    response = client.get("/project/unknown-project/sdd")
    assert response.status_code == 404


def test_project_sdd_page_renders_with_mocked_project(monkeypatch, tmp_path):
    record = ProjectRefRecord(
        root_path=str(tmp_path),
        key="demo-project",
        source="git",
        last_opened_at=datetime(2026, 7, 1, 10, 0, 0),
    )
    monkeypatch.setattr(
        "agentos.cockpit.web.routes.registry.list_projects",
        lambda: [record],
    )
    
    # Create mock sdd artifacts
    sdd_dir = tmp_path / ".sdd"
    sdd_dir.mkdir()
    (sdd_dir / "proposal.md").write_text("My Proposal", encoding="utf-8")
    (sdd_dir / "tasks.md").write_text("- [ ] Task 1\n- [x] Task 2", encoding="utf-8")

    client = TestClient(create_app())
    response = client.get("/project/demo-project/sdd")
    
    assert response.status_code == 200
    assert "My Proposal" in response.text
    assert "Task 1" in response.text
    assert "Task 2" in response.text


def test_project_scanner_page_renders_and_handles_registration(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "agentos.cockpit.web.routes.registry.list_projects",
        lambda: [],
    )
    
    # Create directories to scan
    scan_dir = tmp_path / "projects"
    scan_dir.mkdir()
    proj1 = scan_dir / "proj1"
    proj1.mkdir()
    (proj1 / ".git").mkdir()
    (proj1 / ".sdd").mkdir()
    
    upserts = []
    def mock_upsert(key, path, source="detected"):
        upserts.append((key, path, source))
        return None
        
    monkeypatch.setattr(
        "agentos.cockpit.web.routes.registry.upsert_project",
        mock_upsert,
    )
    
    client = TestClient(create_app())
    
    # Test simple scan page view
    response = client.get(f"/scanner?target_dir={scan_dir}")
    assert response.status_code == 200
    assert "proj1" in response.text
    assert "Git detected" in response.text
    assert "SDD detected" in response.text
    
    # Test register action
    response = client.get(f"/scanner?target_dir={scan_dir}&action=register&register_path={proj1}&register_key=proj1")
    assert response.status_code == 200
    assert "Successfully registered project" in response.text
    assert "proj1" in response.text
    assert len(upserts) == 1
    assert upserts[0][0] == "proj1"

