# ADR-0001: AssiStuff Framework alongside Noredur

- **Status:** Accepted
- **Date:** 2026-10-10

## Context

AssiStuff is being introduced into a codebase that contains Noredur 4.0.0.
Noredur is a reference implementation and must remain available during
migration.

## Decision

- Add AssiStuff as the `assistuff` Python package, version `1.0`, with the
  `assistuff` and `assistuff-pack` command-line entry points.
- Keep the historical `.nrdpkg` package extension.
- Keep Noredur's name, references, and `src/noredur/` tree unchanged.
- Do not make AssiStuff imports reach into `src/noredur/`.

## Implementation record

- `assistuff/`, the two CLI wrappers, and project metadata define the additive
  framework surface.
- `README-assistuff.md` explains the coexistence boundary.

## Constraints

Do not rename, delete, or edit `src/noredur/` as part of AssiStuff work.
