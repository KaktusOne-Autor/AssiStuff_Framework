"""Skill: what can the assistant do."""

from __future__ import annotations

import re

from assistuff.skills.registry import SkillContext

_DESCRIPTIONS: dict[str, tuple[str, str]] = {
    "calculator": ("evaluate arithmetic", "выполнять арифметику"),
    "unit_convert": ("convert units", "конвертировать единицы"),
    "date_math": ("date arithmetic", "вычислять даты"),
    "percentage": ("percentages", "вычислять проценты"),
    "time": ("report current time", "сообщать время"),
    "weather": ("look up weather", "узнавать погоду"),
    "web_search": ("search the web", "искать в интернете"),
    "todo_add": ("add to-dos", "добавлять дела"),
    "todo_list": ("list to-dos", "показывать дела"),
    "todo_complete": ("complete to-dos", "отмечать дела выполненными"),
    "remember": ("save durable notes", "сохранять заметки"),
    "recall": ("search long-term memory", "искать в долгосрочной памяти"),
    "capabilities": ("describe capabilities", "описывать возможности"),
}


def run(value: str, context: SkillContext) -> str:
    is_ru = bool(re.search(r"[а-яё]", value, re.IGNORECASE))
    names = [n for n in _DESCRIPTIONS if n != "capabilities"]
    if is_ru:
        lines = [f"- {_DESCRIPTIONS[n][1]}" for n in names]
        return "Сейчас я умею:\n" + "\n".join(lines)
    lines = [f"- {_DESCRIPTIONS[n][0]}" for n in names]
    return "I can currently:\n" + "\n".join(lines)