"""Compact memory capsule formatting for coding agents."""

from __future__ import annotations

from pydantic import BaseModel, Field

from agentos.memory.models import EventType, MemoryContext, MemoryEvent, MemoryFact


DEFAULT_MAX_CHARS = 4000


class MemoryCapsule(BaseModel):
    """Bounded, source-tagged memory context for MCP responses."""

    project: str
    facts: list[MemoryFact] = Field(default_factory=list)
    decisions: list[MemoryEvent] = Field(default_factory=list)
    procedures: list[MemoryEvent] = Field(default_factory=list)
    recent: list[MemoryEvent] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    rendered: str = ""


def build_memory_capsule(
    project: str,
    context: MemoryContext,
    max_chars: int = DEFAULT_MAX_CHARS,
) -> MemoryCapsule:
    """Build a compact English capsule from repository context."""
    facts = context.facts
    decisions = [event for event in context.events if event.type == EventType.DECISION]
    procedures = [event for event in context.events if _event_kind(event) == "procedure"]
    recent = context.events

    sources = _collect_sources(facts, decisions, procedures, recent)
    rendered = _bound_text(_render(project, facts, decisions, procedures, recent, sources), max_chars)

    return MemoryCapsule(
        project=project,
        facts=facts,
        decisions=decisions,
        procedures=procedures,
        recent=recent,
        sources=sources,
        rendered=rendered,
    )


def _event_kind(event: MemoryEvent) -> str:
    if event.meta.get("kind") == "procedure":
        return "procedure"
    if event.type == EventType.DECISION:
        return "decision"
    return event.type.value


def _collect_sources(
    facts: list[MemoryFact],
    decisions: list[MemoryEvent],
    procedures: list[MemoryEvent],
    recent: list[MemoryEvent],
) -> list[str]:
    sources: list[str] = []
    for fact in facts:
        sources.append(f"fact:{fact.source_event_id or fact.id}")
    for event in [*decisions, *procedures, *recent]:
        source = f"event:{event.id}"
        if source not in sources:
            sources.append(source)
    return sources


def _render(
    project: str,
    facts: list[MemoryFact],
    decisions: list[MemoryEvent],
    procedures: list[MemoryEvent],
    recent: list[MemoryEvent],
    sources: list[str],
) -> str:
    parts = [f"# Memory capsule: {project}"]
    parts.extend(_render_facts(facts))
    parts.extend(_render_events("Decisions", decisions))
    parts.extend(_render_events("Procedures", procedures))
    parts.extend(_render_events("Recent", recent))
    if sources:
        parts.append("## Sources")
        parts.extend(f"- {source}" for source in sources)
    return "\n".join(parts)


def _render_facts(facts: list[MemoryFact]) -> list[str]:
    if not facts:
        return []
    lines = ["## Facts"]
    lines.extend(
        f"- [{fact.source_event_id or fact.id}] {fact.key}: {fact.value}"
        for fact in facts
    )
    return lines


def _render_events(title: str, events: list[MemoryEvent]) -> list[str]:
    if not events:
        return []
    lines = [f"## {title}"]
    lines.extend(f"- [{event.id}] {event.content}" for event in events)
    return lines


def _bound_text(text: str, max_chars: int) -> str:
    if max_chars <= 1:
        return "…"[:max_chars]
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "…"
