"""Agent core loop - the brain of Aki."""

from __future__ import annotations

import asyncio
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

# deferred config
VERSION_CONTROL_KEYWORDS = (
    # English
    "git", "git repo", "git repository", "version control", "repo status",
    "repository status", "initialize git", "init git",
    # Spanish
    "versionamiento", "control de versiones", "poné git", "pone git",
    "repositorio git", "estado del repo", "estado del repositorio",
    "inicializá git", "inicializa git", "revisar el estado del repo",
)

# deferred config
NEW_PRODUCT_KEYWORDS = (
    # English — whole-product / whole-app framing only
    "build me a new app", "build me an app", "build a new project",
    "start a new project", "create a whole new product", "whole new app",
    "the whole app built", "set up the entire project", "the entire project",
    "build the whole thing", "from scratch", "entire application",
    # Spanish — whole-product / whole-app framing only
    "toda la app", "toda la aplicación", "todo el proyecto",
    "proyecto nuevo", "nuevo desde cero", "desde cero",
    "arrancar desde cero", "poné en marcha el proyecto",
    "poner en marcha el proyecto", "tener el proyecto hecho",
    "necesitamos ya poder tener", "que esté hecho el proyecto",
    "armar toda la app",
)

StatusCallback = Callable[[str], None]


@dataclass
class ReasoningOutcome:
    """Result of `_reasoning_loop`: final response text plus checkpoint-relevant metadata."""

    response: str
    last_tool_summary: str
    exhausted: bool


def _is_new_product_request(message: str) -> bool:
    """True when the message frames a whole-new-product/app ask.

    Pure over `message` — coarse bilingual phrase match, independent of
    SCAFFOLDING_KEYWORDS. No history, no I/O.
    """
    lowered = message.lower()
    return any(kw in lowered for kw in NEW_PRODUCT_KEYWORDS)


def _build_new_product_suggestion(has_sdd: bool) -> str:
    """Compose the SDD-scoping suggestion; branch on detect_sdd_artifacts()."""
    if has_sdd:
        return (
            "Esto parece el arranque de un proyecto/app completo. Ya hay artefactos "
            "SDD en este proyecto, así que antes de tirar comandos sueltos conviene "
            "retomar el flujo SDD en curso (continuar la propuesta/spec/tareas "
            "existentes) para no perder el hilo del plan. "
            "Si preferís que lo haga directo igual, decímelo en el próximo mensaje "
            "y sigo sin SDD."
        )
    return (
        "Esto parece el arranque de un proyecto/app completo. Todavía no hay "
        "artefactos SDD en este proyecto; en vez de crear archivos a ciegas conviene "
        "arrancar un flujo SDD con `sdd-init` para acotar el alcance y planificar "
        "antes de escribir código. "
        "Si preferís que lo haga directo igual, decímelo en el próximo mensaje "
        "y sigo sin SDD."
    )


def _notify_status(status_callback: Optional[StatusCallback], message: str) -> None:
    if status_callback is not None:
        status_callback(message)


def _format_thinking_status(iteration: int, max_iterations: int) -> str:
    return f"🧠 Thinking — iteration {iteration}/{max_iterations}"


def _format_tool_status(ordinal: int, total: int, safe_tool_name: str) -> str:
    return f"🔧 Running {safe_tool_name} ({ordinal}/{total})"


def _format_context_status() -> str:
    return "📚 Collecting project context"


def _format_saving_status() -> str:
    return "💾 Saving conversation"


def _format_terminal_status(exhausted: bool) -> str:
    return "⏳ Turn exhausted" if exhausted else "✅ Turn complete"


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


def _split_tool_name(tool_name: str, registry: SkillRegistry) -> tuple[str, str]:
    skill_names: list[str] = []
    try:
        skill_names = [skill.name for skill in registry.list(enabled_only=False)]
    except Exception:
        skill_names = []
    if not skill_names:
        skill_names = list(BUILTIN_SKILLS.keys())

    for skill_name in sorted(skill_names, key=len, reverse=True):
        prefix = f"{skill_name}_"
        if tool_name.startswith(prefix):
            return skill_name, tool_name[len(prefix):]
    if "_" in tool_name:
        prefix, remainder = tool_name.split("_", 1)
        return prefix, remainder
    return "unknown", tool_name


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

    def _should_suggest_sdd_flow(
        self,
        user_input: str,
        profile: Optional[AgentProfile],
        project: str,
        session_id: str,
    ) -> bool:
        """All three gate conditions for the request-level SDD suggestion.

        Fires only when: memory is not disabled, this is the first turn
        (no checkpoint), and the input reads like a whole-new-product ask.
        Order is cheapest-and-most-suppressive first.
        """
        if profile is not None and profile.memory.scope == "disabled":
            return False
        if not _is_new_product_request(user_input):
            return False
        return self.memory.read_checkpoint(project, session_id) is None

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
        _notify_status(status_callback, _format_context_status())
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

        # 5. Reasoning loop (or request-level SDD short-circuit)
        if self._should_suggest_sdd_flow(user_input, profile, project, session_id):
            sdd_status = detect_sdd_artifacts()
            outcome = ReasoningOutcome(
                response=_build_new_product_suggestion(sdd_status.has_sdd),
                last_tool_summary="",
                exhausted=False,
            )
        else:
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
        _notify_status(status_callback, _format_saving_status())
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

        _notify_status(status_callback, _format_terminal_status(outcome.exhausted))
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

        if any(kw in user_input.lower() for kw in VERSION_CONTROL_KEYWORDS):
            messages.append({
                "role": "system",
                "content": (
                    "El pedido parece de versionado/repositorio. Primero inspeccioná el estado real "
                    "con `git_ops.status`. Si la carpeta no es un repo y el usuario quiere activar "
                    "git/versionamiento, preferí `git_ops.init` para inicializarlo de forma segura. "
                    "No uses `filesystem.write`/`append`/`delete` para fabricar `.git` ni para tocar "
                    "rutas internas del repositorio."
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
        depth: int = 0,
    ) -> ReasoningOutcome:
        """Execute reasoning loop with tool calls.

        `depth` is threaded through nested/recursive invocations: 0 for the
        supervisor's own loop, 1 for a worker loop spawned by delegation. The
        synthetic `delegate` tool schema is only exposed to the model when
        `depth == 0` (see `_build_delegate_tool_schema`), which is the sole
        structural guard against a worker delegating further.
        """
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
        if depth == 0:
            tools = [*tools, self._build_delegate_tool_schema()]
        total_tool_calls = 0
        last_tools_used: list[str] = []

        for iteration in range(max_iterations):
            current_iteration = iteration + 1
            _notify_status(
                status_callback,
                _format_thinking_status(current_iteration, max_iterations),
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

                if depth == 0 and fn_name == "delegate":
                    delegate_msg = await self._run_delegation(
                        fn_args, project, session_id, tool_call_id, status_callback
                    )
                    messages.append(delegate_msg)
                    continue

                # Parse skill_name.function_name
                skill_name, fn_name = _split_tool_name(fn_name, self.skills)

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

    async def _run_delegation(
        self,
        fn_args: dict[str, Any],
        project: str,
        session_id: str,
        tool_call_id: str,
        status_callback: Optional[StatusCallback],
    ) -> dict[str, Any]:
        """Resolve, run, and adapt a single worker delegation call.

        Returns the tool-result message to append to the supervisor's
        `messages`. Unknown `profile_id` is adapted into an error tool-result
        message rather than propagating `ProfileNotFoundError` -- the
        supervisor stays in control of recovery (see Resolved Open Decisions,
        openspec/changes/multi-agent-orchestration/tasks.md).
        """
        profile_id = fn_args.get("profile_id")
        try:
            worker_profile = self.agent_registry.resolve(profile_id)
        except Exception:
            return {
                "role": "tool",
                "tool_call_id": tool_call_id,
                "content": f"delegate error: unknown profile '{profile_id}'",
            }

        task = fn_args.get("task", "")
        worker_sid = self._derive_worker_session_id(session_id, tool_call_id)

        worker_context = self.memory.assemble_context(
            query=task,
            project=project,
            session_id=worker_sid,
            max_tokens=get_config().memory.max_context_tokens,
        )
        worker_context = _filter_context_for_profile(worker_context, worker_profile, worker_sid)

        worker_messages = self._build_messages(
            task, worker_context, project, session_id=worker_sid, profile=worker_profile
        )
        worker_tools = _filter_tools_for_profile(self.skills.get_all_tools(), worker_profile)

        outcome = await self._reasoning_loop(
            worker_messages,
            worker_tools,
            project,
            worker_sid,
            status_callback=status_callback,
            profile=worker_profile,
            depth=1,
        )

        return {
            "role": "tool",
            "tool_call_id": tool_call_id,
            "content": self._adapt_worker_outcome(outcome),
        }

    @staticmethod
    def _build_delegate_tool_schema() -> dict[str, Any]:
        """OpenAI-style function schema for the synthetic `delegate` tool.

        Appended to the tools list only when `depth == 0` (see
        `_reasoning_loop`); never present in a worker's own tools list.
        """
        return {
            "type": "function",
            "function": {
                "name": "delegate",
                "description": (
                    "Delegate a task to a specialized worker agent profile. "
                    "The worker runs its own bounded reasoning loop and "
                    "returns its result as this tool's result."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "profile_id": {
                            "type": "string",
                            "description": "AgentRegistry-resolvable id of the worker profile.",
                        },
                        "task": {
                            "type": "string",
                            "description": "Free-form task description, handed to the worker as its initial user message.",
                        },
                    },
                    "required": ["profile_id", "task"],
                },
            },
        }

    @staticmethod
    def _derive_worker_session_id(parent_session_id: str, tool_call_id: str) -> str:
        """Deterministically derive a worker session id from the parent
        session id and the delegating tool-call id. Reproducible for a given
        (parent_session_id, tool_call_id) pair; distinct per tool_call_id."""
        return f"{parent_session_id}:delegate:{tool_call_id}"

    @staticmethod
    def _adapt_worker_outcome(outcome: ReasoningOutcome) -> str:
        """Adapt a worker's ReasoningOutcome into tool-result content.

        Success -> outcome.response verbatim (no last_tool_summary folded
        in -- see openspec/changes/multi-agent-orchestration Resolved Open
        Decisions). Exhausted -> a clearly-marked "did not finish" wrapper
        so the supervisor's model does not mistake it for a completed answer.
        """
        if outcome.exhausted:
            return (
                "Worker did not finish within its iteration budget "
                f"(exhausted=True). Last worker output: {outcome.response}"
            )
        return outcome.response

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
        event = MemoryEvent(
            type=type,
            project=project,
            content=content,
            meta=meta or {},
            source="user",
        )
        return await asyncio.to_thread(self.memory.add_event, event)

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
