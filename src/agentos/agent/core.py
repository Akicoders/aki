"""Agent core loop - the brain of Aki."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any, Optional, AsyncGenerator

from agentos.core.config import get_config, AgentConfig
from agentos.memory.repository import MemoryRepository, create_event
from agentos.memory.models import MemoryContext, EventType, MemoryEvent
from agentos.qwen.client import QwenClient, ChatResponse, get_qwen_client
from agentos.skills.base import SkillRegistry, SkillResult, get_skill_registry
from agentos.skills import BUILTIN_SKILLS

logger = logging.getLogger(__name__)


class AgentOS:
    """Main agent orchestration class."""

    def __init__(
        self,
        config: Optional[AgentConfig] = None,
        qwen_client: Optional[QwenClient] = None,
        memory: Optional[MemoryRepository] = None,
        skill_registry: Optional[SkillRegistry] = None,
    ):
        self.config = config or get_config().agent
        self.qwen = qwen_client or get_qwen_client()
        self.memory = memory or MemoryRepository()
        self.skills = skill_registry or get_skill_registry()
        self._init_skills()

    def _init_skills(self) -> None:
        """Initialize built-in skills from config."""
        skills_config = get_config().skills
        for skill_name in skills_config.enabled:
            if skill_name in BUILTIN_SKILLS and not self.skills.get(skill_name):
                skill_cls = BUILTIN_SKILLS[skill_name]
                skill_config = getattr(skills_config, skill_name, None)
                skill = skill_cls(skill_config.__dict__ if skill_config else None)
                self.skills.register(skill)
                logger.info(f"Initialized skill: {skill_name}")

    async def chat(
        self,
        user_input: str,
        project: str = "default",
        session_id: Optional[str] = None,
        stream: bool = False,
    ) -> str:
        """Main chat entry point."""
        if not session_id:
            session_id = f"sess_{uuid.uuid4().hex[:8]}"

        # 1. Store user input as event
        user_event = create_event(
            type=EventType.CONVERSATION,
            project=project,
            content=user_input,
            meta={"role": "user"},
            source="user",
            session_id=session_id,
        )
        logger.info(f"User [{session_id}]: {user_input[:100]}")

        # 2. Assemble context from memory
        context = self.memory.assemble_context(
            query=user_input,
            project=project,
            session_id=session_id,
            max_tokens=get_config().memory.max_context_tokens,
        )

        # 3. Build messages for LLM
        messages: list[dict[str, Any]] = self._build_messages(user_input, context, project)

        # 4. Get available tools
        tools: list[dict[str, Any]] = self.skills.get_all_tools()

        # 5. Reasoning loop
        response = await self._reasoning_loop(messages, tools, project, session_id)

        # 6. Store agent response
        agent_event = create_event(
            type=EventType.CONVERSATION,
            project=project,
            content=response,
            meta={"role": "assistant"},
            source="agent",
            session_id=session_id,
        )

        logger.info(f"Agent [{session_id}]: {response[:100]}")
        return response

    def _build_messages(
        self,
        user_input: str,
        context: MemoryContext,
        project: str,
    ) -> list[dict[str, Any]]:
        """Build message history for LLM."""
        system_prompt = self.config.system_prompt_template or (
            "You are Aki, an AI agent with persistent project memory for coding workflows. "
            "Help developers preserve durable facts, decisions, and procedures across sessions. "
            "Be concise, practical, and careful with context budgets."
        )

        messages = [
            {"role": "system", "content": system_prompt},
        ]

        # Inject memory context
        memory_text = context.format_for_prompt(max_tokens=get_config().memory.max_context_tokens)
        if memory_text:
            messages.append({
                "role": "system",
                "content": self.config.memory_injection_template.format(memory_context=memory_text)
                if self.config.memory_injection_template
                else f"Contexto de memoria:\n{memory_text}"
            })

        # Inject skills
        skills_text = "\n".join(
            f"- {s.name}: {s.description} — {', '.join(s.functions)}"
            for s in context.skills if s.enabled
        )
        if skills_text:
            messages.append({
                "role": "system",
                "content": self.config.skill_injection_template.format(skills_list=skills_text)
                if self.config.skill_injection_template
                else f"Herramientas disponibles:\n{skills_text}"
            })

        # Current user input
        messages.append({"role": "user", "content": user_input})

        return messages

    async def _reasoning_loop(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        project: str,
        session_id: str,
    ) -> str:
        """Execute reasoning loop with tool calls."""
        max_iterations = self.config.max_iterations
        temperature = self.config.temperature

        for iteration in range(max_iterations):
            logger.debug(f"Reasoning iteration {iteration + 1}/{max_iterations}")

            response: ChatResponse = await self.qwen.chat(
                messages=messages,
                tools=tools,
                tool_choice="auto",
                temperature=temperature,
            )

            # Add assistant message to history
            messages.append({
                "role": "assistant",
                "content": response.content,
                "tool_calls": response.tool_calls,
            })

            # If no tool calls, we're done
            if not response.tool_calls:
                return response.content

            # Execute tool calls
            for tool_call in response.tool_calls:
                fn_name = tool_call["function"]["name"]
                fn_args = tool_call["function"]["arguments"]
                tool_call_id = tool_call["id"]

                # Parse skill_name.function_name
                if "_" in fn_name:
                    skill_name, fn_name = fn_name.split("_", 1)
                else:
                    skill_name, fn_name = "unknown", fn_name

                logger.info(f"Tool call: {skill_name}.{fn_name}({fn_args})")

                result: SkillResult = await self.skills.execute(skill_name, fn_name, fn_args)

                # Store tool result
                tool_result_msg = {
                    "role": "tool",
                    "tool_call_id": tool_call_id,
                    "content": result.model_dump_json() if hasattr(result, 'model_dump_json') else str(result),
                }
                messages.append(tool_result_msg)

                # Log tool execution
                create_event(
                    type=EventType.CONVERSATION,
                    project=project,
                    content=f"Tool: {skill_name}.{fn_name} -> {'ok' if result.success else 'error'}",
                    meta={
                        "tool": f"{skill_name}.{fn_name}",
                        "args": fn_args,
                        "success": result.success,
                        "error": result.error,
                    },
                    source="agent",
                    session_id=session_id,
                )

        # Max iterations reached
        return "Se alcanzó el máximo de iteraciones. ¿Quieres que intente de otra forma?"

    async def stream_chat(
        self,
        user_input: str,
        project: str = "default",
        session_id: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        """Stream chat response (not fully implemented with tools yet)."""
        response = await self.chat(user_input, project, session_id)
        for chunk in response.split():
            yield chunk + " "

    # --- Memory shortcuts ---

    async def remember(
        self,
        content: str,
        project: str = "default",
        type: EventType = EventType.USER_PREFERENCE,
        meta: Optional[dict] = None,
    ) -> MemoryEvent:
        """Explicitly store a memory."""
        event = create_event(
            type=type,
            project=project,
            content=content,
            meta=meta or {},
            source="user",
        )
        return event

    async def recall(self, query: str, project: str = "default") -> MemoryContext:
        """Query memory directly."""
        return self.memory.assemble_context(query=query, project=project)

    async def get_facts(self, project: str = "default") -> list:
        """Get all facts for a project."""
        return self.memory.get_facts_by_scope(f"project:{project}")

    async def set_fact(self, key: str, value: str, project: str = "default", confidence: float = 1.0) -> None:
        """Set a fact manually."""
        from agentos.memory.models import MemoryFact
        fact = MemoryFact(key=key, value=value, scope=f"project:{project}", confidence=confidence)
        self.memory.upsert_fact(fact)


# Global agent instance
_agent: Optional[AgentOS] = None


def get_agent() -> AgentOS:
    global _agent
    if _agent is None:
        _agent = AgentOS()
    return _agent


def reset_agent() -> None:
    global _agent
    _agent = None
