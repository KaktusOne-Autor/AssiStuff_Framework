"""Skill registry."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from assistuff.access.user import User
    from assistuff.memory.store import MemoryStore

_SKILL_ID_RE = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")


@dataclass
class SkillContext:
    profile: str
    memory: "MemoryStore"
    user: "User"


@dataclass
class Skill:
    name: str
    run: Callable[[str, SkillContext], str]
    permission: str | None = None
    description: str = ""


class SkillPermissionDenied(PermissionError):
    pass


class SkillRegistry:
    def __init__(self) -> None:
        self._skills: dict[str, Skill] = {}

    def register(
        self,
        name: str,
        run: Callable[[str, SkillContext], str],
        *,
        permission: str | None = None,
        description: str = "",
    ) -> None:
        if not _SKILL_ID_RE.fullmatch(name):
            raise ValueError(f"invalid skill id: {name!r}")
        if not callable(run):
            raise TypeError(f"skill handler must be callable: {name}")
        if name in self._skills:
            raise ValueError(f"skill already registered: {name}")
        self._skills[name] = Skill(
            name=name,
            run=run,
            permission=permission,
            description=description,
        )

    def get(self, name: str) -> Skill:
        try:
            return self._skills[name]
        except KeyError as exc:
            raise KeyError(f"unknown skill: {name}") from exc

    def names(self) -> list[str]:
        return sorted(self._skills)

    def all(self) -> list[Skill]:
        return [self._skills[name] for name in self.names()]