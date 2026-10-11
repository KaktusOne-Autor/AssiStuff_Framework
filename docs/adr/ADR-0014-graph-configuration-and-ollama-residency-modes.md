# ADR-0014: Graph-based configuration and Ollama residency modes

- **Status:** Accepted
- **Date:** 2026-10-11

## Context

The model and skill configuration is currently distributed across YAML
manifests. Users need a visual way to understand and configure how models and
skills relate, what capabilities they provide, and which capabilities they may
call. Runtime model residency also needs to support both machines with limited
memory and workstations that can keep multiple models ready.

## Decision

### Graph-based model and skill configuration

Add a GUI editor that presents configured models, skills, and their capability
relationships as a Mermaid-like node-and-edge graph.

- Model and skill nodes display their IDs, provided capabilities, and relevant
  status.
- Directed edges represent configured capability calls or dependencies.
- Selecting a node or edge exposes the corresponding editable configuration,
  including capabilities, interop permissions, model/skill manifest fields,
  and avatar selection.
- Saving the graph updates the existing declarative configuration files; the
  graph is a visual editor for those files, not a second configuration source.
- Validate edits with the existing schemas and capability/interop rules before
  writing them. Invalid configurations must be surfaced to the user and must
  not be silently saved.
- The graph is a configuration and inspection surface. It does not change the
  capability bus security model: a displayed edge does not bypass
  `interop.can_call`, `accepts_calls_from`, access levels, hop limits, or TTL.

### Ollama residency modes

Expose a runtime residency mode for models managed by an Ollama endpoint:

1. **Hot-plug** — load a model when a request needs it and allow it to be
   unloaded or evicted when it is no longer needed. This is the recommended
   default for low-memory or otherwise resource-constrained hardware. Respect
   configured pinning, keep-alive, and maximum-loaded-model limits.
2. **Selected-for-background** — keep the user-selected models loaded in the
   background so they are ready for requests without a cold-load delay. This
   mode is intended for workstations with enough RAM/VRAM to hold the selected
   models concurrently. The UI must show the selected set and report load or
   residency failures rather than claiming unavailable models are ready.

The selected-for-background set is explicit; it is not an instruction to load
every installed Ollama model. The selected set must be checked against the
configured resource limits and Ollama's actual loaded-model state.

## Configuration and UX principles

- Make the active residency mode and its resource implications visible in
  Settings and the model graph.
- Preserve declarative configuration as the source of truth, including when
  edits are made through the GUI.
- Do not start or reconfigure arbitrary Ollama server processes without
  explicit user configuration and clear status/error reporting. Residency
  controls which models are loaded through the configured endpoint; managing
  separate Ollama server processes is outside this decision.
- Keep model residency operations cancellable where practical and report
  partial failures per model.

## Consequences

- The graph editor will need schema-aware read/write support and tests for
  round-tripping existing manifests without dropping fields.
- Residency configuration will need an explicit mode and selected model set;
  current `pinned`, `keep_alive`, and `max_loaded` settings alone do not
  represent both modes.
- Hot-plug should remain usable when only one model can be resident at a time.
- Selected-for-background requires resource checks and clear user feedback,
  since Ollama may fail to load models due to available-memory constraints.

## Implementation status

This ADR defines the target behavior. The existing Models and Skills tabs do
not yet provide the graph editor, and `ModelResidency` does not yet implement
the two selectable modes or background selection UI.
