"""Percentage calculations."""

from __future__ import annotations

import re

_PERCENT_OF_RE = re.compile(
    r"(-?\d+(?:[.,]\d+)?)\s*(?:%|percent|процент\w*)\s*(?:of|от)\s*(-?\d+(?:[.,]\d+)?)",
    re.IGNORECASE,
)
_WHAT_PERCENT_RE = re.compile(
    r"(?:what percent(?:age)?(?: is)?|какой процент(?: составляет)?|"
    r"сколько процентов)\s+(-?\d+(?:[.,]\d+)?)\s+(?:of|от)\s+(-?\d+(?:[.,]\d+)?)",
    re.IGNORECASE,
)
_CHANGE_RE = re.compile(
    r"(?:percentage change|процентное изменение)\s+"
    r"(?:from|с)\s*(-?\d+(?:[.,]\d+)?)\s+(?:to|до)\s*(-?\d+(?:[.,]\d+)?)",
    re.IGNORECASE,
)


class PercentError(ValueError):
    pass


def percent_of(text: str) -> str | None:
    m = _PERCENT_OF_RE.search(text)
    if not m:
        return None
    percent = float(m.group(1).replace(",", "."))
    total = float(m.group(2).replace(",", "."))
    result = percent * total / 100
    is_ru = bool(re.search(r"[а-яё]", text, re.IGNORECASE))
    if is_ru:
        return f"{percent:g}% от {total:g} = {result:g}"
    return f"{percent:g}% of {total:g} = {result:g}"


def what_percent(text: str) -> str | None:
    m = _WHAT_PERCENT_RE.search(text)
    if not m:
        return None
    part = float(m.group(1).replace(",", "."))
    total = float(m.group(2).replace(",", "."))
    if total == 0:
        raise PercentError("cannot compute percentage of zero")
    result = part / total * 100
    is_ru = bool(re.search(r"[а-яё]", text, re.IGNORECASE))
    if is_ru:
        return f"{part:g} — это {result:g}% от {total:g}"
    return f"{part:g} is {result:g}% of {total:g}"


def percent_change(text: str) -> str | None:
    m = _CHANGE_RE.search(text)
    if not m:
        return None
    start = float(m.group(1).replace(",", "."))
    end = float(m.group(2).replace(",", "."))
    if start == 0:
        raise PercentError("percentage change from zero is undefined")
    change = (end - start) / abs(start) * 100
    is_ru = bool(re.search(r"[а-яё]", text, re.IGNORECASE))
    if is_ru:
        return f"Процентное изменение: {change:+g}%"
    return f"Percentage change: {change:+g}%"


def evaluate(text: str) -> str:
    for fn in (percent_of, what_percent, percent_change):
        result = fn(text)
        if result is not None:
            return result
    raise PercentError(
        'use e.g. "15% of 200", "what percent is 30 of 200", '
        'or "percentage change from 100 to 120"'
    )