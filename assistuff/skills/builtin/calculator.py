"""Skill: calculator."""

from __future__ import annotations

from assistuff.primitives import arithmetic
from assistuff.skills.registry import SkillContext


def run(value: str, _ctx: SkillContext) -> str:
    expression = value.strip()
    for prefix in ("calculate", "compute", "посчитай", "вычисли", "сколько будет"):
        if expression.lower().startswith(prefix):
            expression = expression[len(prefix):].strip(" :?")
            break
    expression = expression.replace(",", ".")
    result = arithmetic.evaluate(expression)
    return f"{result:g}"