"""Session — per-request context passed to the turn handler."""

from __future__ import annotations

from dataclasses import dataclass, field

from assistuff.access.user import User
from assistuff.memory.store import MemoryStore


@dataclass
class Session:
    profile: str
    user: User
    memory: MemoryStore
    metadata: dict = field(default_factory=dict)