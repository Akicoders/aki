"""Model-backed deep audit pass for `aki audit --deep`.

Unlike the deterministic passes in passes.py, this pass sends a bounded
snapshot of the project (file tree + key docs/config) to the Qwen model
and asks it to flag architectural inconsistencies, code/doc mismatches,
reliability risks, semantic smells, and weak context structures that
static/local checks can't catch. It costs tokens and can be slow -- it
is opt-in only, never run by default 'aki audit'.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Optional

from agentos.cockpit.audit.base import AuditContext, AuditFinding
from agentos.qwen.client import QwenClient, QwenStructuredJSONError, get_qwen_client

_MAX_TREE_ENTRIES = 200
_MAX_DOC_CHARS = 4000
_DOC_CANDIDATES = ("README.md", "CLAUDE.md", "pyproject.toml", "package.json")
_VALID_PRIORITIES = {"P0", "P1", "P2", "P3"}

_SYSTEM_PROMPT = """You are a senior software architect performing a deep, model-backed audit \
of a codebase. You are given a bounded snapshot: a file tree and the contents of a few key \
docs/config files. You do NOT have the full source.

Focus on what static/local checks cannot catch:
- architectural inconsistencies
- code/documentation mismatches
- reliability risks
- semantic smells
- missing or weak context structures

Respond with ONLY a JSON array of findings, no prose, no markdown fences. Each finding:
{"priority": "P0"|"P1"|"P2"|"P3", "category": string, "title": string, "evidence": string, \
"recommendation": string}

If you have no findings, respond with an empty JSON array: []
"""


def _collect_file_tree(root_path: Path) -> list[str]:
    entries: list[str] = []
    skip_dirs = {".git", "__pycache__", "node_modules", ".venv", "venv", ".pytest_cache"}
    for path in sorted(root_path.rglob("*")):
        if any(part in skip_dirs for part in path.parts):
            continue
        try:
            rel = path.relative_to(root_path)
        except ValueError:
            continue
        entries.append(str(rel))
        if len(entries) >= _MAX_TREE_ENTRIES:
            break
    return entries


def _collect_key_docs(root_path: Path) -> dict[str, str]:
    docs: dict[str, str] = {}
    for name in _DOC_CANDIDATES:
        candidate = root_path / name
        if candidate.is_file():
            try:
                docs[name] = candidate.read_text(encoding="utf-8", errors="replace")[:_MAX_DOC_CHARS]
            except OSError:
                continue
    return docs


def _build_user_message(root_path: Path) -> str:
    tree = _collect_file_tree(root_path)
    docs = _collect_key_docs(root_path)

    parts = [f"File tree ({len(tree)} entries, capped at {_MAX_TREE_ENTRIES}):", "\n".join(tree)]
    for name, content in docs.items():
        parts.append(f"\n--- {name} ---\n{content}")
    return "\n".join(parts)


def _parse_findings(raw_content: str) -> list[AuditFinding]:
    content = raw_content.strip()
    if content.startswith("```"):
        content = content.strip("`")
        if content.startswith("json"):
            content = content[4:]
    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        raise QwenStructuredJSONError(f"Deep audit response was not valid JSON: {exc}") from exc

    if not isinstance(data, list):
        raise QwenStructuredJSONError("Deep audit response was not a JSON array")

    findings: list[AuditFinding] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        priority = item.get("priority", "P3")
        if priority not in _VALID_PRIORITIES:
            priority = "P3"
        findings.append(
            AuditFinding(
                priority=priority,
                category=item.get("category", "deep"),
                title=item.get("title", "Untitled finding"),
                evidence=item.get("evidence", ""),
                recommendation=item.get("recommendation", ""),
                autofixable_later=False,
            )
        )
    return findings


class DeepAuditPass:
    """Model-backed audit pass. Opt-in only via 'aki audit --deep'."""

    id = "deep"

    def __init__(self, qwen_client: Optional[QwenClient] = None):
        self._qwen = qwen_client

    def run(self, ctx: AuditContext) -> list[AuditFinding]:
        qwen = self._qwen or get_qwen_client()
        user_message = _build_user_message(ctx.root_path)

        async def _call() -> str:
            response = await qwen.chat(
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": user_message},
                ],
                tools=None,
                tool_choice=None,
                temperature=0.2,
            )
            return response.content

        try:
            raw_content = asyncio.run(_call())
            return _parse_findings(raw_content)
        except Exception as exc:  # noqa: BLE001 - deep audit must never crash the whole run
            return [
                AuditFinding(
                    priority="P2",
                    category="deep",
                    title="Deep audit pass failed",
                    evidence=str(exc),
                    recommendation="Check Qwen API credentials/connectivity and retry 'aki audit --deep'.",
                    autofixable_later=False,
                )
            ]
