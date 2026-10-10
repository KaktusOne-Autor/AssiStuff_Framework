"""Retrieval layer: parse queries, resolve tags, rank hits."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta

from .long_term import LongTermMemory, MemoryHit, MemoryQuery
from .tags import TagRegistry

logger = logging.getLogger(__name__)

_TAG_INLINE_RE = re.compile(r"#[\wА-Яа-яЁё/-]+")
_WORD_RE = re.compile(r"[\wА-Яа-яЁё-]{3,}")

_RELATIVE_TIME_PATTERNS = [
    (re.compile(r"\b(?:today|сегодня)\b", re.I), lambda now: (now - timedelta(days=1), now)),
    (re.compile(r"\b(?:yesterday|вчера)\b", re.I), lambda now: (now - timedelta(days=2), now - timedelta(days=1))),
    (re.compile(r"\b(?:last\s+week|на прошлой неделе)\b", re.I), lambda now: (now - timedelta(days=14), now)),
    (re.compile(r"\b(?:last\s+month|в прошлом месяце)\b", re.I), lambda now: (now - timedelta(days=60), now)),
    (re.compile(r"\b(?:last\s+year|год назад|в прошлом году)\b", re.I), lambda now: (now - timedelta(days=730), now)),
    (re.compile(r"\b(\d{4})\b"), None),  # handled specially
]

_STOPWORDS = {
    "the", "and", "for", "with", "about", "что", "про", "для", "как",
    "когда", "где", "был", "была", "было", "были", "это", "его", "её",
    "мне", "меня", "тебе", "тебя", "говорил", "говорила", "сказал",
    "сказала", "помню", "помнишь", "знаю", "знаешь",
}


class RetrievalError(RuntimeError):
    pass


def parse_memory_query(raw: str, tags: TagRegistry) -> MemoryQuery:
    text = raw.strip()
    inline_tags = _TAG_INLINE_RE.findall(text)
    canonical_tags = tags.canonicalize_many(inline_tags)
    text_no_tags = _TAG_INLINE_RE.sub(" ", text)

    keywords = [
        w.lower() for w in _WORD_RE.findall(text_no_tags)
        if w.lower() not in _STOPWORDS
    ]

    time_range = _extract_time_range(text_no_tags)

    return MemoryQuery(
        keywords=keywords,
        tags=canonical_tags,
        time_range=time_range,
        semantic=None,
        limit=20,
    )


def _extract_time_range(text: str) -> tuple[datetime, datetime] | None:
    now = datetime.now().astimezone()

    for pattern, handler in _RELATIVE_TIME_PATTERNS:
        if handler is None:
            continue
        if pattern.search(text):
            return handler(now)

    year_match = re.search(r"\b(19|20)\d{2}\b", text)
    if year_match:
        year = int(year_match.group(0))
        start = datetime(year, 1, 1, tzinfo=now.tzinfo)
        end = datetime(year, 12, 31, 23, 59, 59, tzinfo=now.tzinfo)
        return start, end

    return None


def rank_hits(hits: list[MemoryHit], query: MemoryQuery) -> list[MemoryHit]:
    def key(hit: MemoryHit) -> tuple:
        tag_overlap = len(set(hit.tags) & set(query.tags)) if query.tags else 0
        kw_overlap = sum(1 for k in query.keywords if k in hit.text.lower())
        return (-tag_overlap, -kw_overlap, hit.timestamp)

    return sorted(hits, key=key, reverse=False)


class MemoryRetriever:
    def __init__(self, memory: LongTermMemory) -> None:
        self.memory = memory

    def search(self, raw_query: str) -> list[MemoryHit]:
        query = parse_memory_query(raw_query, self.memory.tags)
        hits = self.memory.search(query)
        return rank_hits(hits, query)

    def search_with_retry(
        self,
        raw_query: str,
        *,
        retry_callback=None,
        max_retries: int = 1,
    ) -> list[MemoryHit]:
        query = parse_memory_query(raw_query, self.memory.tags)
        unknown = [t for t in query.tags if not self.memory.tags.is_known(t)]
        if not unknown:
            return rank_hits(self.memory.search(query), query)

        logger.warning("unknown tags in query: %s", unknown)
        if retry_callback and max_retries > 0:
            for _ in range(max_retries):
                new_tags = retry_callback(unknown, self.memory.tags.all())
                if not new_tags:
                    break
                query = MemoryQuery(
                    keywords=query.keywords,
                    tags=self.memory.tags.canonicalize_many(new_tags),
                    time_range=query.time_range,
                    semantic=query.semantic,
                    limit=query.limit,
                )
                if all(self.memory.tags.is_known(t) for t in query.tags):
                    break

        if query.tags and all(not self.memory.tags.is_known(t) for t in query.tags):
            logger.warning("no valid tags after retry; searching without tags")
            query = MemoryQuery(
                keywords=query.keywords,
                tags=[],
                time_range=query.time_range,
                semantic=query.semantic,
                limit=query.limit,
            )

        return rank_hits(self.memory.search(query), query)