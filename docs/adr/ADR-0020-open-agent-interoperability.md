# ADR-0020: Open agent and skill interoperability

- **Status:** Accepted
- **Date:** 2026-11-19

## Context

AssiStuff needs to work with non-local model APIs and agent skill ecosystems
without binding its core to a single provider, agent runtime, or proprietary
package format. The requested skill experience is comparable to OpenClaw-like
discoverable agent skills, while preserving AssiStuff's own policy and
execution boundaries.

## Decision

- Prefer documented open formats and protocols: Markdown instructions,
  versioned YAML/JSON metadata, JSON Schema payloads, ordinary HTTP/JSON,
  OpenAPI for HTTP operations, and MCP for agent/tool exchange.
- Use OpenAI-compatible Chat Completions as a provider interoperability
  profile. Describe it as a compatibility target, not a formal open standard.
- Keep skill instructions portable and separate from executable tools.
  Provide a documented import/export subset for OpenClaw-like skill collections
  without claiming whole-runtime compatibility or copying their implementation.
- Adapt external models, skills, and tools at the boundary of the capability
  bus. Keep PUPC authorization, caller restrictions, validation, and local
  privacy policy authoritative.
- Reject unsupported features and permissions explicitly. Never silently
  downgrade security when importing a skill or calling an external agent.

## Consequences

- Publish versioned compatibility profiles and conformance fixtures.
- Add MCP and skill import/export adapters without making either protocol an
  authorization authority.
- Keep proprietary provider SDKs optional and isolated behind adapters.
- Imported instructions, model output, and tool results remain untrusted.
  Third-party executable skills require explicit review and a tested sandbox.

## Implementation status

OpenAI-compatible remote chat completions, instruction-only skill import, and
an MCP stdio `tools/list` / `tools/call` bridge are implemented. Skill export,
additional MCP methods, and interoperability conformance tests remain
planned. See [agent-interoperability.md](../agent-interoperability.md).
