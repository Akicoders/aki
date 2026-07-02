"""Agent core loop - the brain of Aki."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, AsyncGenerator, Callable, Optional

from agentos.core.config import get_config, AgentConfig
from agentos.memory.repository import MemoryRepository, create_event, render_checkpoint
from agentos.memory.repository import CHECKPOINT_REHYDRATION_CHAR_CAP
from agentos.memory.models import MemoryContext, EventType, MemoryEvent
from agentos.qwen.client import QwenClient, ChatResponse, get_qwen_client
from agentos.skills.base import SkillRegistry, SkillResult, get_skill_registry
from agentos.skills import BUILTIN_SKILLS
from agentos.sdd.detector import detect_sdd_artifacts, summarize_sdd_context

logger = logging.getLogger(__name__)

# --- Deferred config (see follow-up: wire into AgentConfig) ---
CHECKPOINT_CADENCE_TURNS = 1  # write checkpoint every N turns (1 = every turn)

StatusCallback = Callable[[str], None]


@dataclass
class ReasoningOutcome:
    """Result of `_reasoning_loop`: final response text plus checkpoint-relevant metadata."""

    response: str
    last_tool_summary: str
    exhausted: bool


def _notify_status(status_callback: Optional[StatusCallback], message: str) -> None:
    if status_callback is not None:
        status_callback(message)


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
        status_callback: Optional[StatusCallback] = None,
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
        _notify_status(status_callback, "Collecting project context")
        context = self.memory.assemble_context(
            query=user_input,
            project=project,
            session_id=session_id,
            max_tokens=get_config().memory.max_context_tokens,
        )

        # 3. Build messages for LLM
        messages: list[dict[str, Any]] = self._build_messages(
            user_input, context, project, session_id=session_id
        )

        # 4. Get available tools
        tools: list[dict[str, Any]] = self.skills.get_all_tools()

        # 5. Reasoning loop
        _notify_status(status_callback, "Reasoning with Qwen")
        outcome = await self._reasoning_loop(messages, tools, project, session_id)
        response = outcome.response

        # 6. Store agent response
        _notify_status(status_callback, "Saving conversation")
        agent_event = create_event(
            type=EventType.CONVERSATION,
            project=project,
            content=response,
            meta={"role": "assistant"},
            source="agent",
            session_id=session_id,
        )

        # 6b. Persist structured checkpoint (mutable current-state), every turn
        # (success or iteration-exhaustion), see design.md section 4a.
        self.memory.write_checkpoint(
            project=project,
            session_id=session_id,
            goal=user_input,
            last_response=response,
            last_tool_result=outcome.last_tool_summary,
            iterations_exhausted=outcome.exhausted,
        )

        logger.info(f"Agent [{session_id}]: {response[:100]}")
        return response

    def _build_messages(
        self,
        user_input: str,
        context: MemoryContext,
        project: str,
        session_id: Optional[str] = None,
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

        # Reserved checkpoint slot: injected BEFORE the memory-context message,
        # read by exact (project, session_id) key, and deliberately NOT routed
        # through context.format_for_prompt / _fit_context_to_budget — it is
        # immune to the budget-fit truncation that governs facts/events (see
        # design.md section 4b, ADR-2).
        if session_id:
            checkpoint = self.memory.read_checkpoint(project, session_id)
            if checkpoint:
                messages.append({
                    "role": "system",
                    "content": render_checkpoint(checkpoint, cap=CHECKPOINT_REHYDRATION_CHAR_CAP),
                })

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

        sdd_keywords = ("spec", "design", "proposal", "tasks", "sdd", "specification", "architecture")
        if any(kw in user_input.lower() for kw in sdd_keywords):
            sdd_context = summarize_sdd_context()
            if sdd_context:
                messages.append({
                    "role": "system",
                    "content": f"SDD project context:\n{sdd_context}"
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
    ) -> ReasoningOutcome:
        """Execute reasoning loop with tool calls."""
        max_iterations = self.config.max_iterations
        temperature = self.config.temperature
        total_tool_calls = 0
        last_tools_used: list[str] = []

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
                return ReasoningOutcome(
                    response=response.content,
                    last_tool_summary=", ".join(last_tools_used[-3:]),
                    exhausted=False,
                )

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
                total_tool_calls += 1
                last_tools_used.append(f"{skill_name}.{fn_name}")

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
        return ReasoningOutcome(
            response=self._format_exhaustion_message(max_iterations, total_tool_calls, last_tools_used),
            last_tool_summary=", ".join(last_tools_used[-3:]),
            exhausted=True,
        )

    @staticmethod
    def _format_exhaustion_message(
        max_iterations: int,
        total_tool_calls: int,
        last_tools_used: list[str],
    ) -> str:
        """Build an honest, actionable message when the reasoning loop is exhausted."""
        recent = last_tools_used[-3:] if last_tools_used else []
        recent_str = ", ".join(recent) if recent else "ninguna"

        return (
            f"Se alcanzó el límite de {max_iterations} iteraciones sin llegar a una respuesta final "
            f"({total_tool_calls} llamadas a herramientas realizadas, últimas usadas: {recent_str}).\n"
            "No voy a reintentar automáticamente de otra forma. Podés: "
            "acotar el pedido, subir el límite de iteraciones (`agent.max_iterations` en config), "
            "o pedirme que continúe desde donde quedó."
        )

    async def stream_chat(
        self,
        user_input: str,
        project: str = "default",
        session_id: Optional[str] = None,
        status_callback: Optional[StatusCallback] = None,
    ) -> AsyncGenerator[str, None]:
        """Stream chat response (not fully implemented with tools yet)."""
        response = await self.chat(
            user_input,
            project,
            session_id,
            status_callback=status_callback,
        )
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
