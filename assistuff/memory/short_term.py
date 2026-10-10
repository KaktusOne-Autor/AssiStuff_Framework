"""Layer 2: short-term memory — SQLite conversation history."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from collections.abc import Generator
from pathlib import Path


class ShortTermMemory:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS messages ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "role TEXT NOT NULL, "
                "content TEXT NOT NULL, "
                "created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"
            )
            conn.execute(
                "CREATE TABLE IF NOT EXISTS todos ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "content TEXT NOT NULL, "
                "status TEXT NOT NULL DEFAULT 'open' "
                "CHECK (status IN ('open','done')), "
                "created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, "
                "completed_at TEXT)"
            )

    @contextmanager
    def _connect(self) -> Generator[sqlite3.Connection, None, None]:
        connection = sqlite3.connect(self.db_path)
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    # ------------------------------------------------------------------
    # Messages
    # ------------------------------------------------------------------

    def add_message(self, role: str, content: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO messages (role, content) VALUES (?, ?)",
                (role, content),
            )

    def recent_messages(self, limit: int = 20) -> list[tuple[str, str]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT role, content FROM messages ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return list(reversed(rows))

    def count_messages(self) -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) FROM messages").fetchone()
        return int(row[0]) if row else 0

    # ------------------------------------------------------------------
    # To-dos
    # ------------------------------------------------------------------

    def add_todo(self, content: str) -> int:
        task = content.strip()
        if not task:
            raise ValueError("To-do text must not be empty")
        if len(task) > 1000:
            raise ValueError("To-do text must not exceed 1000 characters")
        with self._connect() as conn:
            cursor = conn.execute("INSERT INTO todos (content) VALUES (?)", (task,))
            return int(cursor.lastrowid)

    def list_todos(self, *, include_done: bool = False) -> list[tuple[int, str, str]]:
        query = "SELECT id, content, status FROM todos"
        if not include_done:
            query += " WHERE status = 'open'"
        query += " ORDER BY id"
        with self._connect() as conn:
            rows = conn.execute(query).fetchall()
        return [(int(r[0]), str(r[1]), str(r[2])) for r in rows]

    def complete_todo(self, todo_id: int) -> tuple[str, bool]:
        if todo_id <= 0:
            raise ValueError("To-do ID must be a positive integer")
        with self._connect() as conn:
            row = conn.execute(
                "SELECT content, status FROM todos WHERE id = ?",
                (todo_id,),
            ).fetchone()
            if row is None:
                raise ValueError(f"To-do #{todo_id} was not found in this profile")
            content, status = str(row[0]), str(row[1])
            if status == "open":
                conn.execute(
                    "UPDATE todos SET status = 'done', "
                    "completed_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (todo_id,),
                )
        return content, status == "open"