"""Dossier Compiler — background process that builds the dossier."""

from __future__ import annotations

import json
import logging

from assistuff.config.schemas import DossierConfig
from assistuff.runtime.utility import UtilityRoles

from ..long_term import LongTermMemory
from ..short_term import ShortTermMemory
from .model import Dossier
from .storage import DossierStorage

logger = logging.getLogger(__name__)

_COMPILER_SCHEMA = {
    "type": "object",
    "properties": {
        "identity": {"type": "array", "items": {"type": "string"}},
        "preferences": {"type": "array", "items": {"type": "string"}},
        "projects": {"type": "array", "items": {"type": "string"}},
        "recent_topics": {"type": "array", "items": {"type": "string"}},
        "patterns": {"type": "array", "items": {"type": "string"}},
        "relationships": {"type": "array", "items": {"type": "string"}},
        "notes": {"type": "array", "items": {"type": "string"}},
    },
}


class DossierCompiler:
    def __init__(
        self,
        config: DossierConfig,
        roles: UtilityRoles,
        short_term: ShortTermMemory,
        long_term: LongTermMemory,
        storage: DossierStorage,
        profile: str,
    ) -> None:
        self.config = config
        self.roles = roles
        self.short_term = short_term
        self.long_term = long_term
        self.storage = storage
        self.profile = profile
        self._counter = 0

    def maybe_compile(self) -> Dossier | None:
        self._counter += 1
        if self._counter % self.config.compile_every != 0:
            return None
        try:
            return self.compile()
        except Exception:
            logger.exception("dossier compilation failed")
            return None

    def compile(self) -> Dossier:
        current = self.storage.load(self.profile)
        recent = self.short_term.recent_messages(limit=40)
        notes = self._select_notes(current)

        prompt = self._build_prompt(current, recent, notes)
        try:
            data = self.roles.generate_json(
                self.config.compile_model,
                prompt,
                schema=_COMPILER_SCHEMA,
            )
        except Exception as exc:
            logger.warning("dossier compiler model failed: %s", exc)
            return current

        updated = self._merge(current, data)
        self.storage.save(updated)
        logger.info("dossier compiled for profile=%s version=%d", self.profile, updated.version)
        return updated

    def _select_notes(self, dossier: Dossier) -> list[str]:
        seen: list[str] = []
        for tag in self.long_term.tags.all()[:10]:
            hits = self.long_term.search(
                __import__("assistuff.memory.long_term", fromlist=["MemoryQuery"]).MemoryQuery(
                    keywords=[], tags=[tag], time_range=None, semantic=None, limit=5,
                )
            )
            for h in hits:
                line = f"{h.timestamp} {' '.join(h.tags)}: {h.text}"
                if line not in seen:
                    seen.append(line)
        return seen[:60]

    def _build_prompt(
        self,
        dossier: Dossier,
        recent: list[tuple[str, str]],
        notes: list[str],
    ) -> str:
        convo = "\n".join(f"{role}: {content}" for role, content in recent)
        notes_block = "\n".join(notes) if notes else "(none)"
        current_block = dossier.to_markdown()
        return (
            "You are building a structured dossier about the user.\n"
            "Use only facts present in the conversation and notes below.\n"
            "Do not invent. Preserve the user's language.\n"
            "Return JSON with keys: identity, preferences, projects, "
            "recent_topics, patterns, relationships, notes. "
            "Each value is a list of short strings (1 sentence, ≤120 chars).\n\n"
            f"<current_dossier>\n{current_block}\n</current_dossier>\n\n"
            f"<recent_conversation>\n{convo or '(empty)'}\n</recent_conversation>\n\n"
            f"<notes>\n{notes_block}\n</notes>\n\n"
            "Merge: keep existing items that are still relevant, add new ones, "
            "drop outdated. Return only JSON."
        )

    def _merge(self, dossier: Dossier, data: dict) -> Dossier:
        for key in ("identity", "preferences", "projects", "recent_topics",
                    "patterns", "relationships", "notes"):
            value = data.get(key)
            if isinstance(value, list):
                cleaned = [str(v).strip() for v in value if isinstance(v, str) and v.strip()]
                setattr(dossier, key, cleaned[:30])
        return dossier