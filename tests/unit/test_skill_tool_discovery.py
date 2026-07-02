from __future__ import annotations

from agentos.skills.base import Skill, SkillRegistry, SkillResult


class _FakeSkill(Skill):
    name = "fake"
    description = "test skill"

    def _helper_sync(self) -> str:
        """Sync helper, should never be exposed as a tool."""
        return "internal"

    async def do_thing(self, value: str) -> str:
        """Actual tool the model should see."""
        return value


def test_base_class_helpers_are_not_exposed_as_tools():
    """Regression: get_openai_tool (and any other Skill-base helper) must
    never leak into a skill's tool list — only subclass-defined async
    methods are real tools."""
    skill = _FakeSkill()
    assert "get_openai_tool" not in skill.functions
    assert "get_function_schema" not in skill.functions
    assert "execute" not in skill.functions


def test_sync_helper_methods_are_not_exposed_as_tools():
    skill = _FakeSkill()
    assert "_helper_sync" not in skill.functions


def test_async_subclass_methods_are_exposed_as_tools():
    skill = _FakeSkill()
    assert skill.functions == ["do_thing"]


def test_registry_tool_list_excludes_base_helpers():
    registry = SkillRegistry()
    registry.register(_FakeSkill())
    tool_names = [t["function"]["name"] for t in registry.get_all_tools()]
    assert tool_names == ["fake_do_thing"]
