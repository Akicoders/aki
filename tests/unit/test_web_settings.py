from __future__ import annotations

from agentos.cockpit.web.settings import WebServerSettings


def test_web_server_settings_defaults():
    settings = WebServerSettings()

    assert settings.host == "127.0.0.1"
    assert settings.port == 8420
