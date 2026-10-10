"""Output Chain — the single path from models to the user."""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from collections.abc import AsyncIterator, Callable

from .events import ChainEvent

logger = logging.getLogger(__name__)

Emitter = Callable[[ChainEvent], None]


class OutputChain:
    """Collects ChainEvents and dispatches them to subscribers.

    By default, emits synchronously to subscriber callables and queues
    events per trace so callers can await ``collect(trace_id)``.
    """

    def __init__(self) -> None:
        self._subscribers: list[Emitter] = []
        self._queues: dict[str, asyncio.Queue[ChainEvent]] = defaultdict(asyncio.Queue)
        self._closed: set[str] = set()

    def subscribe(self, emitter: Emitter) -> None:
        if not callable(emitter):
            raise TypeError("emitter must be callable")
        self._subscribers.append(emitter)

    def emit(self, event: ChainEvent) -> None:
        self._queues[event.trace_id].put_nowait(event)
        for emitter in self._subscribers:
            try:
                emitter(event)
            except Exception:
                logger.exception("emitter failed for event from %s", event.source)

    def close(self, trace_id: str) -> None:
        if trace_id in self._closed:
            return
        self._closed.add(trace_id)
        self._queues[trace_id].put_nowait(_SENTINEL)

    async def collect(self, trace_id: str) -> AsyncIterator[ChainEvent]:
        queue = self._queues[trace_id]
        while True:
            event = await queue.get()
            if event is _SENTINEL:
                break
            yield event

    def events(self, trace_id: str) -> list[ChainEvent]:
        """Return all events emitted so far for a trace (without consuming)."""
        # Consumers usually prefer collect(); this is for GUI snapshots.
        queue = self._queues.get(trace_id)
        if queue is None:
            return []
        return list(queue._queue)  # noqa: SLF001 — pragmatic introspection

    def final_result(self, trace_id: str) -> str | None:
        for event in reversed(self.events(trace_id)):
            if event.kind == "result":
                text = event.payload.get("text")
                if isinstance(text, str):
                    return text
        return None


class _Sentinel:
    pass


_SENTINEL = _Sentinel()