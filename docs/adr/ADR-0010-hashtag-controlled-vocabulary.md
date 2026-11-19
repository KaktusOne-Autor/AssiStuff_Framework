# ADR-0010: Dynamic bilingual hashtag vocabulary

- **Status:** Accepted
- **Date:** 2026-10-10

## Context

Memory tags should remain human-readable and consistent while allowing the
assistant to capture topics that have not previously appeared.

## Decision

- Keep the tag vocabulary in the `memory.md` header, with bilingual labels
  where configured.
- Resolve known tags to canonical names.
- Add new tags dynamically at the top of the header.
- Soft-validate tags during retrieval as described in ADR-0009.
- Enforce the configured maximum number of tags per note at append time.

## Implementation record

`assistuff/memory/tags.py` provides the tag registry, and the `remember` skill
accepts a note and tags. `LongTermMemory.append()` enforces the configured
maximum number of distinct tags (three by default) and rejects unknown tags
when dynamic additions are disabled. `--memory audit-tags` reports usage and
tags present on notes but missing from the header. Search fuzzy-matches close
tag names and retries unresolved tags once with the planner before dropping
the tag filter.

The Memory panel's **Edit tags…** action can add vocabulary entries directly.

## Remaining work

Support renaming/removing existing vocabulary entries in the Memory panel.
