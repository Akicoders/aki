"""Tests for destructive-call metadata on Skill / SkillRegistry."""

from __future__ import annotations

from agentos.skills.base import Skill, SkillRegistry
from agentos.skills.filesystem import FilesystemSkill


class _PlainSkill(Skill):
    name = "plain"
    description = "test skill with no destructive functions declared"

    async def do_thing(self, value: str) -> str:
        """Actual tool."""
        return value


def test_skill_default_destructive_functions_empty():
    skill = _PlainSkill()
    assert skill.destructive_functions == frozenset()
    assert skill.is_destructive("anything") is False


def test_filesystem_write_append_delete_are_destructive():
    skill = FilesystemSkill()
    assert skill.is_destructive("write") is True
    assert skill.is_destructive("append") is True
    assert skill.is_destructive("delete") is True


def test_filesystem_reads_are_not_destructive():
    skill = FilesystemSkill()
    for fn_name in ("read", "list", "glob", "search", "exists"):
        assert skill.is_destructive(fn_name) is False


def test_registry_is_destructive_true_for_filesystem_write():
    registry = SkillRegistry()
    registry.register(FilesystemSkill())
    assert registry.is_destructive("filesystem", "write") is True


def test_registry_is_destructive_false_for_unknown_skill_or_fn():
    registry = SkillRegistry()
    registry.register(FilesystemSkill())
    assert registry.is_destructive("unknown_skill", "write") is False
    assert registry.is_destructive("filesystem", "unknown_fn") is False


def test_get_all_tools_filesystem_write_reports_destructive_true():
    registry = SkillRegistry()
    registry.register(FilesystemSkill())
    tools = {t["function"]["name"]: t["function"] for t in registry.get_all_tools()}
    assert tools["filesystem_write"]["destructive"] is True
    assert tools["filesystem_append"]["destructive"] is True
    assert tools["filesystem_delete"]["destructive"] is True


def test_get_all_tools_filesystem_read_reports_destructive_false():
    registry = SkillRegistry()
    registry.register(FilesystemSkill())
    tools = {t["function"]["name"]: t["function"] for t in registry.get_all_tools()}
    for name in ("filesystem_read", "filesystem_list", "filesystem_glob", "filesystem_search", "filesystem_exists"):
        assert tools[name]["destructive"] is False


def test_get_all_tools_other_skill_defaults_destructive_false():
    registry = SkillRegistry()
    registry.register(_PlainSkill())
    tools = {t["function"]["name"]: t["function"] for t in registry.get_all_tools()}
    assert tools["plain_do_thing"]["destructive"] is False
