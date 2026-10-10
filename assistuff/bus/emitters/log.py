"""Log emitter for Output Chain."""

from __future__ import annotations

import logging

from ..events import ChainEvent

logger = logging.getLogger("assistuff.output")


def log_emitter(event: ChainEvent) -> None:
    text = event.payload.get("text", "")
    preview = text if len(text) <= 200 else text[:200] + "…"
    logger.info(
        "[%s] %s (%s): %s",
        event.trace_id[:8],
        event.source,
        event.kind,
        preview or event.payload,
    )