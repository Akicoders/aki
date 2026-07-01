"""Tests for skills loading."""

import pytest

from agentos.skills import load_skills, BUILTIN_SKILLS
from agentos.skills.base import get_skill_registry
from agentos.core.config import get_config


class TestSkillsLoading:
    def test_load_skills_populates_registry(self):
        load_skills()
        registry = get_skill_registry()
        skill_list = registry.list(enabled_only=False)
        assert len(skill_list) > 0

    def test_load_skills_loads_all_configured(self):
        config = get_config()
        load_skills(config.skills)
        registry = get_skill_registry()
        for skill_name in config.skills.enabled:
            assert registry.get(skill_name) is not None, f"Skill {skill_name} not loaded"

    def test_load_skills_does_not_duplicate(self):
        load_skills()
        load_skills()
        registry = get_skill_registry()
        skill_list = registry.list(enabled_only=False)
        names = [s.name for s in skill_list]
        assert len(names) == len(set(names)), "Duplicate skills loaded"

    def test_builtin_skills_dict_has_expected_skills(self):
        expected = {"git_ops", "filesystem", "web_search", "n8n_trigger", "scheduler", "code_intel"}
        assert set(BUILTIN_SKILLS.keys()) == expected
