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
accepts a note and tags.

## Remaining work

Connect the unknown-tag retry callback to the planner model, add tag editing in
the Memory panel, and verify the maximum of three tags per note is enforced.
