"""Table-driven tests for the destructive-call gate's pure helpers:
`_is_under_specified` and `_build_clarifying_question` in agentos.agent.core.
"""

from __future__ import annotations

import pytest

from agentos.agent.core import (
    GENERIC_CONTENT_PLACEHOLDERS,
    _is_under_specified,
    _build_clarifying_question,
)


@pytest.mark.parametrize("path", ["", None, "   "])
@pytest.mark.parametrize("fn_name", ["write", "append", "delete"])
def test_is_under_specified_empty_or_none_path_gated(fn_name, path):
    assert _is_under_specified(fn_name, {"path": path, "content": "real content"}) is True


@pytest.mark.parametrize("fn_name", ["write", "append"])
def test_is_under_specified_valid_path_and_content_not_gated(fn_name):
    assert _is_under_specified(fn_name, {"path": "/tmp/x.py", "content": "print('hello')"}) is False


@pytest.mark.parametrize("content", ["", "   ", None])
@pytest.mark.parametrize("fn_name", ["write", "append"])
def test_is_under_specified_empty_or_whitespace_content_gated(fn_name, content):
    assert _is_under_specified(fn_name, {"path": "/tmp/x.py", "content": content}) is True


@pytest.mark.parametrize("token", list(GENERIC_CONTENT_PLACEHOLDERS) + ["TODO", " ... ", "Content Here"])
@pytest.mark.parametrize("fn_name", ["write", "append"])
def test_is_under_specified_placeholder_content_gated(fn_name, token):
    assert _is_under_specified(fn_name, {"path": "/tmp/x.py", "content": token}) is True


@pytest.mark.parametrize("content", ["port=8080", "export default App"])
@pytest.mark.parametrize("fn_name", ["write", "append"])
def test_is_under_specified_real_short_content_not_gated(fn_name, content):
    assert _is_under_specified(fn_name, {"path": "/tmp/x.py", "content": content}) is False


def test_is_under_specified_delete_ignores_content():
    assert _is_under_specified("delete", {"path": "/tmp/x.py"}) is False


def test_build_clarifying_question_missing_path_asks_for_path():
    question = _build_clarifying_question("filesystem", "write", {"path": "", "content": "x"})
    assert "path" in question.lower() or "ruta" in question.lower()


def test_build_clarifying_question_missing_content_asks_for_content():
    question = _build_clarifying_question("filesystem", "write", {"path": "/tmp/x.py", "content": "todo"})
    assert "contenido" in question.lower() or "content" in question.lower()
    assert "/tmp/x.py" in question
