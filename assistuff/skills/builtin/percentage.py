"""Skill: percentages."""

from __future__ import annotations

from assistuff.primitives import percent
from assistuff.skills.registry import SkillContext


def run(value: str, _ctx: SkillContext) -> str:
    return percent.evaluate(value)