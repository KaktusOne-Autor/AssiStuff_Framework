"""Unit conversion."""

from __future__ import annotations

import math
import re

_UNIT_ALIASES: dict[str, tuple[str, float, str]] = {
    # length
    "m": ("length", 1.0, "m"),
    "meter": ("length", 1.0, "m"),
    "meters": ("length", 1.0, "m"),
    "metre": ("length", 1.0, "m"),
    "metres": ("length", 1.0, "m"),
    "метр": ("length", 1.0, "м"),
    "метра": ("length", 1.0, "м"),
    "метров": ("length", 1.0, "м"),
    "km": ("length", 1000.0, "km"),
    "kilometer": ("length", 1000.0, "km"),
    "kilometers": ("length", 1000.0, "km"),
    "kilometre": ("length", 1000.0, "km"),
    "kilometres": ("length", 1000.0, "km"),
    "километр": ("length", 1000.0, "км"),
    "километра": ("length", 1000.0, "км"),
    "километров": ("length", 1000.0, "км"),
    "cm": ("length", 0.01, "cm"),
    "сантиметр": ("length", 0.01, "см"),
    "сантиметра": ("length", 0.01, "см"),
    "сантиметров": ("length", 0.01, "см"),
    "mm": ("length", 0.001, "mm"),
    "мм": ("length", 0.001, "мм"),
    "mile": ("length", 1609.344, "mi"),
    "miles": ("length", 1609.344, "mi"),
    "mi": ("length", 1609.344, "mi"),
    "миля": ("length", 1609.344, "мили"),
    "мили": ("length", 1609.344, "мили"),
    "миль": ("length", 1609.344, "мили"),
    "inch": ("length", 0.0254, "in"),
    "inches": ("length", 0.0254, "in"),
    "in": ("length", 0.0254, "in"),
    "ft": ("length", 0.3048, "ft"),
    "foot": ("length", 0.3048, "ft"),
    "feet": ("length", 0.3048, "ft"),
    "yard": ("length", 0.9144, "yd"),
    "yards": ("length", 0.9144, "yd"),
    "yd": ("length", 0.9144, "yd"),
    # mass
    "kg": ("mass", 1.0, "kg"),
    "килограмм": ("mass", 1.0, "кг"),
    "килограмма": ("mass", 1.0, "кг"),
    "килограммов": ("mass", 1.0, "кг"),
    "g": ("mass", 0.001, "g"),
    "gram": ("mass", 0.001, "g"),
    "grams": ("mass", 0.001, "g"),
    "грамм": ("mass", 0.001, "г"),
    "грамма": ("mass", 0.001, "г"),
    "граммов": ("mass", 0.001, "г"),
    "lb": ("mass", 0.45359237, "lb"),
    "lbs": ("mass", 0.45359237, "lb"),
    "pound": ("mass", 0.45359237, "lb"),
    "pounds": ("mass", 0.45359237, "lb"),
    "фунт": ("mass", 0.45359237, "фунт"),
    "фунта": ("mass", 0.45359237, "фунт"),
    "фунтов": ("mass", 0.45359237, "фунт"),
    "oz": ("mass", 0.028349523125, "oz"),
    "ounce": ("mass", 0.028349523125, "oz"),
    "ounces": ("mass", 0.028349523125, "oz"),
    # volume
    "l": ("volume", 1.0, "L"),
    "liter": ("volume", 1.0, "L"),
    "liters": ("volume", 1.0, "L"),
    "litre": ("volume", 1.0, "L"),
    "litres": ("volume", 1.0, "L"),
    "литр": ("volume", 1.0, "л"),
    "литра": ("volume", 1.0, "л"),
    "литров": ("volume", 1.0, "л"),
    "ml": ("volume", 0.001, "mL"),
    "миллилитр": ("volume", 0.001, "мл"),
    "миллилитра": ("volume", 0.001, "мл"),
    "миллилитров": ("volume", 0.001, "мл"),
    # temperature
    "c": ("temperature", 1.0, "C"),
    "°c": ("temperature", 1.0, "C"),
    "celsius": ("temperature", 1.0, "C"),
    "цельсия": ("temperature", 1.0, "C"),
    "f": ("temperature", 1.0, "F"),
    "°f": ("temperature", 1.0, "F"),
    "fahrenheit": ("temperature", 1.0, "F"),
    "фаренгейт": ("temperature", 1.0, "F"),
    "фаренгейта": ("temperature", 1.0, "F"),
    "k": ("temperature", 1.0, "K"),
    "kelvin": ("temperature", 1.0, "K"),
    "кельвин": ("temperature", 1.0, "K"),
    "кельвинов": ("temperature", 1.0, "K"),
    # time
    "s": ("time", 1.0, "s"),
    "sec": ("time", 1.0, "s"),
    "second": ("time", 1.0, "s"),
    "seconds": ("time", 1.0, "s"),
    "секунда": ("time", 1.0, "с"),
    "секунды": ("time", 1.0, "с"),
    "секунд": ("time", 1.0, "с"),
    "min": ("time", 60.0, "min"),
    "minute": ("time", 60.0, "min"),
    "minutes": ("time", 60.0, "min"),
    "минута": ("time", 60.0, "мин"),
    "минуты": ("time", 60.0, "мин"),
    "минут": ("time", 60.0, "мин"),
    "h": ("time", 3600.0, "h"),
    "hr": ("time", 3600.0, "h"),
    "hour": ("time", 3600.0, "h"),
    "hours": ("time", 3600.0, "h"),
    "час": ("time", 3600.0, "ч"),
    "часа": ("time", 3600.0, "ч"),
    "часов": ("time", 3600.0, "ч"),
    "day": ("time", 86400.0, "day"),
    "days": ("time", 86400.0, "day"),
    "день": ("time", 86400.0, "дн"),
    "дня": ("time", 86400.0, "дн"),
    "дней": ("time", 86400.0, "дн"),
}

_CONVERT_RE = re.compile(
    r"(-?\d+(?:[.,]\d+)?)\s*([A-Za-zА-Яа-яЁё°]+)\s+"
    r"(?:to|in|в)\s+([A-Za-zА-Яа-яЁё°]+)",
    re.IGNORECASE,
)


class UnitError(ValueError):
    pass


def parse_conversion(text: str) -> tuple[float, str, str]:
    cleaned = re.sub(
        r"^\s*(?:convert|переведи|конвертируй)\s+",
        "",
        text.strip(),
        flags=re.IGNORECASE,
    )
    match = _CONVERT_RE.search(cleaned)
    if not match:
        raise UnitError('use a conversion such as "5 km to miles" or "20 C to F"')
    number = float(match.group(1).replace(",", "."))
    source = match.group(2).casefold().lstrip("°")
    target = match.group(3).casefold().lstrip("°")
    return number, source, target


def convert(number: float, source: str, target: str) -> tuple[float, str, str]:
    src = _UNIT_ALIASES.get(source) or _UNIT_ALIASES.get(f"°{source}")
    dst = _UNIT_ALIASES.get(target) or _UNIT_ALIASES.get(f"°{target}")
    if src is None or dst is None:
        raise UnitError("unsupported unit")
    if src[0] != dst[0]:
        raise UnitError("incompatible units")

    dimension = src[0]
    if dimension == "temperature":
        result = _convert_temperature(number, src[2], dst[2])
    else:
        result = number * src[1] / dst[1]
    if not math.isfinite(result):
        raise UnitError("result is not finite")
    return result, src[2], dst[2]


def _convert_temperature(value: float, src: str, dst: str) -> float:
    if src == dst:
        return value
    # to Celsius
    if src == "C":
        c = value
    elif src == "F":
        c = (value - 32) * 5 / 9
    elif src == "K":
        c = value - 273.15
    else:
        raise UnitError("unknown temperature unit")
    # from Celsius
    if dst == "C":
        return c
    if dst == "F":
        return c * 9 / 5 + 32
    if dst == "K":
        return c + 273.15
    raise UnitError("unknown temperature unit")