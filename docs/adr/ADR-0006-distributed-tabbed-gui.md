# ADR-0006: Distributed tabbed desktop GUI

- **Status:** Accepted
- **Date:** 2026-10-10

## Context

The desktop interface needs separable panels that can be developed independently
and a common context for configuration, profile, and runtime access.

## Decision

- Use a tab registry and shared UI context.
- Provide Chat, Models, Tasks, Memory, Skills, Trace, Settings, and Plugins
  tabs.
- Keep telemetry in a dock hidden by default and offer a View menu toggle
  (`Ctrl+T`).
- Support reloading panels (`Ctrl+R`) and running a tray-only interface.

## Implementation record

The shell, registry, panels, telemetry dock, and tray live under `assistuff/ui/`.
The desktop app can be opened with `./bin/assistuff` or `AssiStuff.app`.
Tasks are planned as a validated DAG and run only after the user selects
**Run**; each step is routed through the normal dispatcher.

## Remaining work

Wire Chat's microphone control to voice capabilities, persist/resume task
graphs, document the reload shortcut in the UI, and apply the configured
`qt-material` dark theme consistently.
