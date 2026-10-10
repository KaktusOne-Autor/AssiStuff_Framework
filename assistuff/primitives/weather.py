"""Weather primitive (async, wttr.in)."""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import quote

import httpx

logger = logging.getLogger(__name__)


async def fetch_weather(city: str = "Moscow", *, timeout: float = 8.0) -> dict[str, Any]:
    url = f"https://wttr.in/{quote(city)}?format=j1"
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(url)
            response.raise_for_status()
            payload = response.json()
    except Exception as exc:
        logger.warning("weather lookup failed for %s: %s", city, exc)
        return {
            "city": city,
            "condition": "offline",
            "temperature_c": None,
            "summary": f"Погода в {city}: данные недоступны.",
        }

    current = payload.get("current_condition", [{}])[0]
    temp_c = current.get("temp_C")
    desc_list = current.get("weatherDesc") or [{}]
    desc = desc_list[0].get("value", "неизвестно")
    temperature = int(temp_c) if temp_c is not None else None
    return {
        "city": city,
        "condition": desc,
        "temperature_c": temperature,
        "summary": f"Погода в {city}: {desc}, {temperature}°C."
        if temperature is not None else f"Погода в {city}: {desc}.",
    }