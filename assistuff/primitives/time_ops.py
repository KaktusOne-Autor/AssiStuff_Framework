"""Date and time helpers."""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta

_ISO_DATE_RE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")


def now() -> datetime:
    return datetime.now().astimezone()


def today_iso() -> str:
    return now().date().isoformat()


def yesterday_iso() -> str:
    return (now().date() - timedelta(days=1)).isoformat()


def parse_iso_date(text: str) -> date:
    match = _ISO_DATE_RE.search(text)
    if not match:
        raise ValueError(f"no ISO date found in {text!r}")
    return date.fromisoformat(match.group(0))


def find_iso_dates(text: str) -> list[date]:
    return [date.fromisoformat(m.group(0)) for m in _ISO_DATE_RE.finditer(text)]


def days_between(a: date, b: date) -> int:
    return abs((b - a).days)


def shift_days(start: date, delta: int) -> date:
    return start + timedelta(days=delta)