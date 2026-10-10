"""Skill: weather (async primitive, run via asyncio)."""

from __future__ import annotations

import asyncio
import re

from assistuff.primitives import weather as weather_prim
from assistuff.skills.registry import SkillContext

_CITY_RE = re.compile(
    r"\b(?:in|for|в|для)\s+([\wА-Яа-яЁё-]+(?:\s+[\wА-Яа-яЁё-]+){0,2})",
    re.IGNORECASE,
)


def run(value: str, _ctx: SkillContext) -> str:
    match = _CITY_RE.search(value)
    city = match.group(1).strip(" ?!.,") if match else "Moscow"
    try:
        data = asyncio.run(weather_prim.fetch_weather(city))
    except RuntimeError:
        # already inside an event loop
        loop = asyncio.get_event_loop()
        data = loop.run_until_complete(weather_prim.fetch_weather(city))
    return str(data["summary"])