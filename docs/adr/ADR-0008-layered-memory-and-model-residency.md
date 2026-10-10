# ADR-0008: Layered memory and model residency

- **Status:** Accepted
- **Date:** 2026-10-10

## Context

Conversation continuity and durable personal memory are core framework
capabilities. Local hardware may also require careful model residency to avoid
unnecessary model swaps.

## Decision

Use four memory layers:

1. Working memory in process.
2. Short-term message and todo storage in SQLite.
3. Long-term Markdown notes with full-text and time indexes.
4. A structured dossier sliced and compiled for relevant queries.

Add a model residency manager with pinned models, a maximum number of loaded
models, and eviction behavior.

## Implementation record

Memory layers live under `assistuff/memory/`; residency is implemented in
`assistuff/runtime/residency.py`. Profile data is created under
`~/.assistuff/profiles/<profile>/` on first use.

## Remaining work

Call `warm_pinned()` at startup, trigger dossier compilation from memory writes,
add a memory-tag audit command, and compact `memory.md` above a configured size.
