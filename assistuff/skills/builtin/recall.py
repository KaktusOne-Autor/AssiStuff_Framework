"""Skill: recall from memory (retrieval by time / tags / keywords)."""

from __future__ import annotations

from assistuff.skills.registry import SkillContext


def run(value: str, context: SkillContext) -> str:
    hits = context.memory.retriever.search(value)
    if not hits:
        return f"В памяти профиля {context.profile} ничего не найдено по запросу."

    lines = [
        f"[{h.timestamp}] {' '.join(h.tags)}: {h.text}"
        for h in hits[:10]
    ]
    return (
        f"Результаты поиска в долгосрочной памяти профиля {context.profile}:\n"
        + "\n".join(lines)
    )