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


def test_root_lists_registered_projects_as_html(monkeypatch):
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

    response = client.get("/")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "demo-project" in response.text
