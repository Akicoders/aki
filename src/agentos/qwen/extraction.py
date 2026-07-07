"""Qwen-powered memory extraction with deterministic validation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from agentos.core.config import get_config


class StructuredJSONClient(Protocol):
    async def structured_json(
        self,
        prompt: str,
        system_prompt: str | None = None,
        max_tokens: int | None = None,
        model: str | None = None,
    ) -> dict[str, Any]:
        """Return a parsed JSON object from a prompt."""


@dataclass(frozen=True)
class MemoryCandidate:
    kind: str
    title: str
    content: str
    confidence: float
    provenance: str


@dataclass(frozen=True)
class ExtractionResult:
    ok: bool
    candidates: list[MemoryCandidate] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def grouped(self) -> dict[str, list[MemoryCandidate]]:
        return {
            "facts": [candidate for candidate in self.candidates if candidate.kind == "fact"],
            "decisions": [candidate for candidate in self.candidates if candidate.kind == "decision"],
            "procedures": [candidate for candidate in self.candidates if candidate.kind == "procedure"],
        }


class QwenMemoryExtractor:
    """Extract validated memory candidates from source text."""

    def __init__(self, qwen_client: StructuredJSONClient):
        self.qwen_client = qwen_client

    async def extract(self, text: str) -> ExtractionResult:
        if not text.strip():
            return ExtractionResult(ok=False, errors=["text is required"])

        config = get_config().qwen
        extraction_model = config.extraction_model or config.model
        consolidation_model = config.consolidation_model or config.model
        chunks = _chunk_text(text)

        all_candidates: list[MemoryCandidate] = []
        errors: list[str] = []
        for index, chunk in enumerate(chunks):
            try:
                payload = await self.qwen_client.structured_json(
                    _build_extraction_prompt(chunk, index=index, total=len(chunks)),
                    system_prompt=(
                        "Extract coding-agent memory candidates. Return only JSON with "
                        "top-level arrays: facts, decisions, procedures. Each item must include "
                        "title, content, confidence, and provenance."
                    ),
                    model=extraction_model,
                )
            except Exception as exc:
                return ExtractionResult(ok=False, errors=[f"Qwen extraction failed: {exc}"])

            candidates, item_errors = validate_extraction_payload(payload)
            all_candidates.extend(candidates)
            errors.extend(item_errors)

        deduped = _dedupe_candidates(all_candidates)
        if len(chunks) == 1 or len(deduped) <= 1:
            return ExtractionResult(ok=len(deduped) > 0, candidates=deduped, errors=errors)

        try:
            consolidated_payload = await self.qwen_client.structured_json(
                _build_consolidation_prompt(deduped),
                system_prompt=(
                    "Merge duplicate or overlapping coding-agent memories. Return only JSON with "
                    "top-level arrays: facts, decisions, procedures. Keep the strongest non-duplicated items."
                ),
                model=consolidation_model,
            )
            consolidated, consolidation_errors = validate_extraction_payload(consolidated_payload)
            if consolidated:
                deduped = _dedupe_candidates(consolidated)
            errors.extend(consolidation_errors)
        except Exception:
            # Deterministic dedupe is a valid fallback when model-based consolidation is unavailable.
            pass

        return ExtractionResult(ok=len(deduped) > 0, candidates=deduped, errors=errors)


def validate_extraction_payload(payload: dict[str, Any]) -> tuple[list[MemoryCandidate], list[str]]:
    candidates: list[MemoryCandidate] = []
    errors: list[str] = []
    group_to_kind = {"facts": "fact", "decisions": "decision", "procedures": "procedure"}

    for group in payload:
        if group not in group_to_kind:
            errors.append(f"unsupported group: {group}")

    for group, kind in group_to_kind.items():
        raw_items = payload.get(group, [])
        if raw_items is None:
            continue
        if not isinstance(raw_items, list):
            errors.append(f"{group} must be a list")
            continue
        for index, raw_item in enumerate(raw_items):
            candidate, item_errors = _candidate_from_raw(kind, raw_item, f"{group}[{index}]")
            errors.extend(item_errors)
            if candidate is not None:
                candidates.append(candidate)

    return candidates, errors


def _candidate_from_raw(
    kind: str,
    raw_item: Any,
    path: str,
) -> tuple[MemoryCandidate | None, list[str]]:
    if not isinstance(raw_item, dict):
        return None, [f"{path} must be an object"]

    title = str(raw_item.get("title", "")).strip()
    content = str(raw_item.get("content", "")).strip()
    provenance = str(raw_item.get("provenance", "")).strip()
    confidence = raw_item.get("confidence")

    errors = []
    if not title:
        errors.append(f"{path} missing title")
    if not content:
        errors.append(f"{path} missing content")

    if not provenance:
        errors.append(f"{path} missing provenance")
    if not isinstance(confidence, int | float) or not 0 <= float(confidence) <= 1:
        errors.append(f"{path} confidence must be between 0 and 1")

    if errors:
        return None, errors
    return MemoryCandidate(kind, title, content, float(confidence), provenance), []


def _build_extraction_prompt(text: str, *, index: int, total: int) -> str:
    return (
        "Extract durable project memories from this text chunk. "
        "Use facts for stable knowledge, decisions for chosen direction, and procedures for repeatable steps.\n\n"
        f"Chunk {index + 1}/{total}:\n{text}"
    )


def _build_consolidation_prompt(candidates: list[MemoryCandidate]) -> str:
    payload = {
        "facts": [_candidate_dict(candidate) for candidate in candidates if candidate.kind == "fact"],
        "decisions": [_candidate_dict(candidate) for candidate in candidates if candidate.kind == "decision"],
        "procedures": [_candidate_dict(candidate) for candidate in candidates if candidate.kind == "procedure"],
    }
    return (
        "Merge duplicate or overlapping memories. Prefer concise durable statements, keep provenance, "
        "and drop near-identical duplicates.\n\n"
        f"Candidates: {payload}"
    )


def _chunk_text(text: str, max_chars: int = 1800) -> list[str]:
    normalized = text.strip()
    if len(normalized) <= max_chars:
        return [normalized]

    chunks: list[str] = []
    current = ""
    for paragraph in [part.strip() for part in normalized.split("\n\n") if part.strip()]:
        separator = "\n\n" if current else ""
        if len(current) + len(separator) + len(paragraph) <= max_chars:
            current = f"{current}{separator}{paragraph}"
            continue
        if current:
            chunks.append(current)
            current = ""
        if len(paragraph) <= max_chars:
            current = paragraph
            continue
        for start in range(0, len(paragraph), max_chars):
            chunks.append(paragraph[start : start + max_chars])
    if current:
        chunks.append(current)
    return chunks or [normalized]


def _dedupe_candidates(candidates: list[MemoryCandidate]) -> list[MemoryCandidate]:
    deduped: dict[tuple[str, str, str], MemoryCandidate] = {}
    for candidate in candidates:
        key = (
            candidate.kind,
            _normalize(candidate.title),
            _normalize(candidate.content),
        )
        existing = deduped.get(key)
        if existing is None or candidate.confidence > existing.confidence:
            deduped[key] = candidate
    return list(deduped.values())


def _candidate_dict(candidate: MemoryCandidate) -> dict[str, Any]:
    return {
        "title": candidate.title,
        "content": candidate.content,
        "confidence": candidate.confidence,
        "provenance": candidate.provenance,
    }


def _normalize(text: str) -> str:
    return " ".join(text.lower().split())
