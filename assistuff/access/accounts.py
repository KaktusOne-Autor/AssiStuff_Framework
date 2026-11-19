"""Local account registry and password authentication."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
import hashlib
import hmac
import logging
import secrets
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from .user import User

logger = logging.getLogger(__name__)

_PASSWORD_ITERATIONS = 310_000
_MIN_PASSWORD_LENGTH = 12


class AccountError(RuntimeError):
    """Account operation failed or was not authorized."""


@dataclass(frozen=True)
class AccountSession:
    user: User
    profile: str


@dataclass(frozen=True)
class AccountSummary:
    account_id: str
    username: str
    display_name: str
    level: int
    profiles: tuple[str, ...]
    enabled: bool


class AccountRegistry:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).expanduser()
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        existed = self.path.exists()
        with self._connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS accounts (
                    id TEXT PRIMARY KEY,
                    username TEXT NOT NULL UNIQUE COLLATE NOCASE,
                    display_name TEXT NOT NULL,
                    password_salt BLOB NOT NULL,
                    password_hash BLOB NOT NULL,
                    level INTEGER NOT NULL CHECK(level BETWEEN 0 AND 5),
                    enabled INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS account_profiles (
                    account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
                    profile_id TEXT NOT NULL UNIQUE,
                    PRIMARY KEY (account_id, profile_id)
                );
                CREATE TABLE IF NOT EXISTS account_audit (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    occurred_at TEXT NOT NULL,
                    account_id TEXT,
                    actor_id TEXT,
                    event TEXT NOT NULL
                );
                """
            )
        if not existed:
            self.path.chmod(0o600)

    @contextmanager
    def _connect(self) -> Generator[sqlite3.Connection, None, None]:
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    def has_accounts(self) -> bool:
        with self._connect() as db:
            return db.execute("SELECT 1 FROM accounts LIMIT 1").fetchone() is not None

    def create_account(
        self,
        username: str,
        password: str,
        *,
        profile: str,
        display_name: str | None = None,
        level: int = 0,
        actor: User | None = None,
    ) -> AccountSummary:
        username = username.strip()
        profile = _validate_profile(profile)
        if profile == "guest":
            raise ValueError("'guest' is a reserved profile")
        if not username or len(username) > 128:
            raise ValueError("username must contain 1-128 characters")
        if len(password) < _MIN_PASSWORD_LENGTH:
            raise ValueError(
                f"password must contain at least {_MIN_PASSWORD_LENGTH} characters"
            )

        with self._connect() as db:
            existing = db.execute("SELECT COUNT(*) AS n FROM accounts").fetchone()["n"]
            if existing:
                actor_level = _require_admin(db, actor)
                if not 0 <= level <= actor_level:
                    raise AccountError("requested access level exceeds administrator level")
            else:
                if actor is not None:
                    raise AccountError("first account is bootstrapped by the local operator")
                level = 5

            account_id = str(uuid.uuid4())
            salt = secrets.token_bytes(32)
            password_hash = _hash_password(password, salt)
            try:
                db.execute(
                    """
                    INSERT INTO accounts (
                        id, username, display_name, password_salt, password_hash,
                        level, enabled, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, 1, ?)
                    """,
                    (
                        account_id,
                        username,
                        display_name.strip() if display_name else username,
                        salt,
                        password_hash,
                        level,
                        _now(),
                    ),
                )
                db.execute(
                    "INSERT INTO account_profiles(account_id, profile_id) VALUES (?, ?)",
                    (account_id, profile),
                )
                self._audit(db, account_id, actor, "account_created")
            except sqlite3.IntegrityError as exc:
                raise AccountError(
                    "username already exists or profile is assigned to another account"
                ) from exc

        logger.info("created account %s at PUPC level %d", username, level)
        return AccountSummary(
            account_id=account_id,
            username=username,
            display_name=display_name.strip() if display_name else username,
            level=level,
            profiles=(profile,),
            enabled=True,
        )

    def authenticate(
        self,
        username: str,
        password: str,
        *,
        profile: str | None = None,
    ) -> AccountSession:
        with self._connect() as db:
            row = db.execute(
                """
                SELECT id, username, display_name, password_salt, password_hash,
                       level, enabled
                FROM accounts WHERE username = ? COLLATE NOCASE
                """,
                (username.strip(),),
            ).fetchone()
            if row is None or not row["enabled"]:
                raise AccountError("invalid account credentials")
            actual = _hash_password(password, row["password_salt"])
            if not hmac.compare_digest(actual, row["password_hash"]):
                raise AccountError("invalid account credentials")
            profiles = tuple(
                item["profile_id"]
                for item in db.execute(
                    "SELECT profile_id FROM account_profiles "
                    "WHERE account_id = ? ORDER BY profile_id",
                    (row["id"],),
                )
            )
            if not profiles:
                raise AccountError("account has no assigned profile")
            selected = _validate_profile(profile) if profile else profiles[0]
            if selected not in profiles:
                raise AccountError("profile is not assigned to this account")
            user = User(
                level=row["level"],
                name=row["display_name"],
                account_id=row["id"],
                authenticated=True,
            )
            self._audit(db, row["id"], user, "account_authenticated")
            return AccountSession(user=user, profile=selected)

    def list_accounts(self, actor: User) -> list[AccountSummary]:
        with self._connect() as db:
            _require_admin(db, actor)
            rows = db.execute(
                "SELECT id, username, display_name, level, enabled "
                "FROM accounts ORDER BY username"
            ).fetchall()
            return [
                AccountSummary(
                    account_id=row["id"],
                    username=row["username"],
                    display_name=row["display_name"],
                    level=row["level"],
                    profiles=tuple(
                        item["profile_id"]
                        for item in db.execute(
                            "SELECT profile_id FROM account_profiles "
                            "WHERE account_id = ? ORDER BY profile_id",
                            (row["id"],),
                        )
                    ),
                    enabled=bool(row["enabled"]),
                )
                for row in rows
            ]

    def resolve_session(self, user: User, profile: str) -> User:
        if not user.authenticated or user.account_id is None:
            return User()
        profile = _validate_profile(profile)
        with self._connect() as db:
            row = db.execute(
                """
                SELECT a.username, a.display_name, a.level
                FROM accounts a
                JOIN account_profiles p ON p.account_id = a.id
                WHERE a.id = ? AND a.enabled = 1 AND p.profile_id = ?
                """,
                (user.account_id, profile),
            ).fetchone()
        if row is None:
            raise AccountError("account session is disabled or no longer owns this profile")
        return User(
            level=row["level"],
            name=row["display_name"],
            account_id=user.account_id,
            authenticated=True,
        )

    def set_level(self, account_id: str, level: int, *, actor: User) -> None:
        if actor.account_id == account_id and level < 5:
            raise AccountError("cannot lower the active administrator's own level")
        with self._connect() as db:
            actor_level = _require_admin(db, actor)
            if not 0 <= level <= actor_level:
                raise AccountError("requested access level exceeds administrator level")
            target = db.execute(
                "SELECT level, enabled FROM accounts WHERE id = ?",
                (account_id,),
            ).fetchone()
            if target is None:
                raise AccountError("unknown account")
            if target["enabled"] and target["level"] == 5 and level < 5:
                admins = db.execute(
                    "SELECT COUNT(*) AS n FROM accounts WHERE enabled = 1 AND level = 5"
                ).fetchone()["n"]
                if admins <= 1:
                    raise AccountError("cannot demote the last enabled administrator")
            db.execute("UPDATE accounts SET level = ? WHERE id = ?", (level, account_id))
            self._audit(db, account_id, actor, "access_level_changed")

    def disable_account(self, account_id: str, *, actor: User) -> None:
        if actor.account_id == account_id:
            raise AccountError("cannot disable the active administrator account")
        with self._connect() as db:
            _require_admin(db, actor)
            target = db.execute(
                "SELECT level, enabled FROM accounts WHERE id = ?",
                (account_id,),
            ).fetchone()
            if target is None:
                raise AccountError("unknown account")
            if target["enabled"] and target["level"] == 5:
                admins = db.execute(
                    "SELECT COUNT(*) AS n FROM accounts WHERE enabled = 1 AND level = 5"
                ).fetchone()["n"]
                if admins <= 1:
                    raise AccountError("cannot disable the last enabled administrator")
            db.execute("UPDATE accounts SET enabled = 0 WHERE id = ?", (account_id,))
            self._audit(db, account_id, actor, "account_disabled")

    @staticmethod
    def _audit(
        db: sqlite3.Connection,
        account_id: str | None,
        actor: User | None,
        event: str,
    ) -> None:
        db.execute(
            "INSERT INTO account_audit(occurred_at, account_id, actor_id, event) "
            "VALUES (?, ?, ?, ?)",
            (_now(), account_id, actor.account_id if actor else None, event),
        )


def _require_admin(db: sqlite3.Connection, actor: User | None) -> int:
    if actor is None or not actor.authenticated or actor.account_id is None:
        raise AccountError("an authenticated PUPC level-5 account is required")
    row = db.execute(
        "SELECT level, enabled FROM accounts WHERE id = ?",
        (actor.account_id,),
    ).fetchone()
    if row is None or not row["enabled"] or row["level"] < 5:
        raise AccountError("an authenticated PUPC level-5 account is required")
    return int(row["level"])


def _hash_password(password: str, salt: bytes) -> bytes:
    return hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        _PASSWORD_ITERATIONS,
        dklen=32,
    )


def _validate_profile(profile: str) -> str:
    from assistuff.memory.profiles import ProfileManager

    return ProfileManager.validate_id(profile)


def _now() -> str:
    return datetime.now(UTC).isoformat()
