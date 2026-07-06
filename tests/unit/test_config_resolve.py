"""Tests for resolve_config() precedence-aware global/project config resolution."""

import os

import pytest
import yaml

from agentos.core.config import (
    Config,
    _build_field_env_map,
    _global_home,
    resolve_config,
)


def _write_yaml(path, data: dict) -> None:
    path.write_text(yaml.safe_dump(data), encoding="utf-8")


@pytest.fixture
def isolated_home(tmp_path, monkeypatch):
    """Point HOME at a throwaway dir and chdir into an isolated project dir."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    project = tmp_path / "project"
    project.mkdir()
    (project / ".git").mkdir()
    monkeypatch.chdir(project)
    for var in ("QWEN_MODEL", "QWEN_API_KEY", "DASHSCOPE_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    return home, project


class TestFieldEnvMap:
    def test_composes_nested_prefixes(self):
        field_map = _build_field_env_map()
        assert field_map[("skills", "git_ops", "default_branch")] == "GITOPS_DEFAULT_BRANCH"
        assert field_map[("qwen", "model")] == "QWEN_MODEL"


class TestPrecedenceCriticalRegression:
    def test_real_env_beats_project_and_global_yaml(self, isolated_home, monkeypatch):
        """THE critical regression: a real process env var must win over both
        project-local and global config.yaml for the same key."""
        home, project = isolated_home
        monkeypatch.setenv("QWEN_MODEL", "C")
        _write_yaml(project / "config.yaml", {"qwen": {"model": "B"}})
        (home / ".aki").mkdir(exist_ok=True)
        _write_yaml(home / ".aki" / "config.yaml", {"qwen": {"model": "A"}})

        config = resolve_config()

        assert config.qwen.model == "C"


class TestTierMatrix:
    def test_explicit_config_flag_wins_over_everything(self, isolated_home, monkeypatch, tmp_path):
        home, project = isolated_home
        monkeypatch.setenv("QWEN_MODEL", "C")
        _write_yaml(project / "config.yaml", {"qwen": {"model": "B"}})
        (home / ".aki").mkdir(exist_ok=True)
        _write_yaml(home / ".aki" / "config.yaml", {"qwen": {"model": "A"}})
        override = tmp_path / "override.yaml"
        _write_yaml(override, {"qwen": {"model": "D"}})

        config = resolve_config(config_path=override)

        assert config.qwen.model == "D"

    def test_project_file_wins_over_global_file(self, isolated_home):
        home, project = isolated_home
        _write_yaml(project / "config.yaml", {"qwen": {"model": "B"}})
        (home / ".aki").mkdir(exist_ok=True)
        _write_yaml(home / ".aki" / "config.yaml", {"qwen": {"model": "A"}})

        config = resolve_config()

        assert config.qwen.model == "B"

    def test_global_file_wins_over_internal_default(self, isolated_home):
        home, _ = isolated_home
        (home / ".aki").mkdir(exist_ok=True)
        _write_yaml(home / ".aki" / "config.yaml", {"qwen": {"model": "A"}})

        config = resolve_config()

        assert config.qwen.model == "A"

    def test_internal_default_used_as_last_resort(self, isolated_home):
        config = resolve_config()
        assert config.qwen.model == "qwen-max"

    def test_missing_global_home_is_non_fatal(self, isolated_home):
        # isolated_home never creates ~/.aki
        config = resolve_config()
        assert config.qwen.model == "qwen-max"


class TestAdjacentTierAndTieBreak:
    def test_project_env_beats_global_yaml(self, isolated_home):
        home, project = isolated_home
        (project / ".env").write_text("QWEN_MODEL=proj-env-model\n", encoding="utf-8")
        (home / ".aki").mkdir(exist_ok=True)
        _write_yaml(home / ".aki" / "config.yaml", {"qwen": {"model": "global-yaml-model"}})

        config = resolve_config()

        assert config.qwen.model == "proj-env-model"

    def test_same_tier_yaml_wins_over_dotenv(self, isolated_home):
        home, project = isolated_home
        (project / ".env").write_text("QWEN_MODEL=from-dotenv\n", encoding="utf-8")
        _write_yaml(project / "config.yaml", {"qwen": {"model": "from-yaml"}})

        config = resolve_config()

        assert config.qwen.model == "from-yaml"


class TestEnvFileNone:
    def test_project_dotenv_value_not_selected_is_not_leaked_via_pydantic_dotenv(self, isolated_home, monkeypatch):
        """A real env var for a DIFFERENT key must not be overridden by pydantic's
        own built-in dotenv_settings re-reading ./.env behind our backs."""
        home, project = isolated_home
        monkeypatch.setenv("QWEN_MODEL", "from-real-env")
        (project / ".env").write_text("QWEN_MODEL=from-dotenv-should-not-win\n", encoding="utf-8")

        config = resolve_config()

        assert config.qwen.model == "from-real-env"


class TestComplexFieldsSurvivePruning:
    def test_list_field_from_yaml_only_resolves(self, isolated_home):
        home, project = isolated_home
        _write_yaml(project / "config.yaml", {"skills": {"enabled": ["git_ops"]}})

        config = resolve_config()

        assert config.skills.enabled == ["git_ops"]


class TestGetConfigFreshness:
    def test_reset_config_picks_up_new_files(self, isolated_home):
        from agentos.core.config import get_config, reset_config

        home, project = isolated_home
        config1 = get_config()
        assert config1.qwen.model == "qwen-max"

        reset_config()
        _write_yaml(project / "config.yaml", {"qwen": {"model": "fresh-model"}})
        config2 = get_config()
        assert config2.qwen.model == "fresh-model"
