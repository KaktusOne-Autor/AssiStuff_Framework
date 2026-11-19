"""Retrieval layer: parse queries, resolve tags, rank hits."""

from __future__ import annotations

import inspect
import logging
import re
from dataclasses import replace
from datetime import datetime, timedelta
from difflib import get_close_matches

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
    def __init__(
        self,
        memory: LongTermMemory,
        retry_callback=None,
        *,
        max_retries: int = 1,
    ) -> None:
        self.memory = memory
        self.retry_callback = retry_callback
        self.max_retries = max_retries

    def search(self, raw_query: str) -> list[MemoryHit]:
        query = self._with_fuzzy_tags(
            parse_memory_query(raw_query, self.memory.tags)
        )
        if any(not self.memory.tags.is_known(tag) for tag in query.tags):
            query = replace(query, tags=[])
        return rank_hits(self.memory.search(query), query)

    def search_with_retry(
        self,
        raw_query: str,
        *,
        retry_callback=None,
        max_retries: int | None = None,
    ) -> list[MemoryHit]:
        if max_retries is None:
            max_retries = self.max_retries
        query = self._with_fuzzy_tags(parse_memory_query(raw_query, self.memory.tags))
        unknown = [t for t in query.tags if not self.memory.tags.is_known(t)]
        retry = retry_callback or self.retry_callback
        if unknown and retry and max_retries > 0:
            logger.warning("unknown tags in query: %s", unknown)
            for _ in range(max_retries):
                candidate = retry(unknown, self.memory.tags.all())
                if inspect.isawaitable(candidate):
                    if inspect.iscoroutine(candidate):
                        candidate.close()
                    raise RuntimeError(
                        "async tag retry callbacks require search_with_retry_async"
                    )
                new_tags = candidate
                if not new_tags:
                    break
                query = replace(
                    query,
                    tags=self._with_fuzzy_values(new_tags),
                )
                if not any(
                    not self.memory.tags.is_known(tag)
                    for tag in query.tags
                ):
                    break

        unknown = [t for t in query.tags if not self.memory.tags.is_known(t)]
        if unknown:
            logger.warning("no valid tags after retry; searching without tags")
            query = replace(query, tags=[])

        return rank_hits(self.memory.search(query), query)

    async def search_with_retry_async(
        self,
        raw_query: str,
        *,
        retry_callback=None,
        max_retries: int | None = None,
    ) -> list[MemoryHit]:
        if max_retries is None:
            max_retries = self.max_retries
        query = self._with_fuzzy_tags(parse_memory_query(raw_query, self.memory.tags))
        unknown = [tag for tag in query.tags if not self.memory.tags.is_known(tag)]
        retry = retry_callback or self.retry_callback
        if unknown and retry and max_retries > 0:
            logger.warning("unknown tags in query: %s", unknown)
            for _ in range(max_retries):
                candidate = retry(unknown, self.memory.tags.all())
                new_tags = (
                    await candidate
                    if inspect.isawaitable(candidate)
                    else candidate
                )
                if not new_tags:
                    break
                query = replace(query, tags=self._with_fuzzy_values(new_tags))
                if not any(
                    not self.memory.tags.is_known(tag)
                    for tag in query.tags
                ):
                    break

        unknown = [tag for tag in query.tags if not self.memory.tags.is_known(tag)]
        if unknown:
            logger.warning("no valid tags after retry; searching without tags")
            query = replace(query, tags=[])
        return rank_hits(self.memory.search(query), query)

    def _with_fuzzy_tags(self, query: MemoryQuery) -> MemoryQuery:
        return replace(query, tags=self._with_fuzzy_values(query.tags))

    def _with_fuzzy_values(self, tags: list[str]) -> list[str]:
        known = self.memory.tags.all()
        resolved: list[str] = []
        for tag in tags:
            canonical = self.memory.tags.canonical(tag)
            if self.memory.tags.is_known(canonical):
                resolved.append(canonical)
                continue
            match = get_close_matches(canonical, known, n=1, cutoff=0.72)
            resolved.append(match[0] if match else canonical)
        return self.memory.tags.canonicalize_many(resolved)


_TAG_RETRY_SCHEMA = {
    "type": "object",
    "properties": {
        "tags": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["tags"],
}


async def retry_unknown_tags_with_planner(roles, unknown: list[str], known: list[str]) -> list[str]:
    result = await roles.generate_json(
        "planner",
        "Map unknown memory tags to the closest applicable tags from the "
        "controlled vocabulary. Do not invent tags. If no tag is appropriate, "
        "return an empty list.\n"
        f"Unknown tags: {unknown}\nKnown tags: {known}",
        schema=_TAG_RETRY_SCHEMA,
    )
    tags = result.get("tags", [])
    if not isinstance(tags, list):
        return []
    return [tag for tag in tags if isinstance(tag, str)]