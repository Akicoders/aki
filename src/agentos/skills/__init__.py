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
]

BUILTIN_SKILLS = {
    "git_ops": GitOpsSkill,
    "filesystem": FilesystemSkill,
    "web_search": WebSearchSkill,
    "n8n_trigger": N8nTriggerSkill,
    "scheduler": SchedulerSkill,
    "code_intel": CodeIntelSkill,
}