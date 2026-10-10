"""User identity and PUPC level."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class User:
    level: int = 0
    name: str = "guest"

    def can(self, required_level: int) -> bool:
        return self.level >= required_level


def check_permission(user_level: int, required: int) -> bool:
    return user_level >= required