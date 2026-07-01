"""Aki - AI agent with portable project memory."""

from __future__ import annotations

from importlib import import_module

__version__ = "0.1.0"
__author__ = "Paul"
__license__ = "MIT"

_LAZY_EXPORTS = {
    "AgentOS": ("agentos.agent.core", "AgentOS"),
    "get_agent": ("agentos.agent.core", "get_agent"),
    "Config": ("agentos.core.config", "Config"),
    "get_config": ("agentos.core.config", "get_config"),
    "MemoryEvent": ("agentos.memory.models", "MemoryEvent"),
    "MemoryFact": ("agentos.memory.models", "MemoryFact"),
    "MemoryContext": ("agentos.memory.models", "MemoryContext"),
    "EventType": ("agentos.memory.models", "EventType"),
    "MemoryRepository": ("agentos.memory.repository", "MemoryRepository"),
    "QwenClient": ("agentos.qwen.client", "QwenClient"),
    "get_qwen_client": ("agentos.qwen.client", "get_qwen_client"),
    "Skill": ("agentos.skills.base", "Skill"),
    "SkillRegistry": ("agentos.skills.base", "SkillRegistry"),
    "SkillResult": ("agentos.skills.base", "SkillResult"),
    "get_skill_registry": ("agentos.skills.base", "get_skill_registry"),
}


def __getattr__(name: str):
    if name not in _LAZY_EXPORTS:
        raise AttributeError(f"module 'agentos' has no attribute {name!r}")

    module_name, attr_name = _LAZY_EXPORTS[name]
    value = getattr(import_module(module_name), attr_name)
    globals()[name] = value
    return value

__all__ = [
    "AgentOS",
    "get_agent",
    "Config",
    "get_config",
    "MemoryEvent",
    "MemoryFact",
    "Skill",
    "MemoryContext",
    "EventType",
    "MemoryRepository",
    "QwenClient",
    "get_qwen_client",
    "Skill",
    "SkillRegistry",
    "SkillResult",
    "get_skill_registry",
]
