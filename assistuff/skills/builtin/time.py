"""Skill: current time and date."""

from __future__ import annotations

import re

from assistuff.primitives import time_ops
from assistuff.skills.registry import SkillContext


def run(value: str, _ctx: SkillContext) -> str:
    now = time_ops.now()
    is_ru = bool(re.search(r"[а-яё]", value, re.IGNORECASE))
    if re.search(r"\byesterday\b|\bвчера\b", value, re.IGNORECASE):
        yesterday = time_ops.yesterday_iso()
        if is_ru:
            return f"Вчера было {yesterday}. Сейчас {now:%H:%M}, {now:%Y-%m-%d}."
        return f"Yesterday was {yesterday}. Local time is {now:%H:%M}, {now:%A}, {now:%Y-%m-%d}."
    if is_ru:
        return f"Сейчас {now:%H:%M}, {now:%Y-%m-%d}."
    return f"Local time: {now:%H:%M}, {now:%A}, {now:%Y-%m-%d}."