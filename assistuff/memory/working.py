"""Layer 1: working memory — in-memory, per trace."""

from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class WorkingMemory:
    trace_id: str
    started_at: float = field(default_factory=time.time)
    entries: dict[str, object] = field(default_factory=dict)

    def set(self, key: str, value: object) -> None:
        self.entries[key] = value

    def get(self, key: str, default: object = None) -> object:
        return self.entries.get(key, default)

    def clear(self) -> None:
        self.entries.clear()

    @property
    def age_seconds(self) -> float:
        return time.time() - self.started_at