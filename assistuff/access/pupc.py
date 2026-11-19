"""PUPC — access control checks."""

from __future__ import annotations

import logging

from assistuff.config.schemas import AccessConfig, PupcConfig

from .user import User

logger = logging.getLogger(__name__)


class AccessDenied(PermissionError):
    pass


class Pupc:
    def __init__(self, config: AccessConfig, pupc: PupcConfig) -> None:
        self.config = config
        self.pupc = pupc

    def level_for_profile(self, profile: str) -> int:
        if profile in self.config.profile_levels:
            return self.config.profile_levels[profile]
        return self.config.default_level

    def user_for_profile(self, profile: str) -> User:
        logger.debug("profile %s has no authenticated account; using guest access", profile)
        return User(level=0, name="guest")

    def check(self, user: User, required_level: int, *, action: str = "") -> bool:
        if user.level >= required_level:
            return True
        if self.config.log_all_denials:
            logger.warning(
                "[PUPC] denied user=%s level=%d required=%d action=%s",
                user.name,
                user.level,
                required_level,
                action or "?",
            )
        return False

    def enforce(self, user: User, required_level: int, *, action: str = "") -> None:
        if not self.check(user, required_level, action=action):
            raise AccessDenied(
                f"Access denied: {user.name} (level {user.level}) "
                f"for action {action or '?'} (requires {required_level})"
            )

    def level_name(self, level: int) -> str:
        entry = self.pupc.levels.get(level)
        return entry.id if entry else f"level-{level}"