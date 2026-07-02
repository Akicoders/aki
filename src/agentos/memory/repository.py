"""Memory repository - data access layer."""

import io
import json
import logging
import os
import warnings
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Optional, Protocol

import chromadb
from chromadb.config import Settings as ChromaSettings
from sqlalchemy import and_, func, or_, select

from .database import get_database
from .models import (
    EventType,
    MemoryContext,
    MemoryEvent,
    MemoryEventModel,
    MemoryFact,
    MemoryFactModel,
    Skill,
    SkillModel,
)


_MODEL_LOGGERS = ("huggingface_hub", "sentence_transformers", "transformers")

# --- Deferred config (see follow-up: wire into AgentConfig/MemoryConfig) ---
CHECKPOINT_FIELD_CHAR_CAP = 1000        # per free-text field cap before serialize
CHECKPOINT_REHYDRATION_CHAR_CAP = 2000  # hard cap on rendered rehydration slot
RESERVED_FACT_KEY_PREFIX = "session:"   # reserved-key namespace guard
LAST_SESSION_KEY = "session:last"
CHECKPOINT_KEY_TEMPLATE = RESERVED_FACT_KEY_PREFIX + "{session_id}:checkpoint"


def render_checkpoint(checkpoint: dict, cap: int) -> str:
    """Deterministic, bounded, human/model-readable rendering of a checkpoint dict.

    Plain function, no class state, hard-capped to `cap` chars so it can be
    injected into a reserved system-message slot without unbounded growth.
    Truncation is deterministic: same input always yields the same output.
    """
    goal = checkpoint.get("goal") or ""
    open_items = checkpoint.get("open_items") or []
    last_tool_result = checkpoint.get("last_tool_result") or ""

    lines = ["Checkpoint (previous session state):", f"- Goal: {goal}"]

    if open_items:
        lines.append("- Open items:")
        lines.extend(f"  - {item}" for item in open_items)
    else:
        lines.append("- Open items: none")

    if last_tool_result:
        lines.append(f"- Last tool result: {last_tool_result}")

    if checkpoint.get("iterations_exhausted"):
        lines.append("- Note: previous turn hit the iteration limit before finishing.")

    rendered = "\n".join(lines)
    return rendered[:cap]


class Embedder(Protocol):
    """Text embedding provider used by the memory repository."""

    def embed(self, text: str) -> list[float]:
        """Return a normalized embedding for text."""


class SentenceTransformerEmbedder:
    """SentenceTransformer adapter that satisfies the Embedder protocol."""

    def __init__(self, model_name: str):
        self.model = _get_sentence_transformer(model_name)

    def embed(self, text: str) -> list[float]:
        return self.model.encode(text, normalize_embeddings=True).tolist()


def _create_sentence_transformer(model_name: str):
    os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

    captured_output = io.StringIO()
    logger_levels = {name: logging.getLogger(name).level for name in _MODEL_LOGGERS}

    try:
        for logger_name in _MODEL_LOGGERS:
            logging.getLogger(logger_name).setLevel(logging.ERROR)

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            with redirect_stdout(captured_output), redirect_stderr(captured_output):
                from sentence_transformers import SentenceTransformer

                return SentenceTransformer(model_name)
    finally:
        for logger_name, level in logger_levels.items():
            logging.getLogger(logger_name).setLevel(level)


@lru_cache(maxsize=None)
def _get_sentence_transformer(model_name: str):
    return _create_sentence_transformer(model_name)


def reset_embedder_cache() -> None:
    _get_sentence_transformer.cache_clear()


class MemoryRepository:
    """Unified access to episodic, semantic, and procedural memory."""

    def __init__(
        self,
        db_path: Optional[Path] = None,
        chroma_path: Optional[Path] = None,
        embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2",
        embedder: Optional[Embedder] = None,
    ):
        self.db = get_database(db_path)
        self.chroma_path = chroma_path or (db_path.parent / "chroma_db" if db_path else Path("data/chroma_db"))
        self.chroma_path.mkdir(parents=True, exist_ok=True)

        self.chroma = chromadb.PersistentClient(
            path=str(self.chroma_path),
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        self.collection = self.chroma.get_or_create_collection(
            name="memory_events",
            metadata={"hnsw:space": "cosine"},
        )

        self.embedder = embedder or SentenceTransformerEmbedder(embedding_model)

    # --- Embeddings ---

    def _embed(self, text: str) -> list[float]:
        return self.embedder.embed(text)

    # --- Episodic Memory (Events) ---

    def add_event(self, event: MemoryEvent) -> MemoryEvent:
        """Store an event with embedding."""
        if event.embedding is None:
            event.embedding = self._embed(event.content)

        with self.db.session() as session:
            session.add(event.to_model())

        # Also store in ChromaDB for vector search
        self.collection.add(
            ids=[event.id],
            embeddings=[event.embedding],
            documents=[event.content],
            metadatas=[{
                "type": event.type.value,
                "project": event.project,
                "source": event.source,
                "timestamp": event.timestamp.isoformat(),
                "session_id": event.session_id or "",
            }],
        )

        return event

    def get_event(self, event_id: str) -> Optional[MemoryEvent]:
        with self.db.session() as session:
            model = session.get(MemoryEventModel, event_id)
            return MemoryEvent.from_model(model) if model else None

    def search_events(
        self,
        query: str,
        project: Optional[str] = None,
        event_types: Optional[list[EventType]] = None,
        limit: int = 10,
        min_score: float = 0.3,
    ) -> list[MemoryEvent]:
        """Hybrid search: vector + keyword + filters."""
        if not query.strip():
            with self.db.session() as session:
                stmt = select(MemoryEventModel)
                if project:
                    stmt = stmt.where(MemoryEventModel.project == project)
                if event_types:
                    stmt = stmt.where(MemoryEventModel.type.in_(event_types))
                stmt = stmt.order_by(MemoryEventModel.timestamp.desc()).limit(limit)
                models = session.execute(stmt).scalars().all()
            return [MemoryEvent.from_model(m) for m in models]

        query_embedding = self._embed(query)

        # Vector search in ChromaDB
        where = {}
        if project:
            where["project"] = project
        if event_types:
            where["type"] = {"$in": [t.value for t in event_types]}

        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=limit * 3,  # Get more for reranking
            where=where or None,
        )

        event_ids = results["ids"][0] if results["ids"] else []
        if not event_ids:
            return []

        # Fetch from SQL with scores
        distances = results["distances"][0] if results["distances"] else []
        id_to_score = dict(zip(event_ids, distances))

        with self.db.session() as session:
            stmt = select(MemoryEventModel).where(MemoryEventModel.id.in_(event_ids))
            if project:
                stmt = stmt.where(MemoryEventModel.project == project)
            if event_types:
                stmt = stmt.where(MemoryEventModel.type.in_(event_types))
            models = session.execute(stmt).scalars().all()

        # Sort by score (lower distance = higher similarity)
        events = [MemoryEvent.from_model(m) for m in models]
        events.sort(key=lambda e: id_to_score.get(e.id, 1.0))
        return [e for e in events if id_to_score.get(e.id, 1.0) <= (1.0 - min_score)][:limit]

    def get_recent_events(
        self,
        project: Optional[str] = None,
        limit: int = 20,
        hours: int = 24,
    ) -> list[MemoryEvent]:
        cutoff = datetime.utcnow() - timedelta(hours=hours)
        with self.db.session() as session:
            stmt = select(MemoryEventModel).where(MemoryEventModel.timestamp >= cutoff)
            if project:
                stmt = stmt.where(MemoryEventModel.project == project)
            stmt = stmt.order_by(MemoryEventModel.timestamp.desc()).limit(limit)
            models = session.execute(stmt).scalars().all()
        return [MemoryEvent.from_model(m) for m in models]

    # --- Semantic Memory (Facts) ---

    def upsert_fact(self, fact: MemoryFact) -> MemoryFact:
        """Insert or update a fact."""
        with self.db.session() as session:
            existing = session.get(MemoryFactModel, fact.id)
            if existing:
                existing.value = fact.value
                existing.confidence = fact.confidence
                existing.updated_at = datetime.utcnow()
                existing.access_count = fact.access_count
                existing.last_accessed = fact.last_accessed
            else:
                session.add(fact.to_model())
        return fact

    def get_fact(self, key: str, scope: str) -> Optional[MemoryFact]:
        with self.db.session() as session:
            stmt = select(MemoryFactModel).where(
                and_(MemoryFactModel.key == key, MemoryFactModel.scope == scope)
            )
            model = session.execute(stmt).scalar_one_or_none()
            return MemoryFact.from_model(model) if model else None

    def get_facts_by_scope(self, scope: str, limit: int = 100) -> list[MemoryFact]:
        with self.db.session() as session:
            stmt = select(MemoryFactModel).where(MemoryFactModel.scope == scope).limit(limit)
            models = session.execute(stmt).scalars().all()
        return [MemoryFact.from_model(m) for m in models]

    def search_facts(
        self,
        query: str,
        scope: Optional[str] = None,
        limit: int = 10,
    ) -> list[MemoryFact]:
        """Simple keyword search on facts."""
        with self.db.session() as session:
            stmt = select(MemoryFactModel)
            if scope:
                stmt = stmt.where(MemoryFactModel.scope == scope)
            if query:
                stmt = stmt.where(
                    or_(
                        MemoryFactModel.key.ilike(f"%{query}%"),
                        MemoryFactModel.value.ilike(f"%{query}%"),
                    )
                )
            stmt = stmt.order_by(MemoryFactModel.confidence.desc()).limit(limit)
            models = session.execute(stmt).scalars().all()
        return [MemoryFact.from_model(m) for m in models]

    # --- Reserved-key facts (session pointer / checkpoint) ---

    def _upsert_reserved_fact(self, key: str, scope: str, value: str) -> MemoryFact:
        """Upsert a fact by (key, scope) instead of `upsert_fact`'s id-keyed semantics.

        `upsert_fact` looks up rows by `fact.id` (primary key). A freshly
        constructed `MemoryFact` gets a random id, so calling `upsert_fact`
        directly on a new instance would INSERT a duplicate row every time
        instead of updating in place. This helper reads the existing fact by
        (key, scope) first and reuses its id when present.
        """
        existing = self.get_fact(key, scope)
        kwargs = {"key": key, "scope": scope, "value": value, "confidence": 1.0}
        if existing is not None:
            kwargs["id"] = existing.id
        fact = MemoryFact(**kwargs)
        return self.upsert_fact(fact)

    def touch_last_session(self, project: str, session_id: str) -> None:
        """Persist the most recently used session_id for a project."""
        self._upsert_reserved_fact(LAST_SESSION_KEY, f"project:{project}", session_id)

    def get_last_session(self, project: str) -> Optional[str]:
        """Return the last-used session_id for a project, if any."""
        fact = self.get_fact(LAST_SESSION_KEY, f"project:{project}")
        return fact.value if fact else None

    def write_checkpoint(
        self,
        project: str,
        session_id: str,
        *,
        goal: str,
        last_response: str,
        last_tool_result: str,
        iterations_exhausted: bool,
    ) -> None:
        """Upsert the structured per-session checkpoint and touch session:last.

        Deterministic JSON snapshot (see design.md section 3). Free-text
        fields are hard-capped before serialization so the row and its
        rehydrated render stay bounded.
        """
        payload = {
            "v": 1,
            "session_id": session_id,
            "project": project,
            "goal": (goal or "")[:CHECKPOINT_FIELD_CHAR_CAP],
            "open_items": [],
            "last_tool_result": (last_tool_result or "")[:CHECKPOINT_FIELD_CHAR_CAP],
            "last_response": (last_response or "")[:CHECKPOINT_FIELD_CHAR_CAP],
            "iterations_exhausted": iterations_exhausted,
            "updated_at": datetime.utcnow().isoformat() + "Z",
        }
        key = CHECKPOINT_KEY_TEMPLATE.format(session_id=session_id)
        self._upsert_reserved_fact(key, f"project:{project}", json.dumps(payload))
        self.touch_last_session(project, session_id)

    def read_checkpoint(self, project: str, session_id: str) -> Optional[dict]:
        """Return the checkpoint dict for a session, or None if absent."""
        fact = self.get_fact(CHECKPOINT_KEY_TEMPLATE.format(session_id=session_id), f"project:{project}")
        if fact is None:
            return None
        data = json.loads(fact.value)
        data.setdefault("v", 1)
        data.setdefault("open_items", [])
        data.setdefault("last_tool_result", "")
        data.setdefault("last_response", "")
        data.setdefault("iterations_exhausted", False)
        return data

    def increment_fact_access(self, fact_id: str) -> None:
        with self.db.session() as session:
            model = session.get(MemoryFactModel, fact_id)
            if model:
                model.access_count += 1
                model.last_accessed = datetime.utcnow()

    # --- Procedural Memory (Skills) ---

    def upsert_skill(self, skill: Skill) -> Skill:
        with self.db.session() as session:
            existing = session.get(SkillModel, skill.name)
            if existing:
                existing.description = skill.description
                existing.functions = skill.functions_json
                existing.enabled = skill.enabled
                existing.config = skill.config_json
                existing.updated_at = datetime.utcnow()
            else:
                session.add(skill.to_model())
        return skill

    def get_skill(self, name: str) -> Optional[Skill]:
        with self.db.session() as session:
            model = session.get(SkillModel, name)
            return Skill.from_model(model) if model else None

    def list_skills(self, enabled_only: bool = True) -> list[Skill]:
        with self.db.session() as session:
            stmt = select(SkillModel)
            if enabled_only:
                stmt = stmt.where(SkillModel.enabled == True)
            models = session.execute(stmt).scalars().all()
        return [Skill.from_model(m) for m in models]

    # --- Context Assembly ---

    def assemble_context(
        self,
        query: str,
        project: Optional[str] = None,
        session_id: Optional[str] = None,
        max_tokens: int = 8000,
    ) -> MemoryContext:
        """Build context for LLM: relevant facts + recent events + skills."""
        facts = self.search_facts(query, scope=f"project:{project}" if project else None, limit=15)
        if not facts and project:
            facts = [
                fact
                for fact in self.get_facts_by_scope(f"project:{project}", limit=15)
                if not fact.key.startswith(RESERVED_FACT_KEY_PREFIX)
            ]

        events = self.search_events(query, project=project, limit=10)

        if session_id:
            with self.db.session() as session:
                stmt = select(MemoryEventModel).where(
                    and_(
                        MemoryEventModel.session_id == session_id,
                        MemoryEventModel.timestamp >= datetime.utcnow() - timedelta(hours=2),
                    )
                ).order_by(MemoryEventModel.timestamp.desc()).limit(10)
                models = session.execute(stmt).scalars().all()
                session_events = [MemoryEvent.from_model(m) for m in models]
                seen = {event.id for event in events}
                for event in session_events:
                    if event.id not in seen:
                        events.append(event)
                        seen.add(event.id)

        skills = self.list_skills(enabled_only=True)
        context = MemoryContext(
            facts=facts[:20],
            events=events[:15],
            skills=skills,
            total_tokens=0,
        )
        context = self._fit_context_to_budget(context, max_tokens=max_tokens)
        context.total_tokens = self.estimate_context_tokens(context)
        return context

    def estimate_context_tokens(self, context: MemoryContext) -> int:
        return _estimate_tokens(context.format_for_prompt(max_tokens=1_000_000))

    def _fit_context_to_budget(self, context: MemoryContext, max_tokens: int) -> MemoryContext:
        fitted = MemoryContext(skills=context.skills)
        for fact in context.facts:
            candidate = MemoryContext(
                facts=[*fitted.facts, fact],
                events=fitted.events,
                skills=fitted.skills,
            )
            if self.estimate_context_tokens(candidate) > max_tokens:
                break
            fitted.facts.append(fact)

        for event in context.events:
            candidate = MemoryContext(
                facts=fitted.facts,
                events=[*fitted.events, event],
                skills=fitted.skills,
            )
            if self.estimate_context_tokens(candidate) > max_tokens:
                break
            fitted.events.append(event)

        fitted.total_tokens = self.estimate_context_tokens(fitted)
        return fitted

    # --- Consolidation ---

    def consolidate_project(self, project: str, max_events: int = 10000) -> int:
        """Consolidate old events into facts (extract preferences, decisions)."""
        with self.db.session() as session:
            # Count events
            count = session.execute(
                select(func.count(MemoryEventModel.id)).where(MemoryEventModel.project == project)
            ).scalar()

            if count <= max_events:
                return 0

            # Get oldest events for consolidation
            stmt = select(MemoryEventModel).where(
                MemoryEventModel.project == project
            ).order_by(MemoryEventModel.timestamp.asc()).limit(count - max_events)
            old_events = session.execute(stmt).scalars().all()

            # TODO: Use LLM to extract facts from events
            # For now, just mark as consolidated
            fact_count = 0
            for evt in old_events:
                if evt.type in (EventType.USER_PREFERENCE, EventType.DECISION):
                    fact = MemoryFact(
                        key=evt.content[:100],
                        value=evt.content,
                        scope=f"project:{project}",
                        source_event_id=evt.id,
                        confidence=0.8,
                    )
                    self.upsert_fact(fact)
                    fact_count += 1

            return fact_count


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


# Convenience functions

def create_event(
    type: EventType,
    project: str,
    content: str,
    meta: Optional[dict] = None,
    source: str = "user",
    session_id: Optional[str] = None,
) -> MemoryEvent:
    """Create and store an event."""
    repo = MemoryRepository()
    event = MemoryEvent(
        type=type,
        project=project,
        content=content,
        meta=meta or {},
        source=source,
        session_id=session_id,
    )
    return repo.add_event(event)
