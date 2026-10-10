"""Profile manager — per-user isolated storage."""

from __future__ import annotations

import re
from pathlib import Path

from assistuff.config.paths import get_user_root

_PROFILE_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")


class ProfileManager:
    def __init__(
        self,
        storage_dir: str | Path = "~/.assistuff/profiles",
        default_profile: str = "default",
    ) -> None:
        configured = Path(storage_dir).expanduser()
        if not configured.is_absolute():
            configured = get_user_root() / configured
        self.storage_dir = configured
        self.default_profile = self.validate_id(default_profile)
        self.active_file = self.storage_dir / ".active_profile"
        self.create(self.default_profile)

    @staticmethod
    def validate_id(profile_id: str) -> str:
        normalized = profile_id.strip().casefold()
        if not _PROFILE_ID.fullmatch(normalized):
            raise ValueError(
                "Profile IDs must be 1-32 lowercase ASCII letters, digits, "
                "underscores, or hyphens, and start with a letter or digit."
            )
        return normalized

    def profile_dir(self, profile_id: str) -> Path:
        return self.storage_dir / self.validate_id(profile_id)

    def create(self, profile_id: str) -> str:
        normalized = self.validate_id(profile_id)
        self.profile_dir(normalized).mkdir(parents=True, exist_ok=True)
        return normalized

    def list_profiles(self) -> list[str]:
        if not self.storage_dir.is_dir():
            return [self.default_profile]
        found = [
            item.name
            for item in self.storage_dir.iterdir()
            if item.is_dir() and _PROFILE_ID.fullmatch(item.name)
        ]
        return sorted(set(found) | {self.default_profile})

    def get_active(self) -> str:
        if not self.active_file.exists():
            return self.default_profile
        active = self.validate_id(self.active_file.read_text(encoding="utf-8"))
        if active not in self.list_profiles():
            raise ValueError(f"Active profile does not exist: {active}")
        return active

    def set_active(self, profile_id: str) -> str:
        normalized = self.validate_id(profile_id)
        if normalized not in self.list_profiles():
            raise ValueError(f"Profile does not exist: {normalized}")
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        tmp = self.active_file.with_suffix(".tmp")
        tmp.write_text(normalized, encoding="utf-8")
        tmp.replace(self.active_file)
        return normalized