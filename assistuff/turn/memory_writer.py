"""Turn memory writer — persists the exchange and triggers dossier compile."""

from __future__ import annotations

import logging

from assistuff.memory.store import MemoryStore

logger = logging.getLogger(__name__)


class MemoryWriter:
    def __init__(
        self,
        store: MemoryStore,
        *,
        compile_hook=None,
        enabled: bool = True,
    ) -> None:
        self.store = store
        self.compile_hook = compile_hook
        self.enabled = enabled

    async def record(
        self,
        *,
        user_text: str,
        assistant_text: str,
        summary: str = "",
    ) -> None:
        if not self.enabled:
            return
        try:
            self.store.short_term.add_message("user", user_text)
            self.store.short_term.add_message("assistant", assistant_text)
        except Exception:
            logger.exception("failed to record messages")
            return

        if summary:
            try:
                self.store.long_term.append(summary, ["#events"])
            except Exception:
                logger.exception("failed to append summary")

        if self.compile_hook is not None:
            try:
                result = self.compile_hook()
                if hasattr(result, "__await__"):
                    await result
            except Exception:
                logger.exception("dossier compile hook failed")