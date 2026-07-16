from __future__ import annotations

from datetime import datetime
from pathlib import Path

from sqlalchemy import select
from typer.testing import CliRunner

from agentos.cli.cockpit import build_cockpit_snapshot, resolve_project_ref
from agentos.cli.main import app
from agentos.memory.database import Database
from agentos.memory.models import EventType, MemoryEventModel, MemoryFactModel


runner = CliRunner()


def test_resolve_project_ref_prefers_git_root(tmp_path):
    repo_root = tmp_path / "repo-root"
    nested = repo_root / "src" / "feature"
    nested.mkdir(parents=True)
    (repo_root / ".git").mkdir()

    project = resolve_project_ref(nested)

    assert project is not None
    assert project.root_path == repo_root
    assert project.key == "repo-root"
    assert project.source == "git"


def test_resolve_project_ref_accepts_marker_root(tmp_path):
    project_root = tmp_path / "marker-project"
    project_root.mkdir()
    (project_root / "pyproject.toml").write_text("[project]\nname='marker-project'\n", encoding="utf-8")

    project = resolve_project_ref(project_root)

    assert project is not None
    assert project.root_path == project_root
    assert project.source == "marker"


def test_resolve_project_ref_rejects_plain_directory(tmp_path):
    plain = tmp_path / "notes"
    plain.mkdir()

    assert resolve_project_ref(plain) is None


def test_build_cockpit_snapshot_reads_memory_summary(tmp_path):
    project_root = tmp_path / "memory-project"
    project_root.mkdir()
    (project_root / "pyproject.toml").write_text("[project]\nname='memory-project'\n", encoding="utf-8")

    db = Database(project_root / "data" / "agentos.db")
    try:
        with db.session() as session:
            session.add(
                MemoryFactModel(
                    id="fact_1",
                    key="package-manager",
                    value="uv",
                    scope="project:memory-project",
                    confidence=1.0,
                    updated_at=datetime(2026, 7, 1, 10, 0, 0),
                )
            )
            session.add(
                MemoryEventModel(
                    id="evt_decision",
                    type=EventType.DECISION,
                    project="memory-project",
                    content="We use SDD for feature delivery.",
                    meta="{}",
                    timestamp=datetime(2026, 7, 1, 11, 0, 0),
                    source="user",
                )
            )
            session.add(
                MemoryEventModel(
                    id="evt_workflow",
                    type=EventType.CODE_CHANGE,
                    project="memory-project",
                    content="Recently updated the MCP setup flow.",
                    meta="{}",
                    timestamp=datetime(2026, 7, 1, 12, 0, 0),
                    source="agent",
                )
            )
            session.execute(select(MemoryFactModel))
    finally:
        db.close()

    project = resolve_project_ref(project_root)
    assert project is not None

    snapshot = build_cockpit_snapshot(project)

    assert snapshot.memory_summary.recent_facts[0].key == "package-manager"
    assert snapshot.memory_summary.latest_decision == "We use SDD for feature delivery."
    assert snapshot.memory_summary.recent_workflow_memory == "Recently updated the MCP setup flow."
    assert snapshot.project.last_memory_activity_at == datetime(2026, 7, 1, 12, 0, 0)


def test_build_cockpit_snapshot_skips_upsert_when_record_open_false(tmp_path, monkeypatch):
    project_root = tmp_path / "readonly-project"
    project_root.mkdir()
    (project_root / "pyproject.toml").write_text("[project]\nname='readonly-project'\n", encoding="utf-8")

    project = resolve_project_ref(project_root)
    assert project is not None

    calls = []
    monkeypatch.setattr(
        "agentos.cli.cockpit.registry.upsert_project",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )

    build_cockpit_snapshot(project, record_open=False)

    assert calls == []


def test_build_cockpit_snapshot_upserts_by_default(tmp_path, monkeypatch):
    project_root = tmp_path / "default-project"
    project_root.mkdir()
    (project_root / "pyproject.toml").write_text("[project]\nname='default-project'\n", encoding="utf-8")

    project = resolve_project_ref(project_root)
    assert project is not None

    calls = []
    monkeypatch.setattr(
        "agentos.cli.cockpit.registry.upsert_project",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )

    build_cockpit_snapshot(project)

    assert len(calls) == 1


def test_build_cockpit_snapshot_writes_breadcrumb_when_record_open(tmp_path, monkeypatch):
    project_root = tmp_path / "breadcrumb-project"
    project_root.mkdir()
    (project_root / "pyproject.toml").write_text("[project]\nname='breadcrumb-project'\n", encoding="utf-8")

    project = resolve_project_ref(project_root)
    assert project is not None

    monkeypatch.setattr("agentos.cli.cockpit.registry.upsert_project", lambda *args, **kwargs: None)

    calls = []
    monkeypatch.setattr(
        "agentos.cli.cockpit.write_breadcrumb",
        lambda root_path: calls.append(root_path),
    )

    build_cockpit_snapshot(project, record_open=True)

    assert calls == [project.root_path]


def test_build_cockpit_snapshot_skips_breadcrumb_when_record_open_false(tmp_path, monkeypatch):
    project_root = tmp_path / "no-breadcrumb-project"
    project_root.mkdir()
    (project_root / "pyproject.toml").write_text("[project]\nname='no-breadcrumb-project'\n", encoding="utf-8")

    project = resolve_project_ref(project_root)
    assert project is not None

    monkeypatch.setattr("agentos.cli.cockpit.registry.upsert_project", lambda *args, **kwargs: None)

    calls = []
    monkeypatch.setattr(
        "agentos.cli.cockpit.write_breadcrumb",
        lambda root_path: calls.append(root_path),
    )

    build_cockpit_snapshot(project, record_open=False)

    assert calls == []


def test_root_command_opens_cockpit_overview_for_project(tmp_path, monkeypatch):
    project_root = tmp_path / "cockpit-project"
    project_root.mkdir()
    (project_root / "pyproject.toml").write_text("[project]\nname='cockpit-project'\n", encoding="utf-8")
    sdd_dir = project_root / "docs" / "sdd"
    sdd_dir.mkdir(parents=True)
    (sdd_dir / "proposal.md").write_text("# Proposal\n", encoding="utf-8")

    monkeypatch.chdir(project_root)

    result = runner.invoke(app, [])

    assert result.exit_code == 0
    assert "OPERATIONAL COCKPIT" in result.output.upper()
    assert "Action Required" in result.output
    assert "Project Health" in result.output
    assert "Memory" in result.output
    assert "SDD Status" in result.output
    assert project_root.name in result.output
    assert "Root" in result.output


def test_cockpit_web_flag_dispatches_to_run_server(tmp_path, monkeypatch):
    project_root = tmp_path / "web-project"
    project_root.mkdir()
    (project_root / "pyproject.toml").write_text("[project]\nname='web-project'\n", encoding="utf-8")
    monkeypatch.chdir(project_root)

    calls = []
    monkeypatch.setattr(
        "agentos.cli.main.run_server",
        lambda settings: calls.append(settings),
    )

    result = runner.invoke(app, ["cockpit", "--web", "--host", "127.0.0.1", "--port", "9001"])

    assert result.exit_code == 0
    assert len(calls) == 1
    assert calls[0].host == "127.0.0.1"
    assert calls[0].port == 9001
    assert "OPERATIONAL COCKPIT" not in result.output.upper()


def test_cockpit_web_flag_reports_port_conflict_cleanly(tmp_path, monkeypatch):
    project_root = tmp_path / "conflict-project"
    project_root.mkdir()
    (project_root / "pyproject.toml").write_text("[project]\nname='conflict-project'\n", encoding="utf-8")
    monkeypatch.chdir(project_root)

    def _raise_address_in_use(settings):
        raise OSError("[Errno 98] Address already in use")

    monkeypatch.setattr("agentos.cli.main.run_server", _raise_address_in_use)

    result = runner.invoke(app, ["cockpit", "--web", "--port", "9002"])

    assert result.exit_code != 0
    assert "9002" not in result.output or "port" in result.output.lower()
    assert "--port" in result.output
    assert "Traceback" not in result.output


def test_cockpit_without_web_flag_still_renders_terminal_cockpit(tmp_path, monkeypatch):
    project_root = tmp_path / "terminal-project"
    project_root.mkdir()
    (project_root / "pyproject.toml").write_text("[project]\nname='terminal-project'\n", encoding="utf-8")
    monkeypatch.chdir(project_root)

    calls = []
    monkeypatch.setattr(
        "agentos.cli.main.run_server",
        lambda settings: calls.append(settings),
    )

    result = runner.invoke(app, ["cockpit"])

    assert result.exit_code == 0
    assert calls == []
    assert "OPERATIONAL COCKPIT" in result.output.upper()


def test_root_command_falls_back_to_projects_browse(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, [])

    assert result.exit_code == 0
    assert "Projects Browse" in result.output
    assert "does not resolve to a recognizable project root" in result.output
    assert "aki cockpit" in result.output
    assert "/absolute/path/to/project" in result.output


def test_cockpit_health_drill_down_renders_detail(tmp_path, monkeypatch):
    project_root = tmp_path / "detail-project"
    project_root.mkdir()
    (project_root / "pyproject.toml").write_text("[project]\nname='detail-project'\n", encoding="utf-8")

    monkeypatch.chdir(project_root)

    result = runner.invoke(app, ["cockpit", "health"])

    assert result.exit_code == 0
    assert "Project Health Detail" in result.output
    assert "tests" in result.output
    assert "sdd" in result.output
    assert "git" in result.output
    assert "env" in result.output
    assert "mcp" in result.output


def test_projects_browse_command_shows_onboarding_when_empty(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["projects", "browse"], input="\n")

    assert result.exit_code == 0
    assert "Onboarding" in result.output
    assert "No known projects yet" in result.output


def test_projects_browse_command_lists_registered_project(tmp_path, monkeypatch):
    project_root = tmp_path / "listed-project"
    project_root.mkdir()
    (project_root / "pyproject.toml").write_text("[project]\nname='listed-project'\n", encoding="utf-8")
    monkeypatch.chdir(project_root)

    # Registering the project happens as a side effect of opening the cockpit.
    runner.invoke(app, [])

    result = runner.invoke(app, ["projects", "browse"], input="\n")

    assert result.exit_code == 0
    assert "Known Projects" in result.output
    assert "listed" in result.output


def test_projects_browse_command_filters_by_query(tmp_path, monkeypatch):
    project_root = tmp_path / "filterable-project"
    project_root.mkdir()
    (project_root / "pyproject.toml").write_text("[project]\nname='filterable-project'\n", encoding="utf-8")
    monkeypatch.chdir(project_root)
    runner.invoke(app, [])

    result = runner.invoke(app, ["projects", "browse", "--filter", "no-match-anywhere"], input="\n")

    assert result.exit_code == 0
    assert "No projects match filter" in result.output


def test_projects_browse_command_select_opens_cockpit(tmp_path, monkeypatch):
    project_root = tmp_path / "selectable-project"
    project_root.mkdir()
    (project_root / "pyproject.toml").write_text("[project]\nname='selectable-project'\n", encoding="utf-8")
    monkeypatch.chdir(project_root)
    runner.invoke(app, [])

    result = runner.invoke(app, ["projects", "browse"], input="1\n")

    assert result.exit_code == 0
    assert "Known Projects" in result.output
    assert "OPERATIONAL COCKPIT" in result.output.upper()
