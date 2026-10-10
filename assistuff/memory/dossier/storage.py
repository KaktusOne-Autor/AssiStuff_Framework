"""Dossier storage: read/write with versioned history."""

from __future__ import annotations

import shutil
from datetime import datetime, timezone
from pathlib import Path

from .model import Dossier


class DossierStorage:
    def __init__(self, profile_dir: Path) -> None:
        self.profile_dir = Path(profile_dir)
        self.profile_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.profile_dir / "dossier.md"
        self.history_dir = self.profile_dir / "dossier.history"

    def load(self, profile: str) -> Dossier:
        if not self.path.is_file():
            return Dossier(profile=profile)
        text = self.path.read_text(encoding="utf-8")
        return Dossier.from_markdown(text, profile=profile)

    def save(self, dossier: Dossier, *, keep_history: int = 10) -> None:
        if self.path.is_file():
            self.history_dir.mkdir(parents=True, exist_ok=True)
            ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
            shutil.copy2(self.path, self.history_dir / f"v{dossier.version}-{ts}.md")
            self._prune_history(keep_history)
        dossier.version += 1
        dossier.updated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        self.path.write_text(dossier.to_markdown(), encoding="utf-8")

    def _prune_history(self, keep: int) -> None:
        if not self.history_dir.is_dir() or keep <= 0:
            return
        files = sorted(self.history_dir.glob("*.md"))
        for old in files[:-keep]:
            try:
                old.unlink()
            except OSError:
                pass