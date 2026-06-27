"""MCP memory tool handlers."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from agentos.mcp.project import detect_project
from agentos.memory.capsule import build_memory_capsule
from agentos.memory.models import EventType, MemoryEvent, MemoryFact
from agentos.memory.repository import MemoryRepository

TOOL_NAMES = [
    "memory_context",
    "memory_search",
    "memory_save",
    "memory_extract",
    "memory_explain",
]

QWEN_NOT_IMPLEMENTED = "Qwen extraction not yet implemented"


def list_tool_names() -> list[str]:
    return list(TOOL_NAMES)


class MemoryToolHandlers:
    """Directly callable handlers used by MCP registration and tests."""

    def __init__(self, repository: MemoryRepository | None = None):
        self.repository = repository or MemoryRepository()

    def memory_context(
        self,
        project: str | None = None,
        query: str | None = None,
        limit: int = 10,
    ) -> dict[str, Any]:
        resolved_project = detect_project(project)
        safe_limit = _safe_limit(limit)
        context = self.repository.assemble_context(
            query or "",
            project=resolved_project,
            max_tokens=safe_limit,
        )
        context.facts = context.facts[:safe_limit]
        context.events = context.events[:safe_limit]
        capsule = build_memory_capsule(project=resolved_project, context=context)
        return _ok(resolved_project, capsule=capsule.model_dump(mode="json"))

    def memory_search(
        self,
        query: str,
        project: str | None = None,
        limit: int = 10,
    ) -> dict[str, Any]:
        resolved_project = detect_project(project)
        if not query.strip():
            return _error(resolved_project, "query is required", items=[])

        safe_limit = _safe_limit(limit)
        facts = self.repository.search_facts(
            query,
            scope=f"project:{resolved_project}",
            limit=safe_limit,
        )
        events = self.repository.search_events(
            query,
            project=resolved_project,
            limit=safe_limit,
            min_score=0.0,
        )
        items = [_fact_item(fact) for fact in facts] + [_event_item(event) for event in events]
        return _ok(resolved_project, items=items[:safe_limit])

    def memory_save(
        self,
        kind: str,
        title: str,
        content: str,
        project: str | None = None,
        confidence: float | None = None,
    ) -> dict[str, Any]:
        resolved_project = detect_project(project)
        normalized_kind = kind.strip().lower()
        if normalized_kind not in {"fact", "decision", "procedure"}:
            return _error(
                resolved_project,
                "Unsupported memory kind. Expected one of: fact, decision, procedure",
            )
        if not title.strip() or not content.strip():
            return _error(resolved_project, "title and content are required")

        if normalized_kind == "fact":
            fact = MemoryFact(
                key=title.strip(),
                value=content.strip(),
                scope=f"project:{resolved_project}",
                confidence=confidence if confidence is not None else 1.0,
            )
            stored = self.repository.upsert_fact(fact)
            return _ok(resolved_project, memory=_fact_item(stored))

        event_type = EventType.DECISION if normalized_kind == "decision" else EventType.TASK
        event = MemoryEvent(
            type=event_type,
            project=resolved_project,
            content=content.strip(),
            meta={"kind": normalized_kind, "title": title.strip(), "confidence": confidence or 1.0},
            source="mcp",
        )
        stored_event = self.repository.add_event(event)
        return _ok(resolved_project, memory=_event_item(stored_event))

    def memory_extract(
        self,
        text: str,
        project: str | None = None,
        source: str | None = None,
    ) -> dict[str, Any]:
        return _error(detect_project(project), QWEN_NOT_IMPLEMENTED, items=[])

    def memory_explain(self, query: str, project: str | None = None) -> dict[str, Any]:
        return _error(detect_project(project), QWEN_NOT_IMPLEMENTED, items=[])


def tool_callables(handlers: MemoryToolHandlers) -> dict[str, Callable[..., dict[str, Any]]]:
    return {
        "memory_context": handlers.memory_context,
        "memory_search": handlers.memory_search,
        "memory_save": handlers.memory_save,
        "memory_extract": handlers.memory_extract,
        "memory_explain": handlers.memory_explain,
    }


def _safe_limit(limit: int) -> int:
    return max(1, min(limit, 50))


def _ok(project: str, **payload: Any) -> dict[str, Any]:
    return {"ok": True, "project": project, "errors": [], **payload}


def _error(project: str, message: str, **payload: Any) -> dict[str, Any]:
    return {"ok": False, "project": project, "errors": [message], **payload}


def _fact_item(fact: MemoryFact) -> dict[str, Any]:
    return {
        "id": fact.id,
        "title": fact.key,
        "kind": "fact",
        "summary": fact.value,
        "project": fact.scope.removeprefix("project:"),
        "confidence": fact.confidence,
        "source": fact.source_event_id,
    }


def _event_item(event: MemoryEvent) -> dict[str, Any]:
    kind = event.meta.get("kind")
    if not kind:
        kind = "decision" if event.type == EventType.DECISION else event.type.value
    return {
        "id": event.id,
        "title": event.meta.get("title", event.content[:80]),
        "kind": kind,
        "summary": event.content,
        "project": event.project,
        "confidence": event.meta.get("confidence", 1.0),
        "source": event.source,
    }
