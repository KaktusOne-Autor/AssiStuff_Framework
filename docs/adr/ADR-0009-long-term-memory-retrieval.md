# ADR-0009: Long-term memory retrieval

- **Status:** Accepted
- **Date:** 2026-10-10

## Context

Long-term notes must be discoverable by time, keyword, and controlled tags, even
when a generated search query contains an unknown tag.

## Decision

- Index Markdown notes with FTS5 keyword and time data and filter by tags.
- Parse memory queries and rank the matching notes.
- Soft-validate tags: retry query generation once when an unknown tag is
  returned, then search without the tag filter.
- Allow rebuilding indexes from Markdown.

## Implementation record

Retrieval and indexing are implemented in `assistuff/memory/retrieval.py` and
`assistuff/memory/long_term.py`. CLI operations include search, append, tags,
and reindex.

## Remaining work

Implement vector search, a `reindex --force` option, and fuzzy tag matching.
SQLite FTS5 is expected from the supported macOS Python builds.
