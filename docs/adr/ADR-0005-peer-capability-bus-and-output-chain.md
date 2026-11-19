# ADR-0005: Peer capability bus and output chain

- **Status:** Accepted
- **Date:** 2026-10-10

## Context

Models and skills should be peers addressable by capability rather than being
hidden behind one fixed orchestrator. Execution results and progress should be
observable by more than the original caller.

## Decision

- Register models and skills as capabilities on a shared bus.
- Enforce hop limits, time-to-live, caller allowlists, and minimum access
  levels when dispatching capability calls.
- Track calls with a trace ID, hops, call stack, and elapsed time.
- Emit chain events through an `OutputChain` that supports emitters and
  subscribers, collection, and final-result lookup.
- Treat GUI, logging, and TTS as event emitters/subscribers rather than
  hardwiring output to the caller.

## Implementation record

Core events, trace, output chain, capability bus, adapters, and emitters live
under `assistuff/bus/`. Calls made by a registered model or skill are checked
against its `interop.can_call` list; wildcard permissions are expanded for
model tool use. Tests cover allowed/denied peer calls and nested trace paths.
The Trace panel visualizes call-stack paths and safely receives events emitted
from worker threads. The Chat panel reads `output_chain.stream_to_gui`.

## Remaining work

Read `output_chain.stream_to_gui` consistently across all UI output surfaces.
