"""Skills framework for AgentOS."""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Optional
from inspect import signature, getdoc
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


@dataclass
class FunctionSchema:
    name: str
    description: str
    parameters: dict[str, Any]
    required: list[str] = field(default_factory=list)


class SkillResult(BaseModel):
    success: bool
    data: Any = None
    error: Optional[str] = None
    meta: dict[str, Any] = Field(default_factory=dict)


class Skill(ABC):
    """Base class for all skills."""

    name: str
    description: str
    functions: list[str] = Field(default_factory=list)
    enabled: bool = True
    config: dict[str, Any] = Field(default_factory=dict)

    def __init__(self, config: Optional[dict] = None):
        if config:
            self.config.update(config)
        # Auto-discover functions
        self.functions = self._discover_functions()

    def _discover_functions(self) -> list[str]:
        """Find all public async methods that don't start with _."""
        return [
            name for name in dir(self)
            if not name.startswith("_")
            and callable(getattr(self, name))
            and name not in {"get_function_schema", "execute"}
        ]

    def get_function_schema(self, fn_name: str) -> Optional[FunctionSchema]:
        """Generate OpenAI function schema for a function."""
        fn = getattr(self, fn_name, None)
        if not fn or not callable(fn):
            return None

        sig = signature(fn)
        doc = getdoc(fn) or ""

        # Parse parameters
        properties = {}
        required = []
        for param_name, param in sig.parameters.items():
            if param_name == "self":
                continue
            param_type = param.annotation if param.annotation != param.empty else str
            properties[param_name] = self._type_to_json_schema(param_type)
            if param.default == param.empty:
                required.append(param_name)

        return FunctionSchema(
            name=f"{self.name}.{fn_name}",
            description=doc.strip(),
            parameters={
                "type": "object",
                "properties": properties,
                "required": required,
            },
            required=required,
        )

    def _type_to_json_schema(self, typ: Any) -> dict[str, Any]:
        """Convert Python type to JSON Schema."""
        if typ == str:
            return {"type": "string"}
        elif typ == int:
            return {"type": "integer"}
        elif typ == float:
            return {"type": "number"}
        elif typ == bool:
            return {"type": "boolean"}
        elif typ == list or (hasattr(typ, "__origin__") and typ.__origin__ == list):
            return {"type": "array", "items": {}}
        elif typ == dict or (hasattr(typ, "__origin__") and typ.__origin__ == dict):
            return {"type": "object"}
        elif typ == Optional[str] or (hasattr(typ, "__origin__") and typ.__origin__ is Optional and typ.__args__[0] == str):
            return {"type": "string"}
        return {"type": "string"}

    def get_openai_tool(self, fn_name: str) -> Optional[dict[str, Any]]:
        """Get OpenAI-compatible tool definition."""
        schema = self.get_function_schema(fn_name)
        if not schema:
            return None
        return {
            "type": "function",
            "function": {
                "name": schema.name.replace(".", "_"),
                "description": schema.description,
                "parameters": schema.parameters,
            },
        }

    @abstractmethod
    async def execute(self, function: str, arguments: dict[str, Any]) -> SkillResult:
        """Execute a function by name with arguments."""
        fn = getattr(self, function, None)
        if not fn:
            return SkillResult(success=False, error=f"Function {function} not found")
        try:
            result = await fn(**arguments)
            return SkillResult(success=True, data=result)
        except Exception as e:
            logger.exception(f"Skill {self.name}.{function} failed")
            return SkillResult(success=False, error=str(e))


class SkillRegistry:
    """Registry for managing skills."""

    def __init__(self):
        self._skills: dict[str, Skill] = {}

    def register(self, skill: Skill) -> None:
        self._skills[skill.name] = skill
        logger.info(f"Registered skill: {skill.name}")

    def unregister(self, name: str) -> None:
        if name in self._skills:
            del self._skills[name]
            logger.info(f"Unregistered skill: {name}")

    def get(self, name: str) -> Optional[Skill]:
        return self._skills.get(name)

    def list(self, enabled_only: bool = True) -> list[Skill]:
        skills = list(self._skills.values())
        if enabled_only:
            skills = [s for s in skills if s.enabled]
        return skills

    def get_all_tools(self) -> list[dict[str, Any]]:
        """Get all OpenAI tool definitions from all skills."""
        tools = []
        for skill in self._skills.values():
            if not skill.enabled:
                continue
            for fn_name in skill.functions:
                tool = skill.get_openai_tool(fn_name)
                if tool:
                    tools.append(tool)
        return tools

    async def execute(self, skill_name: str, function: str, arguments: dict[str, Any]) -> SkillResult:
        skill = self.get(skill_name)
        if not skill:
            return SkillResult(success=False, error=f"Skill {skill_name} not found")
        if not skill.enabled:
            return SkillResult(success=False, error=f"Skill {skill_name} is disabled")
        return await skill.execute(function, arguments)


# Global registry
_registry: Optional[SkillRegistry] = None


def get_skill_registry() -> SkillRegistry:
    global _registry
    if _registry is None:
        _registry = SkillRegistry()
    return _registry