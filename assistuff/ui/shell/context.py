"""Shared UI context passed to panels."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from assistuff.bus.events import ChainEvent
from assistuff.config.schemas import RuntimeConfigBundle


@dataclass
class UiContext:
    config: RuntimeConfigBundle
    dispatcher: Any = None          # Dispatcher or None
    profile: str = "default"
    user_level: int = 0
    metadata: dict = field(default_factory=dict)

    def emit_test_event(self, trace_id: str = "ui") -> ChainEvent:
        return ChainEvent(
            trace_id=trace_id,
            source="ui",
            kind="result",
            payload={"text": "ui event"},
        )