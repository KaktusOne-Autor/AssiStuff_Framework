"""Layer 3: long-term memory — Markdown + FTS5 index."""

from __future__ import annotations

import logging
import re
import sqlite3
from collections import Counter
from contextlib import contextmanager
from collections.abc import Generator
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from assistuff.config.schemas import LongTermTagsConfig
from .tags import TagRegistry

logger = logging.getLogger(__name__)

_HEADER = "# AssiStuff memory\n\n"
_NOTE_LINE_RE = re.compile(
    r"^-\s*\[(?P<ts>[^\]]+)\]\s*(?P<tags>(?:#[\wА-Яа-яЁё/-]+\s+)*)(?P<body>.+?)\s*$"
)
_TAG_INLINE_RE = re.compile(r"#[\wА-Яа-яЁё/-]+")
_DEFAULT_TAG_BLOCK = (
    "<!-- tags\n"
    "identity: имя, возраст, город, язык, часовой пояс\n"
    "preferences: стиль, формат, язык ответов\n"
    "projects: проекты, над которыми работает пользователь\n"
    "people: люди, отношения, коллеги, семья\n"
    "health: здоровье, самочувствие, привычки\n"
    "schedule: расписание, встречи, дедлайны\n"
    "finance: финансы, покупки, бюджеты\n"
    "learning: учёба, курсы, книги, статьи\n"
    "ideas: идеи, планы, гипотезы\n"
    "problems: проблемы, баги, блокеры\n"
    "decisions: принятые решения, выводы\n"
    "questions: открытые вопросы, нерешённое\n"
    "events: события, поездки, встречи\n"
    "tools: инструменты, технологии, софт\n"
    "misc: всё остальное\n"
    "-->\n\n## Notes\n"
)


@dataclass(frozen=True)
class MemoryHit:
    line_start: int
    timestamp: str
    tags: tuple[str, ...]
    text: str
    score: float = 0.0


@dataclass(frozen=True)
class MemoryQuery:
    keywords: list[str]
    tags: list[str]
    time_range: tuple[datetime, datetime] | None
    semantic: str | None
    limit: int = 20


class LongTermMemory:
    def __init__(
        self,
        memory_md_path: str | Path,
        index_path: str | Path | None = None,
        *,
        tags_config: LongTermTagsConfig | None = None,
    ) -> None:
        self.memory_md_path = Path(memory_md_path)
        self.index_path = Path(index_path) if index_path else self.memory_md_path.with_suffix(".index.db")
        self.tags = TagRegistry(self.memory_md_path)
        self.tags_config = tags_config or LongTermTagsConfig()
        self._ensure_files()
        self._ensure_index()
        self.tags.load()
        self._reindex_if_needed()

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def _ensure_files(self) -> None:
        self.memory_md_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.memory_md_path.exists():
            self.memory_md_path.write_text(_HEADER + _DEFAULT_TAG_BLOCK, encoding="utf-8")

    @contextmanager
    def _connect(self) -> Generator[sqlite3.Connection, None, None]:
        conn = sqlite3.connect(self.index_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _ensure_index(self) -> None:
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS time_index ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "line_no INTEGER NOT NULL, "
                "timestamp TEXT NOT NULL, "
                "tags TEXT NOT NULL, "
                "text TEXT NOT NULL)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_time ON time_index(timestamp)"
            )
            try:
                conn.execute(
                    "CREATE VIRTUAL TABLE IF NOT EXISTS keyword_index "
                    "USING fts5(text, tags UNINDEXED, line_no UNINDEXED, timestamp UNINDEXED)"
                )
            except sqlite3.OperationalError as exc:
                logger.warning("FTS5 unavailable: %s", exc)

    # ------------------------------------------------------------------
    # Indexing
    # ------------------------------------------------------------------

    def _reindex_if_needed(self) -> None:
        if not self.index_path.exists() or self._index_is_stale():
            self.reindex(force=True)

    def _index_is_stale(self) -> bool:
        if not self.index_path.exists():
            return True
        if not self.memory_md_path.exists():
            return True
        try:
            return self.memory_md_path.stat().st_mtime > self.index_path.stat().st_mtime
        except OSError:
            return True

    def reindex(self, *, force: bool = False) -> int:
        if not force and not self._index_is_stale():
            return self.count()
        notes = self._parse_notes()
        with self._connect() as conn:
            conn.execute("DELETE FROM time_index")
            try:
                conn.execute("DELETE FROM keyword_index")
            except sqlite3.OperationalError:
                pass
            for note in notes:
                conn.execute(
                    "INSERT INTO time_index (line_no, timestamp, tags, text) "
                    "VALUES (?, ?, ?, ?)",
                    (note["line_no"], note["timestamp"], " ".join(note["tags"]), note["text"]),
                )
                try:
                    conn.execute(
                        "INSERT INTO keyword_index (text, tags, line_no, timestamp) "
                        "VALUES (?, ?, ?, ?)",
                        (note["text"], " ".join(note["tags"]), note["line_no"], note["timestamp"]),
                    )
                except sqlite3.OperationalError:
                    pass
        logger.info("reindexed %d notes", len(notes))
        return len(notes)

    def _parse_notes(self) -> list[dict]:
        if not self.memory_md_path.is_file():
            return []
        notes: list[dict] = []
        for line_no, raw in enumerate(self.memory_md_path.read_text(encoding="utf-8").splitlines()):
            m = _NOTE_LINE_RE.match(raw)
            if not m:
                continue
            ts = m.group("ts").strip()
            tags = tuple(_TAG_INLINE_RE.findall(m.group("tags") or ""))
            notes.append({
                "line_no": line_no,
                "timestamp": ts,
                "tags": tags,
                "text": m.group("body").strip(),
            })
        return notes

    # ------------------------------------------------------------------
    # Append
    # ------------------------------------------------------------------

    def append(self, text: str, tags: list[str]) -> MemoryHit:
        text = text.strip()
        if not text:
            raise ValueError("note text must not be empty")
        if len(text) > 500:
            raise ValueError("note text must not exceed 500 characters")
        canonical = self.tags.canonicalize_many(tags)
        if not canonical:
            canonical = [self.tags_config.fallback]
        if len(canonical) > self.tags_config.max_per_note:
            raise ValueError(
                f"a memory note can have at most "
                f"{self.tags_config.max_per_note} tags"
            )
        while len(canonical) < self.tags_config.min_per_note:
            fallback = self.tags.canonical(self.tags_config.fallback)
            if fallback in canonical:
                raise ValueError(
                    f"this note requires at least {self.tags_config.min_per_note} "
                    "distinct tags"
                )
            canonical.append(fallback)

        for c in canonical:
            if not self.tags.is_known(c) and not self.tags_config.dynamic:
                raise ValueError(f"unknown memory tag {c!r}; dynamic tags are disabled")
            if not self.tags.is_known(c):
                self.tags.add(
                    c,
                    position=self.tags_config.new_tag_position,
                )
        timestamp = datetime.now().astimezone().isoformat(timespec="seconds")
        line = f"- [{timestamp}] {' '.join(canonical)} {text}\n"
        with self.memory_md_path.open("a", encoding="utf-8") as handle:
            handle.write(line)
        self.reindex(force=True)
        return MemoryHit(
            line_start=0,
            timestamp=timestamp,
            tags=tuple(canonical),
            text=text,
        )

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search(self, query: MemoryQuery) -> list[MemoryHit]:
        keywords = [k for k in query.keywords if k]
        canonical_tags = self.tags.canonicalize_many(query.tags) if query.tags else []
        hits: list[MemoryHit] = []

        with self._connect() as conn:
            rows = self._candidate_rows(conn, keywords, canonical_tags, query.time_range)
        for row in rows:
            hits.append(MemoryHit(
                line_start=int(row["line_no"]),
                timestamp=str(row["timestamp"]),
                tags=tuple(str(row["tags"]).split()) if row["tags"] else (),
                text=str(row["text"]),
                score=float(row.get("score", 0.0)) if isinstance(row, dict) else 0.0,
            ))
        hits.sort(key=lambda h: (h.timestamp, h.line_start), reverse=True)
        return hits[: query.limit]

    def _candidate_rows(
        self,
        conn: sqlite3.Connection,
        keywords: list[str],
        tags: list[str],
        time_range: tuple[datetime, datetime] | None,
    ) -> list[sqlite3.Row]:
        clauses: list[str] = []
        params: list[object] = []

        if time_range is not None:
            start_iso = time_range[0].isoformat(timespec="seconds")
            end_iso = time_range[1].isoformat(timespec="seconds")
            clauses.append("timestamp BETWEEN ? AND ?")
            params.extend([start_iso, end_iso])

        for tag in tags:
            clauses.append("tags LIKE ?")
            params.append(f"%{tag}%")

        if keywords:
            fts_query = " OR ".join(keywords)
            try:
                rows = conn.execute(
                    f"SELECT line_no, timestamp, tags, text, bm25(keyword_index) AS score "
                    f"FROM keyword_index WHERE keyword_index MATCH ? "
                    f"ORDER BY score LIMIT 100",
                    (fts_query,),
                ).fetchall()
            except sqlite3.OperationalError:
                rows = []
            filtered: list[sqlite3.Row] = []
            for row in rows:
                if tags and not any(t in (row["tags"] or "") for t in tags):
                    continue
                if time_range is not None:
                    ts = str(row["timestamp"])
                    if not (time_range[0].isoformat(timespec="seconds") <= ts
                            <= time_range[1].isoformat(timespec="seconds")):
                        continue
                filtered.append(row)
            if filtered:
                return filtered

        where = " AND ".join(clauses) if clauses else "1=1"
        rows = conn.execute(
            f"SELECT line_no, timestamp, tags, text FROM time_index "
            f"WHERE {where} ORDER BY timestamp DESC LIMIT 100",
            params,
        ).fetchall()

        if keywords:
            lowered = [k.lower() for k in keywords]
            rows = [
                r for r in rows
                if any(k in str(r["text"]).lower() for k in lowered)
            ]
        return rows

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def read_all(self) -> str:
        if not self.memory_md_path.is_file():
            return ""
        return self.memory_md_path.read_text(encoding="utf-8")

    def count(self) -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) FROM time_index").fetchone()
        return int(row[0]) if row else 0

    def audit_tags(self) -> tuple[dict[str, int], list[str]]:
        counts: Counter[str] = Counter()
        for note in self._parse_notes():
            counts.update(note["tags"])
        unknown = sorted(tag for tag in counts if not self.tags.is_known(tag))
        ordered_counts = {
            tag: counts.get(tag, 0)
            for tag in self.tags.all()
        }
        ordered_counts.update({tag: counts[tag] for tag in unknown})
        return ordered_counts, unknown