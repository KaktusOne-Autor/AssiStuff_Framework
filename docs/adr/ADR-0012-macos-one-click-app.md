# ADR-0012: One-click macOS application bundle

- **Status:** Accepted
- **Date:** 2026-10-10

## Context

The desktop GUI should launch directly from Finder without requiring the user to
open a terminal or remember a command.

## Decision

Provide a lightweight `AssiStuff.app` bundle at the project root. Its executable
resolves the project relative to the bundle and invokes `bin/assistuff`, which
uses the project virtual environment when available. Startup output is retained
in `~/.assistuff/logs/gui-launch.log`.

## Consequences

- The bundle is intended to remain in the project directory; moving it by itself
  will break the relative project lookup.
- GUI dependencies must be installed in the project's `.venv` before launch.
- Ollama remains a separate local service and must be available for model-backed
  chat.
