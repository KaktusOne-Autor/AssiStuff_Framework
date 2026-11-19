"""OutputChain emitter that speaks final text results."""

from __future__ import annotations

import logging
from collections.abc import Callable

from ..events import ChainEvent

logger = logging.getLogger(__name__)

TtsErrorHandler = Callable[[Exception], None]


class TtsEmitter:
    def __init__(
        self,
        speak: Callable[[str], None],
        *,
        only_final: bool = True,
        on_error: TtsErrorHandler | None = None,
    ) -> None:
        self._speak = speak
        self._only_final = only_final
        self._on_error = on_error

    def __call__(self, event: ChainEvent) -> None:
        if event.kind != "result":
            return
        if self._only_final and event.payload.get("_final") is not True:
            return
        text = event.payload.get("text")
        if not isinstance(text, str) or not text.strip():
            return
        try:
            self._speak(text)
        except Exception as exc:
            logger.exception("TTS emitter failed")
            if self._on_error is not None:
                self._on_error(exc)
