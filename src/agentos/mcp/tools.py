"""MCP memory tool handlers."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

from agentos.core.config import get_config
from agentos.mcp.project import detect_project
from agentos.memory.capsule import build_memory_capsule
from agentos.memory.models import EventType, MemoryEvent, MemoryFact
from agentos.memory.repository import MemoryRepository
from agentos.qwen.client import get_qwen_client
from agentos.qwen.extraction import MemoryCandidate, QwenMemoryExtractor

TOOL_NAMES = [
    "memory_context",
    "memory_search",
    "memory_save",
    "memory_extract",
    "memory_explain",
]

def list_tool_names() -> list[str]:
    return list(TOOL_NAMES)


class MemoryToolHandlers:
    """Directly callable handlers used by MCP registration and tests."""

    def __init__(self, repository: MemoryRepository | None = None, qwen_client: Any | None = None):
        self.repository = repository or MemoryRepository()
        self.qwen_client = qwen_client or get_qwen_client()

    async def memory_context(
        self,
        project: str | None = None,
        query: str | None = None,
        limit: int = 10,
    ) -> dict[str, Any]:
        resolved_project = detect_project(project)
        safe_limit = _safe_limit(limit)
        max_tokens = get_config().memory.max_context_tokens
        context = self.repository.assemble_context(
            query or "",
            project=resolved_project,
            max_tokens=max_tokens,
        )
        context.facts = context.facts[:safe_limit]
        context.events = context.events[:safe_limit]
        context.total_tokens = self.repository.estimate_context_tokens(context)
        capsule = build_memory_capsule(project=resolved_project, context=context)
        return _ok(resolved_project, capsule=capsule.model_dump(mode="json"))

    async def memory_search(
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

    async def memory_save(
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

    async def memory_extract(
        self,
        text: str,
        project: str | None = None,
        source: str | None = None,
    ) -> dict[str, Any]:
        resolved_project = detect_project(project)
        extractor = QwenMemoryExtractor(self.qwen_client)
        extraction = await extractor.extract(text)
        if not extraction.ok:
            return _error(resolved_project, *extraction.errors, items=[])

        items = [
            self._store_candidate(candidate, resolved_project, source or "mcp_extract")
            for candidate in extraction.candidates
        ]
        context = self.repository.assemble_context(
            "",
            project=resolved_project,
            max_tokens=get_config().memory.max_context_tokens,
        )
        capsule = build_memory_capsule(project=resolved_project, context=context)
        return _ok(resolved_project, items=items, capsule=capsule.model_dump(mode="json"))

    async def memory_explain(self, query: str, project: str | None = None) -> dict[str, Any]:
        resolved_project = detect_project(project)
        if not query.strip():
            return _error(resolved_project, "query is required", items=[])

        search_res = await self.memory_search(query=query, project=resolved_project, limit=10)
        items = search_res["items"]
        if not items:
            context = self.repository.assemble_context(
                "",
                project=resolved_project,
                max_tokens=get_config().memory.max_context_tokens,
            )
            items = [_fact_item(fact) for fact in context.facts] + [
                _event_item(event) for event in context.events
            ]
            items = items[:10]

        errors: list[str] = []
        explanations = _fallback_explanations(query, items)
        try:
            qwen_payload = await self.qwen_client.structured_json(
                _build_explanation_prompt(query, items),
                system_prompt=(
                    "Explain why each stored memory is relevant to the query. "
                    "Use only facts present in the provided memory items. Return JSON with "
                    "an explanations array in the same order as the items."
                ),
            )
            explanations = _safe_qwen_explanations(qwen_payload, items, explanations)
        except Exception as exc:
            errors.append(f"Qwen explanation failed: {exc}")

        explained_items = [
            {**item, "explanation": explanations[index]} for index, item in enumerate(items)
        ]
        return {"ok": True, "project": resolved_project, "errors": errors, "items": explained_items}

    def _store_candidate(
        self,
        candidate: MemoryCandidate,
        project: str,
        source: str,
    ) -> dict[str, Any]:
        if candidate.kind == "fact":
            fact = MemoryFact(
                key=candidate.title,
                value=candidate.content,
                scope=f"project:{project}",
                confidence=candidate.confidence,
            )
            return _fact_item(self.repository.upsert_fact(fact))

        event_type = EventType.DECISION if candidate.kind == "decision" else EventType.TASK
        event = MemoryEvent(
            type=event_type,
            project=project,
            content=candidate.content,
            meta={
                "kind": candidate.kind,
                "title": candidate.title,
                "confidence": candidate.confidence,
                "provenance": candidate.provenance,
            },
            source=source,
        )
        return _event_item(self.repository.add_event(event))


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


def _error(project: str, *messages: str, **payload: Any) -> dict[str, Any]:
    return {"ok": False, "project": project, "errors": list(messages), **payload}


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





def _build_explanation_prompt(query: str, items: list[dict[str, Any]]) -> str:
    return (
        f"Query: {query}\n\n"
        "Stored memory items:\n"
        f"{items}\n\n"
        "Return JSON: {\"explanations\": [{\"explanation\": \"...\"}]}"
    )


def _safe_qwen_explanations(
    payload: dict[str, Any],
    items: list[dict[str, Any]],
    fallback: list[str],
) -> list[str]:
    raw_explanations = payload.get("explanations", [])
    if not isinstance(raw_explanations, list):
        return fallback

    explanations = fallback.copy()
    for index, item in enumerate(items):
        if index >= len(raw_explanations) or not isinstance(raw_explanations[index], dict):
            continue
        explanation = str(raw_explanations[index].get("explanation", "")).strip()
        if explanation and _references_stored_content(explanation, item):
            explanations[index] = explanation
    return explanations


def _references_stored_content(explanation: str, item: dict[str, Any]) -> bool:
    stored_terms = _keywords(f"{item.get('title', '')} {item.get('summary', '')}")
    return bool(stored_terms & _keywords(explanation))


def _fallback_explanations(query: str, items: list[dict[str, Any]]) -> list[str]:
    query_terms = _keywords(query)
    explanations = []
    for item in items:
        item_terms = _keywords(str(item.get("summary", "")))
        overlap = sorted(query_terms & item_terms)
        if overlap:
            explanations.append(f"Matches query terms: {', '.join(overlap[:5])}")
        else:
            explanations.append("Included as stored project memory for this project.")
    return explanations


def _keywords(text: str) -> set[str]:
    normalized = "".join(char.lower() if char.isalnum() else " " for char in text)
    return {word for word in normalized.split() if len(word) >= 3}
