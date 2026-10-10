"""Chain events flowing through the Output Chain."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Literal

EventKind = Literal["result", "citation", "progress", "error"]


@dataclass(frozen=True)
class ChainEvent:
    trace_id: str
    source: str
    kind: EventKind
    payload: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    def __post_init__(self) -> None:
        if not self.trace_id:
            raise ValueError("trace_id must not be empty")
        if not self.source:
            raise ValueError("source must not be empty")
        if self.kind not in ("result", "citation", "progress", "error"):
            raise ValueError(f"invalid kind: {self.kind!r}")