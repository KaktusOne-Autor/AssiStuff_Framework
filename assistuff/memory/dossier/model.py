"""Dossier — structured user profile."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class Dossier:
    profile: str
    version: int = 1
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds"))
    identity: list[str] = field(default_factory=list)
    preferences: list[str] = field(default_factory=list)
    projects: list[str] = field(default_factory=list)
    recent_topics: list[str] = field(default_factory=list)
    patterns: list[str] = field(default_factory=list)
    relationships: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_markdown(self) -> str:
        lines = [
            "---",
            f"profile: {self.profile}",
            f"version: {self.version}",
            f"updated_at: {self.updated_at}",
            "---",
            "",
            f"# Dossier: {self.profile}",
            "",
        ]
        for name in ("identity", "preferences", "projects", "recent_topics",
                     "patterns", "relationships", "notes"):
            items = getattr(self, name)
            lines.append(f"## {name.replace('_', ' ').title()}")
            if items:
                lines.extend(f"- {item}" for item in items)
            else:
                lines.append("- (none yet)")
            lines.append("")
        return "\n".join(lines)

    @classmethod
    def from_markdown(cls, text: str, profile: str) -> "Dossier":
        dossier = cls(profile=profile)
        section: str | None = None
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("## "):
                section = stripped[3:].strip().lower().replace(" ", "_")
                continue
            if stripped.startswith("- "):
                item = stripped[2:].strip()
                if item and item != "(none yet)" and section and hasattr(dossier, section):
                    getattr(dossier, section).append(item)
            if stripped.startswith("version:"):
                try:
                    dossier.version = int(stripped.split(":", 1)[1].strip())
                except ValueError:
                    pass
            elif stripped.startswith("updated_at:"):
                dossier.updated_at = stripped.split(":", 1)[1].strip()
        return dossier

    def section(self, name: str) -> list[str]:
        if not hasattr(self, name):
            return []
        return list(getattr(self, name))