"""Memory models for Aki."""

from datetime import datetime
from enum import Enum
from typing import Any, Optional
from uuid import uuid4
from pydantic import BaseModel, Field
from sqlalchemy import (
    String, Text, DateTime, Integer, Float, ForeignKey, Index, Enum as SQLEnum
)
from sqlalchemy.orm import Mapped, mapped_column, DeclarativeBase
import json


class MemoryType(str, Enum):
    EPISODIC = "episodic"       # Events: what happened
    SEMANTIC = "semantic"       # Facts: what we know
    PROCEDURAL = "procedural"   # Skills: how to do things


class EventType(str, Enum):
    USER_PREFERENCE = "user_preference"
    DECISION = "decision"
    TASK = "task"
    CONVERSATION = "conversation"
    ERROR = "error"
    OUTCOME = "outcome"
    CODE_CHANGE = "code_change"
    DEPLOY = "deploy"


class Base(DeclarativeBase):
    pass


class MemoryEventModel(Base):
    __tablename__ = "memory_events"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    type: Mapped[EventType] = mapped_column(SQLEnum(EventType), index=True)
    project: Mapped[str] = mapped_column(String(128), index=True)
    content: Mapped[str] = mapped_column(Text)
    meta: Mapped[str] = mapped_column(Text, default="{}")  # JSON
    embedding: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON array
    timestamp: Mapped[datetime] = mapped_column(DateTime, index=True, default=datetime.utcnow)
    source: Mapped[str] = mapped_column(String(64), default="user")  # user, agent, system
    session_id: Mapped[Optional[str]] = mapped_column(String(64), index=True, nullable=True)

    __table_args__ = (
        Index("ix_memory_events_project_timestamp", "project", "timestamp"),
        Index("ix_memory_events_type_project", "type", "project"),
    )


class MemoryFactModel(Base):
    __tablename__ = "memory_facts"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    key: Mapped[str] = mapped_column(String(256), index=True)
    value: Mapped[str] = mapped_column(Text)
    scope: Mapped[str] = mapped_column(String(256), index=True)  # project:ERP-AI, global, user:paul
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    source_event_id: Mapped[Optional[str]] = mapped_column(String(64), ForeignKey("memory_events.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    access_count: Mapped[int] = mapped_column(Integer, default=0)
    last_accessed: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    __table_args__ = (
        Index("ix_memory_facts_scope_key", "scope", "key"),
    )


class SkillModel(Base):
    __tablename__ = "skills"

    name: Mapped[str] = mapped_column(String(128), primary_key=True)
    description: Mapped[str] = mapped_column(Text)
    functions: Mapped[str] = mapped_column(Text)  # JSON array
    enabled: Mapped[bool] = mapped_column(default=True)
    config: Mapped[str] = mapped_column(Text, default="{}")  # JSON
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# Pydantic models for API/CLI

class MemoryEvent(BaseModel):
    id: str = Field(default_factory=lambda: f"evt_{uuid4().hex[:8]}")
    type: EventType
    project: str
    content: str
    meta: dict[str, Any] = Field(default_factory=dict)
    embedding: Optional[list[float]] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    source: str = "user"
    session_id: Optional[str] = None

    @classmethod
    def from_model(cls, model: MemoryEventModel) -> "MemoryEvent":
        return cls(
            id=model.id,
            type=model.type,
            project=model.project,
            content=model.content,
            meta=json.loads(model.meta) if model.meta else {},
            embedding=json.loads(model.embedding) if model.embedding else None,
            timestamp=model.timestamp,
            source=model.source,
            session_id=model.session_id,
        )

    def to_model(self) -> MemoryEventModel:
        return MemoryEventModel(
            id=self.id,
            type=self.type,
            project=self.project,
            content=self.content,
            meta=json.dumps(self.meta),
            embedding=json.dumps(self.embedding) if self.embedding else None,
            timestamp=self.timestamp,
            source=self.source,
            session_id=self.session_id,
        )


class MemoryFact(BaseModel):
    id: str = Field(default_factory=lambda: f"fact_{uuid4().hex[:8]}")
    key: str
    value: str
    scope: str
    confidence: float = 1.0
    source_event_id: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    access_count: int = 0
    last_accessed: Optional[datetime] = None

    @classmethod
    def from_model(cls, model: MemoryFactModel) -> "MemoryFact":
        return cls(
            id=model.id,
            key=model.key,
            value=model.value,
            scope=model.scope,
            confidence=model.confidence,
            source_event_id=model.source_event_id,
            created_at=model.created_at,
            updated_at=model.updated_at,
            access_count=model.access_count,
            last_accessed=model.last_accessed,
        )

    def to_model(self) -> MemoryFactModel:
        return MemoryFactModel(
            id=self.id,
            key=self.key,
            value=self.value,
            scope=self.scope,
            confidence=self.confidence,
            source_event_id=self.source_event_id,
            created_at=self.created_at,
            updated_at=self.updated_at,
            access_count=self.access_count,
            last_accessed=self.last_accessed,
        )


class Skill(BaseModel):
    name: str
    description: str
    functions: list[str]
    enabled: bool = True
    config: dict[str, Any] = Field(default_factory=dict)

    @property
    def functions_json(self) -> str:
        return json.dumps(self.functions)

    @property
    def config_json(self) -> str:
        return json.dumps(self.config)

    @classmethod
    def from_model(cls, model: SkillModel) -> "Skill":
        return cls(
            name=model.name,
            description=model.description,
            functions=json.loads(model.functions),
            enabled=model.enabled,
            config=json.loads(model.config),
        )

    def to_model(self) -> SkillModel:
        return SkillModel(
            name=self.name,
            description=self.description,
            functions=self.functions_json,
            enabled=self.enabled,
            config=self.config_json,
        )


class MemoryContext(BaseModel):
    """Assembled context for LLM injection."""
    events: list[MemoryEvent] = Field(default_factory=list)
    facts: list[MemoryFact] = Field(default_factory=list)
    skills: list[Skill] = Field(default_factory=list)
    total_tokens: int = 0

    def format_for_prompt(self, max_tokens: int = 8000) -> str:
        sections: list[str] = []
        used_tokens = 0

        section_builders = [
            ("Hechos conocidos", [
                f"- [{fact.scope}] {fact.key} = {fact.value} (confidence: {fact.confidence:.2f})"
                for fact in self.facts[:20]
            ]),
            ("Eventos recientes", [
                f"- [{event.timestamp:%Y-%m-%d %H:%M}] ({event.type.value}) {event.project}: {event.content[:200]}"
                for event in self.events[:15]
            ]),
            ("Herramientas disponibles", [
                f"- {skill.name}: {skill.description} — funciones: {', '.join(skill.functions)}"
                for skill in self.skills
                if skill.enabled
            ]),
        ]

        for title, lines in section_builders:
            if not lines:
                continue
            accepted_lines: list[str] = []
            section_overhead = _estimate_tokens(title) + 4
            for line in lines:
                line_tokens = _estimate_tokens(line)
                projected = used_tokens + section_overhead + sum(_estimate_tokens(item) for item in accepted_lines) + line_tokens
                if projected > max_tokens:
                    break
                accepted_lines.append(line)
            if not accepted_lines:
                continue
            body = "\n".join(accepted_lines)
            section = f"{title}:\n{body}"
            sections.append(section)
            used_tokens += _estimate_tokens(section)
            if used_tokens >= max_tokens:
                break

        return "\n\n".join(sections)


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)
