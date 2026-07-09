from __future__ import annotations

from typer.testing import CliRunner

from agentos.cli.cockpit import resolve_project_ref
from agentos.cli.main import app
from agentos.cockpit.navigation import CockpitUIState, run_cockpit_loop

runner = CliRunner()


def _make_project(tmp_path):
    project_root = tmp_path / "nav-project"
    project_root.mkdir()
    (project_root / "pyproject.toml").write_text("[project]\nname='nav-project'\n", encoding="utf-8")
    return resolve_project_ref(project_root)


def test_cockpit_ui_state_defaults():
    state = CockpitUIState()

    assert state.current_view == "overview"
    assert state.selected_panel == 0
    assert state.selected_index == 0
    assert state.filter_query == ""
    assert state.refresh_in_progress is False


def test_run_cockpit_loop_drills_into_panel_detail_then_item_detail(tmp_path, capsys):
    project = _make_project(tmp_path)
    keys = iter(["", "", "q"])  # Enter (overview->panel), Enter (panel->item), quit

    def fake_ask(_prompt: str) -> str:
        return next(keys)

    exit_code = run_cockpit_loop(runner_console(), project, input_func=fake_ask)

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "Project Health Detail" not in output  # default focused panel is Action Required
    assert "Action Required Detail" in output
    assert "Item Detail" in output


def test_run_cockpit_loop_back_and_overview_navigation(tmp_path):
    project = _make_project(tmp_path)
    keys = iter(["", "b", "g", "q"])

    def fake_ask(_prompt: str) -> str:
        return next(keys)

    exit_code = run_cockpit_loop(runner_console(), project, input_func=fake_ask)

    assert exit_code == 0


def test_run_cockpit_loop_refresh_and_filter(tmp_path):
    project = _make_project(tmp_path)
    keys = iter(["r", "/", "sdd", "q"])

    def fake_ask(_prompt: str) -> str:
        return next(keys)

    exit_code = run_cockpit_loop(runner_console(), project, input_func=fake_ask)

    assert exit_code == 0


def test_run_cockpit_loop_tab_and_list_navigation(tmp_path):
    project = _make_project(tmp_path)
    keys = iter(["tab", "j", "k", "q"])

    def fake_ask(_prompt: str) -> str:
        return next(keys)

    exit_code = run_cockpit_loop(runner_console(), project, input_func=fake_ask)

    assert exit_code == 0


def test_cockpit_interactive_flag_runs_navigation_loop(tmp_path, monkeypatch):
    project_root = tmp_path / "interactive-project"
    project_root.mkdir()
    (project_root / "pyproject.toml").write_text("[project]\nname='interactive-project'\n", encoding="utf-8")
    monkeypatch.chdir(project_root)

    # Mock the Textual app's run method so it doesn't try to draw to the terminal in tests
    run_called = False
    
    def fake_run(self, *args, **kwargs):
        nonlocal run_called
        run_called = True
        return None
        
    monkeypatch.setattr("agentos.cockpit.tui.app.AkiCockpitApp.run", fake_run)

    result = runner.invoke(app, ["cockpit", "--interactive"])

    assert result.exit_code == 0
    assert run_called is True


def runner_console():
    from rich.console import Console

    return Console(force_terminal=False, width=100)
