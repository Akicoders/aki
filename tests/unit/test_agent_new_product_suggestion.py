"""Table-driven tests for the new-product-suggestion pure helpers:
`_is_new_product_request` and `_build_new_product_suggestion` in
agentos.agent.core (Phase 1 of sdd-scaffolding-flow-suggestion).
"""

from __future__ import annotations

import pytest

from agentos.agent.core import (
    NEW_PRODUCT_KEYWORDS,
    SCAFFOLDING_KEYWORDS,
    _is_new_product_request,
    _build_new_product_suggestion,
)


def test_is_new_product_request_canonical_failure_case():
    assert _is_new_product_request("necesitamos ya poder tener el astro hecho") is True


@pytest.mark.parametrize(
    "message",
    [
        "armar toda la app",
        "build me a new app",
        "todo el proyecto desde cero",
        "set up the entire project",
        "ARMAR TODA LA APP",
    ],
)
def test_is_new_product_request_bilingual_variants(message):
    assert _is_new_product_request(message) is True


def test_is_new_product_request_scaffolding_phrase_not_matched():
    assert _is_new_product_request("creá un componente nuevo") is False


def test_is_new_product_request_unrelated_message_not_matched():
    assert _is_new_product_request("leé el archivo config.py") is False


def test_new_product_keywords_do_not_overlap_scaffolding_keywords():
    for kw in NEW_PRODUCT_KEYWORDS:
        assert kw not in SCAFFOLDING_KEYWORDS


def test_build_new_product_suggestion_has_sdd_mentions_continue():
    text = _build_new_product_suggestion(has_sdd=True)
    lowered = text.lower()
    assert "sdd-init" not in lowered
    assert "retomar" in lowered or "continuar" in lowered or "en curso" in lowered


def test_build_new_product_suggestion_no_sdd_mentions_bootstrap():
    text = _build_new_product_suggestion(has_sdd=False)
    assert "sdd-init" in text.lower()


@pytest.mark.parametrize("has_sdd", [True, False])
def test_build_new_product_suggestion_no_worker_vocabulary(has_sdd):
    text = _build_new_product_suggestion(has_sdd=has_sdd).lower()
    assert "delegate" not in text
    assert "worker" not in text


@pytest.mark.parametrize("has_sdd", [True, False])
def test_build_new_product_suggestion_is_advisory(has_sdd):
    text = _build_new_product_suggestion(has_sdd=has_sdd).lower()
    assert "si preferís" in text and "decímelo" in text
