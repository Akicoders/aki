"""Qwen-powered memory extraction with deterministic validation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


class StructuredJSONClient(Protocol):
    async def structured_json(
        self,
        prompt: str,
        system_prompt: str | None = None,
        max_tokens: int | None = None,
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

        try:
            payload = await self.qwen_client.structured_json(
                _build_extraction_prompt(text),
                system_prompt=(
                    "Extract coding-agent memory candidates. Return only JSON with "
                    "top-level arrays: facts, decisions, procedures. Each item must include "
                    "title, content, confidence, and provenance."
                ),
            )
        except Exception as exc:
            return ExtractionResult(ok=False, errors=[f"Qwen extraction failed: {exc}"])

        candidates, errors = validate_extraction_payload(payload)
        return ExtractionResult(ok=bool(candidates) and not errors, candidates=candidates, errors=errors)


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


def _build_extraction_prompt(text: str) -> str:
    return (
        "Extract durable project memories from this text. "
        "Use facts for stable knowledge, decisions for chosen direction, and procedures for repeatable steps.\n\n"
        f"Text:\n{text}"
    )
