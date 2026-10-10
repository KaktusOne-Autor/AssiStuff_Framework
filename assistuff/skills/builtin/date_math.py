"""Skill: date arithmetic."""

from __future__ import annotations

import re

from assistuff.primitives import time_ops
from assistuff.skills.registry import SkillContext

_BETWEEN_RE = re.compile(r"\bbetween\b|\bмежду\b", re.IGNORECASE)
_SHIFT_RE = re.compile(
    r"(\d{4}-\d{2}-\d{2})\s*([+-])\s*(\d+)\s*(?:days?|дн\w*)",
    re.IGNORECASE,
)


def run(value: str, _ctx: SkillContext) -> str:
    text = value.casefold()
    dates = time_ops.find_iso_dates(text)

    if len(dates) >= 2 and _BETWEEN_RE.search(text):
        days = time_ops.days_between(dates[0], dates[1])
        is_ru = bool(re.search(r"[а-яё]", text))
        return f"{days} дней" if is_ru else f"{days} days"

    shift = _SHIFT_RE.search(text)
    if shift:
        start = time_ops.parse_iso_date(shift.group(1))
        delta = int(shift.group(3)) * (1 if shift.group(2) == "+" else -1)
        return time_ops.shift_days(start, delta).isoformat()

    raise ValueError(
        'use ISO dates, e.g. "days between 2026-01-01 and 2026-01-10" '
        'or "2026-01-01 + 10 days"'
    )