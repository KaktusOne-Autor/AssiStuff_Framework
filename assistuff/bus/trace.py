"""Trace — one user turn's full call graph."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field

from .events import ChainEvent


@dataclass
class Trace:
    query: str
    trace_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    started_at: float = field(default_factory=time.time)
    finished_at: float | None = None
    hops: int = 0
    events: list[ChainEvent] = field(default_factory=list)
    call_stack: list[str] = field(default_factory=list)

    def push(self, node: str) -> None:
        self.call_stack.append(node)
        self.hops += 1

    def pop(self) -> None:
        if self.call_stack:
            self.call_stack.pop()

    def record(self, event: ChainEvent) -> None:
        self.events.append(event)

    def finish(self) -> None:
        self.finished_at = time.time()

    @property
    def elapsed_ms(self) -> float:
        end = self.finished_at or time.time()
        return (end - self.started_at) * 1000.0

    def summary(self) -> dict:
        return {
            "trace_id": self.trace_id,
            "query": self.query,
            "hops": self.hops,
            "events": len(self.events),
            "elapsed_ms": round(self.elapsed_ms, 1),
            "path": list(self.call_stack),
        }