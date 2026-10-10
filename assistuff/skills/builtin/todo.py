"""Skill: to-do list management."""

from __future__ import annotations

import re

from assistuff.skills.registry import SkillContext

_ADD_PREFIX_RE = re.compile(
    r"^\s*(?:add|create|добавь|создай|запиши)\s+"
    r"(?:(?:a|the)\s+)?"
    r"(?:(?:to\s+my\s+)?(?:to-do|todo)\s+list|"
    r"(?:to-do|todo|task|задачу|дело|задача)\s*)*"
    r"(?:в\s+список\s+дел\s*)*[:,-]?\s*",
    re.IGNORECASE,
)


def add(value: str, context: SkillContext) -> str:
    task = _ADD_PREFIX_RE.sub("", value).strip()
    if not task:
        raise ValueError("provide to-do text")
    todo_id = context.memory.short_term.add_todo(task)
    is_ru = bool(re.search(r"[а-яё]", value, re.IGNORECASE))
    return f"Добавлено в список дел #{todo_id}: {task}" if is_ru else f"Added to-do #{todo_id}: {task}"


def list_todos(value: str, context: SkillContext) -> str:
    todos = context.memory.short_term.list_todos()
    is_ru = bool(re.search(r"[а-яё]", value, re.IGNORECASE))
    if not todos:
        return "Список дел пуст." if is_ru else "Your to-do list is empty."
    lines = [f"- #{tid} {content}" for tid, content, _ in todos]
    return ("Список дел:\n" if is_ru else "") + "\n".join(lines)


def complete(value: str, context: SkillContext) -> str:
    match = re.search(r"#?(\d+)\b", value)
    if not match:
        raise ValueError('specify the to-do ID, e.g. "complete task #3"')
    todo_id = int(match.group(1))
    content, changed = context.memory.short_term.complete_todo(todo_id)
    is_ru = bool(re.search(r"[а-яё]", value, re.IGNORECASE))
    if is_ru:
        if changed:
            return f"Выполнено дело #{todo_id}: {content}"
        return f"Дело #{todo_id} уже выполнено: {content}"
    if changed:
        return f"Completed to-do #{todo_id}: {content}"
    return f"To-do #{todo_id} was already complete: {content}"