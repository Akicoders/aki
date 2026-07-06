"""Tests for user-facing error message mapping in the interactive CLI."""

import httpx
import pytest

from agentos.cli.main import _friendly_turn_error


def test_timeout_exception_maps_to_friendly_message():
    exc = httpx.TimeoutException("timed out")
    assert "timeout" in _friendly_turn_error(exc).lower()


def test_connect_error_maps_to_friendly_message():
    exc = httpx.ConnectError("connection refused")
    assert "conectar" in _friendly_turn_error(exc).lower()


@pytest.mark.parametrize("status_code,keyword", [(401, "api key"), (429, "límite")])
def test_http_status_error_maps_known_codes(status_code, keyword):
    request = httpx.Request("POST", "https://example.com")
    response = httpx.Response(status_code, request=request)
    exc = httpx.HTTPStatusError("error", request=request, response=response)
    assert keyword in _friendly_turn_error(exc).lower()


def test_unmapped_exception_falls_back_to_str():
    exc = ValueError("something specific")
    assert _friendly_turn_error(exc) == "something specific"
