"""Dossier slicer — loads relevant sections within a token budget."""

from __future__ import annotations

import re

from assistuff.config.schemas import DossierConfig

from .model import Dossier

_KEYWORD_TRIGGERS = {
    "projects": re.compile(r"\b(?:project|проект|работа|work)\w*", re.I),
    "recent_topics": re.compile(r"\b(?:yesterday|today|recent|вчера|сегодня|недавно|говорил)\w*", re.I),
    "patterns": re.compile(r"\b(?:habit|pattern|usually|always|привычк|обычно|всегда)\w*", re.I),
    "relationships": re.compile(r"\b(?:people|person|friend|colleague|люди|человек|коллег|друг)\w*", re.I),
}

# Rough estimate: ~4 chars per token for multilingual text
_CHARS_PER_TOKEN = 4


class DossierSlicer:
    def __init__(self, config: DossierConfig) -> None:
        self.config = config

    def slice(self, dossier: Dossier, query: str) -> str:
        sections: list[tuple[str, list[str]]] = []

        for name, mode in self._section_modes().items():
            if mode == "never":
                continue
            if mode == "always":
                sections.append((name, dossier.section(name)))
                continue
            if self._matches(name, query):
                sections.append((name, dossier.section(name)))

        budget = self.config.max_slice_tokens * _CHARS_PER_TOKEN
        output: list[str] = []
        used = 0
        for name, items in sections:
            header = f"## {name.replace('_', ' ').title()}"
            block_lines = [header]
            if items:
                block_lines.extend(f"- {item}" for item in items)
            else:
                block_lines.append("- (none yet)")
            block = "\n".join(block_lines)
            if used + len(block) > budget:
                break
            output.append(block)
            used += len(block)
        return "\n\n".join(output)

    def _section_modes(self) -> dict[str, str]:
        s = self.config.sections
        return {
            "identity": s.identity,
            "preferences": s.preferences,
            "projects": s.projects,
            "recent_topics": s.recent_topics,
            "patterns": s.patterns,
            "relationships": s.relationships,
        }

    def _matches(self, section: str, query: str) -> bool:
        pattern = _KEYWORD_TRIGGERS.get(section)
        if pattern is None:
            return False
        return bool(pattern.search(query))