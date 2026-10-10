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
under `assistuff/bus/`.

## Remaining work

Add a two-model `interop.can_call` enforcement test, read the
`output_chain.stream_to_gui` switch consistently across the UI, and render the
trace call stack as a graph in the Trace panel.
