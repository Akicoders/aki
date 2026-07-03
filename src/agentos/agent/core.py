"""Agent core loop - the brain of Aki."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, AsyncGenerator, Callable, Optional

from agentos.agents import AgentProfile, AgentRegistry
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

# deferred config
GENERIC_CONTENT_PLACEHOLDERS: frozenset[str] = frozenset({
    "todo", "tbd", "fixme", "...", "…",
    "placeholder", "content", "contenido",
    "content here", "contenido aqui", "your content here",
    "tu contenido aqui",
})

# deferred config
SCAFFOLDING_KEYWORDS = (
    # English
    "create", "generate", "set up", "setup", "scaffold", "bootstrap",
    "new project", "new component", "new file", "new module", "boilerplate",
    "start a project", "initialize",
    # Spanish
    "crear", "creá", "crea", "generar", "generá", "genera", "armar",
    "armá", "arma", "estructura", "andamiaje", "nuevo proyecto",
    "nuevo componente", "nuevo archivo", "inicializar", "montar",
)

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


def _format_iteration_status(iteration: int, max_iterations: int) -> str:
    return f"Reasoning iteration {iteration}/{max_iterations}"


def _format_final_iteration_status(iteration: int, max_iterations: int) -> str:
    return f"Final iteration {iteration}/{max_iterations}; no automatic retry remains"


def _format_tool_status(ordinal: int, total: int, safe_tool_name: str) -> str:
    return f"Running tool {ordinal}/{total}: {safe_tool_name}"


def _is_under_specified(fn_name: str, fn_args: dict[str, Any]) -> bool:
    """True when a destructive call's args are too vague to execute safely.
    Pure over fn_args -- no history, no turn count (spec: the 'simple' heuristic)."""
    path = fn_args.get("path")
    if path is None or not str(path).strip():
        return True
    if fn_name in ("write", "append"):
        content = fn_args.get("content")
        if content is None or not str(content).strip():
            return True
        if str(content).strip().lower() in GENERIC_CONTENT_PLACEHOLDERS:
            return True
    return False  # delete: path presence is sufficient specificity


def _build_clarifying_question(skill_name: str, fn_name: str, fn_args: dict[str, Any]) -> str:
    path = fn_args.get("path")
    if path is None or not str(path).strip():
        return (
            "Antes de escribir necesito el destino exacto. "
            "¿En qué ruta (path) querés que cree/modifique el archivo, "
            "y con qué stack/estructura?"
        )
    return (
        f"Voy a escribir en `{path}` pero el contenido está vacío o es un "
        "placeholder genérico. ¿Qué contenido concreto querés que ponga?"
    )


def _profile_event_meta(role: str, profile: AgentProfile | None) -> dict[str, str]:
    """Build event metadata without changing default no-profile payloads."""
    meta = {"role": role}
    if profile is not None:
        meta["active_profile_id"] = profile.id
    return meta


def _openai_tool_name_to_policy_name(tool_name: str) -> str:
    """Normalize OpenAI function names to profile policy names."""
    return tool_name.replace("_", ".", 1)


def _tool_is_allowed(profile: AgentProfile | None, skill_name: str, fn_name: str) -> bool:
    if profile is None:
        return True
    return profile.tools.allows(f"{skill_name}.{fn_name}")


def _filter_tools_for_profile(
    tools: list[dict[str, Any]],
    profile: AgentProfile | None,
) -> list[dict[str, Any]]:
    """Filter advertised tool schemas; runtime validation still enforces safety."""
    if profile is None:
        return tools
    return [
        tool
        for tool in tools
        if profile.tools.allows(_openai_tool_name_to_policy_name(tool["function"]["name"]))
    ]


def _filter_context_for_profile(
    context: MemoryContext,
    profile: AgentProfile | None,
    session_id: str,
) -> MemoryContext:
    """Apply profile memory visibility without changing repository storage."""
    if profile is None or profile.memory.scope in {"project", "global"}:
        return context
    if profile.memory.scope == "session":
        return MemoryContext(
            facts=[],
            events=[event for event in context.events if event.session_id == session_id],
            skills=context.skills,
            total_tokens=0,
        )
    return MemoryContext(skills=context.skills)


def _tool_policy_denial(tool_name: str) -> str:
    return f"Tool `{tool_name}` is not allowed by the selected agent profile."


class AgentOS:
    """Main agent orchestration class."""

    def __init__(
        self,
        config: Optional[AgentConfig] = None,
        qwen_client: Optional[QwenClient] = None,
        memory: Optional[MemoryRepository] = None,
        skill_registry: Optional[SkillRegistry] = None,
        agent_registry: Optional[AgentRegistry] = None,
    ):
        self.config = config or get_config().agent
        self.qwen = qwen_client or get_qwen_client()
        self.memory = memory or MemoryRepository()
        self.skills = skill_registry or get_skill_registry()
        self.agent_registry = agent_registry or AgentRegistry.from_config(
            get_config().agent_profiles
        )
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
        profile_id: Optional[str] = None,
    ) -> str:
        """Main chat entry point."""
        if not session_id:
            session_id = f"sess_{uuid.uuid4().hex[:8]}"

        profile = self.agent_registry.resolve(profile_id) if profile_id else None
        _notify_status(status_callback, "Starting turn")

        # 1. Store user input as event
        if profile is None or profile.memory.scope != "disabled":
            create_event(
                type=EventType.CONVERSATION,
                project=project,
                content=user_input,
                meta=_profile_event_meta("user", profile),
                source="user",
                session_id=session_id,
            )
        logger.info(f"User [{session_id}]: {user_input[:100]}")

        # 2. Assemble context from memory
        _notify_status(status_callback, "Collecting project context")
        if profile is not None and profile.memory.scope == "disabled":
            context = MemoryContext()
        else:
            context = self.memory.assemble_context(
                query=user_input,
                project=project,
                session_id=session_id,
                max_tokens=get_config().memory.max_context_tokens,
            )
            context = _filter_context_for_profile(context, profile, session_id)

        # 3. Build messages for LLM
        messages: list[dict[str, Any]] = self._build_messages(
            user_input, context, project, session_id=session_id, profile=profile
        )

        # 4. Get available tools
        tools: list[dict[str, Any]] = _filter_tools_for_profile(
            self.skills.get_all_tools(), profile
        )

        # 5. Reasoning loop
        outcome = await self._reasoning_loop(
            messages,
            tools,
            project,
            session_id,
            status_callback=status_callback,
            profile=profile,
        )
        response = outcome.response

        # 6. Store agent response
        _notify_status(status_callback, "Saving conversation")
        if profile is None or profile.memory.scope != "disabled":
            create_event(
                type=EventType.CONVERSATION,
                project=project,
                content=response,
                meta=_profile_event_meta("assistant", profile),
                source="agent",
                session_id=session_id,
            )

        # 6b. Persist structured checkpoint (mutable current-state), every turn
        # (success or iteration-exhaustion), see design.md section 4a.
        if profile is None or profile.memory.scope != "disabled":
            checkpoint_kwargs: dict[str, Any] = {}
            if profile is not None:
                checkpoint_kwargs["active_profile_id"] = profile.id
            self.memory.write_checkpoint(
                project=project,
                session_id=session_id,
                goal=user_input,
                last_response=response,
                last_tool_result=outcome.last_tool_summary,
                iterations_exhausted=outcome.exhausted,
                **checkpoint_kwargs,
            )

        _notify_status(status_callback, "Turn exhausted" if outcome.exhausted else "Turn complete")
        logger.info(f"Agent [{session_id}]: {response[:100]}")
        return response

    def _build_messages(
        self,
        user_input: str,
        context: MemoryContext,
        project: str,
        session_id: Optional[str] = None,
        profile: Optional[AgentProfile] = None,
    ) -> list[dict[str, Any]]:
        """Build message history for LLM."""
        system_prompt = (
            profile.prompt_template
            if profile
            else self.config.system_prompt_template
            or (
                "You are Aki, an AI agent with persistent project memory for coding workflows. "
                "Help developers preserve durable facts, decisions, and procedures across sessions. "
                "Be concise, practical, and careful with context budgets."
            )
        )

        messages = [
            {"role": "system", "content": system_prompt},
        ]

        # Reserved checkpoint slot: injected BEFORE the memory-context message,
        # read by exact (project, session_id) key, and deliberately NOT routed
        # through context.format_for_prompt / _fit_context_to_budget — it is
        # immune to the budget-fit truncation that governs facts/events (see
        # design.md section 4b, ADR-2).
        if session_id and (profile is None or profile.memory.scope != "disabled"):
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

        if any(kw in user_input.lower() for kw in SCAFFOLDING_KEYWORDS):
            messages.append({
                "role": "system",
                "content": (
                    "El pedido parece de scaffolding/creación de estructura. "
                    "Antes de llamar a cualquier herramienta destructiva "
                    "(filesystem.write / append / delete), verificá que tengas los "
                    "detalles estructurales clave: ruta destino, framework/stack, "
                    "convención de nombres y layout de archivos. Si falta alguno, "
                    "hacé UNA pregunta aclaratoria concreta en tu respuesta en lugar "
                    "de crear archivos a ciegas."
                ),
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
        status_callback: Optional[StatusCallback] = None,
        profile: Optional[AgentProfile] = None,
    ) -> ReasoningOutcome:
        """Execute reasoning loop with tool calls."""
        max_iterations = (
            profile.max_iterations
            if profile and profile.max_iterations is not None
            else self.config.max_iterations
        )
        temperature = (
            profile.temperature
            if profile and profile.temperature is not None
            else self.config.temperature
        )
        total_tool_calls = 0
        last_tools_used: list[str] = []

        for iteration in range(max_iterations):
            current_iteration = iteration + 1
            _notify_status(
                status_callback,
                _format_iteration_status(current_iteration, max_iterations),
            )
            if current_iteration == max_iterations:
                _notify_status(
                    status_callback,
                    _format_final_iteration_status(current_iteration, max_iterations),
                )
            logger.debug(f"Reasoning iteration {current_iteration}/{max_iterations}")

            response: ChatResponse = await self.qwen.chat(
                messages=messages,
                tools=tools,
                tool_choice="auto",
                temperature=temperature,
                **({"model": profile.model} if profile and profile.model else {}),
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
            total_tools_in_response = len(response.tool_calls)
            for tool_ordinal, tool_call in enumerate(response.tool_calls, start=1):
                fn_name = tool_call["function"]["name"]
                fn_args = tool_call["function"]["arguments"]
                tool_call_id = tool_call["id"]

                # Parse skill_name.function_name
                if "_" in fn_name:
                    skill_name, fn_name = fn_name.split("_", 1)
                else:
                    skill_name, fn_name = "unknown", fn_name

                logger.info(f"Tool call: {skill_name}.{fn_name}({fn_args})")

                safe_tool_name = f"{skill_name}.{fn_name}"

                if not _tool_is_allowed(profile, skill_name, fn_name):
                    logger.info("Profile tool policy denied: %s", safe_tool_name)
                    return ReasoningOutcome(
                        response=_tool_policy_denial(safe_tool_name),
                        last_tool_summary=", ".join(last_tools_used[-3:]),
                        exhausted=False,
                    )

                if self.skills.is_destructive(skill_name, fn_name) and _is_under_specified(
                    fn_name, fn_args
                ):
                    logger.info(f"Destructive gate fired: {skill_name}.{fn_name} under-specified")
                    return ReasoningOutcome(
                        response=_build_clarifying_question(skill_name, fn_name, fn_args),
                        last_tool_summary=", ".join(last_tools_used[-3:]),
                        exhausted=False,
                    )

                total_tool_calls += 1
                last_tools_used.append(safe_tool_name)
                _notify_status(
                    status_callback,
                    _format_tool_status(tool_ordinal, total_tools_in_response, safe_tool_name),
                )

                result: SkillResult = await self.skills.execute(skill_name, fn_name, fn_args)

                # Store tool result
                tool_result_msg = {
                    "role": "tool",
                    "tool_call_id": tool_call_id,
                    "content": result.model_dump_json() if hasattr(result, 'model_dump_json') else str(result),
                }
                messages.append(tool_result_msg)

                if profile is None or profile.memory.scope != "disabled":
                    meta: dict[str, Any] = {
                        "tool": f"{skill_name}.{fn_name}",
                        "args": fn_args,
                        "success": result.success,
                        "error": result.error,
                    }
                    if profile is not None:
                        meta["active_profile_id"] = profile.id

                    # Log tool execution
                    create_event(
                        type=EventType.CONVERSATION,
                        project=project,
                        content=f"Tool: {skill_name}.{fn_name} -> {'ok' if result.success else 'error'}",
                        meta=meta,
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
        last_attempted = f"tool {recent[-1]}" if recent else "reasoning iteration"
        recent_str = ", ".join(recent) if recent else "none"

        return (
            f"The turn reached the {max_iterations}-iteration budget. "
            "No final answer was produced. "
            f"Last attempted: {last_attempted}. "
            f"Tool calls completed: {total_tool_calls}; recent safe tool names: {recent_str}.\n"
            "Try simplifying the request, clarifying the target outcome, "
            "or continuing from the last checkpoint."
        )

    async def stream_chat(
        self,
        user_input: str,
        project: str = "default",
        session_id: Optional[str] = None,
        status_callback: Optional[StatusCallback] = None,
        profile_id: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        """Stream chat response (not fully implemented with tools yet)."""
        response = await self.chat(
            user_input,
            project,
            session_id,
            status_callback=status_callback,
            profile_id=profile_id,
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
