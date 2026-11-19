"""Shared UI context passed to panels."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from assistuff.bus.events import ChainEvent
from assistuff.config.schemas import RuntimeConfigBundle

AUDIO_ENABLED_SETTING = "voice/audio_enabled"
SETTINGS_APPLICATION = "AssiStuff"
SETTINGS_ORGANIZATION = "AssiStuff"


@dataclass
class UiContext:
    config: RuntimeConfigBundle
    dispatcher: Any = None          # Dispatcher or None
    profile: str = "default"
    user_level: int = 0
    user_name: str = "guest"
    account_id: str | None = None
    authenticated: bool = False
    metadata: dict = field(default_factory=dict)

    def emit_test_event(self, trace_id: str = "ui") -> ChainEvent:
        return ChainEvent(
            trace_id=trace_id,
            source="ui",
            kind="result",
            payload={"text": "ui event"},
        )
