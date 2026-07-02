from __future__ import annotations

import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

from agentos.cockpit.audit.base import AuditContext
from agentos.cockpit.audit.deep import DeepAuditPass, _parse_findings


def _make_ctx(root_path) -> AuditContext:
    return AuditContext(project=MagicMock(), root_path=root_path, generated_at=datetime.now())


def _chat_response(content: str):
    response = MagicMock()
    response.content = content
    return response


def test_deep_pass_parses_valid_json_findings(tmp_path):
    (tmp_path / "README.md").write_text("# Project\n", encoding="utf-8")

    qwen = AsyncMock()
    findings_json = json.dumps([
        {
            "priority": "P1",
            "category": "architecture",
            "title": "Docs claim X, code does Y",
            "evidence": "README says async but handler is sync",
            "recommendation": "Update README or fix handler",
        }
    ])
    qwen.chat.return_value = _chat_response(findings_json)

    pass_ = DeepAuditPass(qwen_client=qwen)
    findings = pass_.run(_make_ctx(tmp_path))

    assert len(findings) == 1
    assert findings[0].priority == "P1"
    assert findings[0].category == "architecture"
    qwen.chat.assert_awaited_once()


def test_deep_pass_handles_empty_findings(tmp_path):
    qwen = AsyncMock()
    qwen.chat.return_value = _chat_response("[]")

    pass_ = DeepAuditPass(qwen_client=qwen)
    findings = pass_.run(_make_ctx(tmp_path))

    assert findings == []


def test_deep_pass_never_crashes_on_bad_model_output(tmp_path):
    qwen = AsyncMock()
    qwen.chat.return_value = _chat_response("not json at all")

    pass_ = DeepAuditPass(qwen_client=qwen)
    findings = pass_.run(_make_ctx(tmp_path))

    assert len(findings) == 1
    assert findings[0].category == "deep"
    assert findings[0].priority == "P2"


def test_deep_pass_never_crashes_on_client_error(tmp_path):
    qwen = AsyncMock()
    qwen.chat.side_effect = RuntimeError("connection refused")

    pass_ = DeepAuditPass(qwen_client=qwen)
    findings = pass_.run(_make_ctx(tmp_path))

    assert len(findings) == 1
    assert "connection refused" in findings[0].evidence


def test_parse_findings_strips_markdown_fences():
    fenced = "```json\n[{\"priority\": \"P0\", \"category\": \"c\", \"title\": \"t\", \"evidence\": \"e\", \"recommendation\": \"r\"}]\n```"
    findings = _parse_findings(fenced)
    assert len(findings) == 1
    assert findings[0].priority == "P0"


def test_parse_findings_defaults_invalid_priority_to_p3():
    raw = json.dumps([{"priority": "URGENT", "category": "c", "title": "t"}])
    findings = _parse_findings(raw)
    assert findings[0].priority == "P3"
