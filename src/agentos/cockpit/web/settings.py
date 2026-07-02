"""Settings for the cockpit web server."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class WebServerSettings:
    """Host/port configuration for `aki cockpit --web`.

    Kept as a small, additive dataclass local to the web package rather than
    part of `agentos.core.config` — the web server's bind address is an
    opt-in CLI concern, not persistent project configuration.
    """

    host: str = "127.0.0.1"
    port: int = 8420
