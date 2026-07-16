"""Specialized agent profile contracts."""

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


AgentRole = Literal["planner", "builder", "reviewer", "custom"]
MemoryScope = Literal["project", "session", "global", "disabled"]


class ToolPolicy(BaseModel):
    """Allow-policy for tools exposed to a specialized agent profile."""

    allowed: list[str] = Field(default_factory=list)
    deny_all: bool = False

    @model_validator(mode="after")
    def _require_allow_list_or_deny_all(self) -> "ToolPolicy":
        if not self.allowed and not self.deny_all:
            raise ValueError("tools must define allowed entries or set deny_all=true")
        if self.allowed and self.deny_all:
            raise ValueError("tools cannot define allowed entries when deny_all=true")
        return self

    def allows(self, tool_name: str) -> bool:
        """Return whether a tool/function name is allowed by this profile."""
        if self.deny_all:
            return False
        return tool_name in self.allowed


class MemoryPolicy(BaseModel):
    """Memory scope declared by a specialized agent profile."""

    scope: MemoryScope


class DelegationMetadata(BaseModel):
    """Gates whether this profile's `_reasoning_loop` exposes the synthetic
    `delegate` tool to the model. When `enabled` is False, the tool schema is
    withheld at depth 0 and `_run_delegation` also refuses to execute as a
    defensive guard (in case a stale tool-call from conversation history or a
    mid-conversation profile switch still reaches it).

    `strategy` remains reserved for future delegation-strategy selection and
    has no runtime effect yet.
    """

    enabled: bool = True
    strategy: str | None = None


class AgentProfile(BaseModel):
    """Declarative identity and policy for one specialized agent."""

    id: str
    name: str
    description: str
    role: AgentRole
    prompt_template: str
    model: str | None = None
    temperature: float | None = None
    max_iterations: int | None = None
    tools: ToolPolicy
    memory: MemoryPolicy
    delegation: DelegationMetadata = Field(default_factory=DelegationMetadata)

    @field_validator("id")
    @classmethod
    def _validate_stable_id(cls, value: str) -> str:
        if not value:
            raise ValueError("id is required")
        if not all(
            char.islower() or char.isdigit() or char in {"-", "_"}
            for char in value
        ):
            raise ValueError("id must use lowercase letters, digits, hyphens, or underscores")
        return value

    @field_validator("name", "description", "prompt_template")
    @classmethod
    def _validate_required_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value is required")
        return value
