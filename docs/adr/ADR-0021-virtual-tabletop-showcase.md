# ADR-0021: Virtual Tabletop showcase

- **Status:** Accepted
- **Date:** 2026-11-19

## Context

Visual Output should demonstrate more than static answers while preserving
the HTML viewer's isolation boundary. A Virtual Tabletop (VTT) is a useful
showcase for procedural visuals, structured NPC responses, and player aids.

## Decision

- Implement VTT as an original GUI scene board with interactive tokens and
  view-only snapshots through the existing Visual Output artifact store.
- Use common grid tabletop interactions without copying Foundry VTT source,
  assets, or proprietary implementation details.
- Support local hot-seat and token-protected LAN browser play with per-player
  positions, rotating turns, terrain costs, reachable destinations,
  discoverable locations, and an exit objective.
- Generate deterministic, seeded maps locally; keep map dimensions bounded by
  validated framework configuration.
- Keep dice local and implement an original point-buy and 3d6 roll-under helper
  inspired by a familiar tabletop mechanic. Do not present it as official
  GURPS rules.
- Persist character sheets in the active profile and validate their point
  budgets. Keep live campaign state in memory.
- Place NPC actors on the map and route NPC dialogue and Storyteller GM
  requests through the configured dispatcher. Validate structured responses
  against strict JSON schemas before displaying them.
- For LAN sessions, require a host-provided join code and per-player token.
  Keep the host responsible for all AI requests and warn that HTTP traffic is
  unencrypted and intended only for trusted local networks.
- Do not allow map regeneration while LAN hosting; stop the host first to
  avoid invalidating joined players' live state.
- Keep model interaction outside the HTML page. Do not expose a JavaScript
  host bridge or allow artifact HTML to call models, memory, or dice services.
- Treat AI rules explanations as non-authoritative summaries. Do not bundle
  or reproduce published rulebook text.
- Leave VTT playtests and acceptance tests to the user.

## Consequences

- Add a configurable VTT tab with map, character, dice, NPC, Storyteller GM,
  rules-help, hot-seat, and LAN-host controls.
- Map and dice remain available without a model service; AI interactions
  require a functioning configured provider.
- NPC, Storyteller, and rules prompts may be sent to a remote provider and
  must follow the configured provider's data policy.
- LAN multiplayer is deliberately simple: plain HTTP, up to eight total
  players, and no resumable campaign persistence. Do not expose it to the
  public internet.
- Combat automation and complete rules coverage are outside this
  implementation.

## Implementation status

The VTT tab includes seeded maps, hot-seat and LAN sessions, character
point-buy, map-visible NPCs, a structured AI Storyteller, local 3d6 checks,
rules summaries, and isolated HTML snapshots. Live campaign state is
in-memory; character sheets are profile-local. VTT-specific acceptance tests
remain user-owned. See [vtt.md](../vtt.md).
