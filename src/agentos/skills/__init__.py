"""Skills package - built-in skills."""

from agentos.skills.git_ops import GitOpsSkill
from agentos.skills.filesystem import FilesystemSkill
from agentos.skills.web_search import WebSearchSkill
from agentos.skills.n8n_trigger import N8nTriggerSkill
from agentos.skills.scheduler import SchedulerSkill
from agentos.skills.code_intel import CodeIntelSkill

__all__ = [
    "GitOpsSkill",
    "FilesystemSkill",
    "WebSearchSkill",
    "N8nTriggerSkill",
    "SchedulerSkill",
    "CodeIntelSkill",
    "BUILTIN_SKILLS",
    "load_skills",
]

BUILTIN_SKILLS = {
    "git_ops": GitOpsSkill,
    "filesystem": FilesystemSkill,
    "web_search": WebSearchSkill,
    "n8n_trigger": N8nTriggerSkill,
    "scheduler": SchedulerSkill,
    "code_intel": CodeIntelSkill,
}


def load_skills(config=None) -> None:
    """Load built-in skills into the global registry based on config."""
    from agentos.skills.base import get_skill_registry
    from agentos.core.config import get_config

    registry = get_skill_registry()
    skills_config = config or get_config().skills

    for skill_name in skills_config.enabled:
        if skill_name in BUILTIN_SKILLS and not registry.get(skill_name):
            skill_cls = BUILTIN_SKILLS[skill_name]
            skill_config = getattr(skills_config, skill_name, None)
            skill = skill_cls(skill_config.__dict__ if skill_config else None)
            registry.register(skill)