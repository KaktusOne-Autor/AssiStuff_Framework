"""TTS emitter placeholder — real implementation in voice/tts.py."""

from __future__ import annotations

import logging
from collections.abc import Callable

from ..events import ChainEvent

logger = logging.getLogger(__name__)


class TtsEmitter:
    def __init__(self, speak: Callable[[str], None], *, only_final: bool = True) -> None:
        self._speak = speak
        self._only_final = only_final

    def __call__(self, event: ChainEvent) -> None:
        if event.kind != "result":
            return
        text = event.payload.get("text")
        if not isinstance(text, str) or not text.strip():
            return
        try:
            self._speak(text)
        except Exception:
            logger.exception("TTS emitter failed")