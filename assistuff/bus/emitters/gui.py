"""GUI emitter placeholder — real implementation in ui/panels/chat.py."""

from __future__ import annotations

from collections.abc import Callable

from ..events import ChainEvent


class GuiEmitter:
    def __init__(self, callback: Callable[[ChainEvent], None] | None = None) -> None:
        self._callback = callback

    def __call__(self, event: ChainEvent) -> None:
        if self._callback is not None:
            self._callback(event)