"""Build the built-in skill registry."""

from __future__ import annotations

from assistuff.config.schemas import SkillManifest
from assistuff.skills.registry import SkillRegistry

from . import (
    calculator,
    capabilities,
    date_math,
    percentage,
    recall,
    remember,
    text_utility,
    time as time_skill,
    todo,
    unit_convert,
    weather,
    web_search,
)


def register_builtins(registry: SkillRegistry, manifests: dict[str, SkillManifest]) -> None:
    entries = [
        ("calculator", calculator.run, "calculator"),
        ("unit_convert", unit_convert.run, "unit_convert"),
        ("date_math", date_math.run, "date_math"),
        ("percentage", percentage.run, "percentage"),
        ("time", time_skill.run, "time"),
        ("weather", weather.run, "weather"),
        ("web_search", web_search.run, "web_search"),
        ("todo_add", todo.add, "todo_add"),
        ("todo_list", todo.list_todos, "todo_list"),
        ("todo_complete", todo.complete, "todo_complete"),
        ("remember", remember.run, "remember"),
        ("recall", recall.run, "recall"),
        ("capabilities", capabilities.run, "capabilities"),
        ("summarize", text_utility.summarize, "summarize"),
        ("rewrite", text_utility.rewrite, "rewrite"),
        ("extract_action_items", text_utility.extract_action_items, "extract_action_items"),
    ]
    for name, handler, manifest_id in entries:
        manifest = manifests.get(manifest_id)
        permission = manifest.access.pupc_action if manifest and manifest.access else None
        description = ", ".join(manifest.capabilities.provides) if manifest else ""
        registry.register(name, handler, permission=permission, description=description)