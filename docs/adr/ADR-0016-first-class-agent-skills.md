# ADR-0016: First-class agent skills

- **Status:** Accepted
- **Date:** 2026-11-19

## Context

AssiStuff currently has built-in Python skills and an opt-in plugin loader for
Python modules. Users need an extensible skill system that can be discovered,
reviewed, configured, and invoked by agents, without making every skill an
unstructured in-process plugin.

The requested experience is comparable to discoverable agent-skill systems
(including OpenClaw-like instruction-led skills), but skills should remain
portable across agent runtimes rather than depend on a proprietary SDK. This
ADR does not prescribe copying another project's code or text or claim full
runtime compatibility.

## Decision

- Define an AssiStuff skill package with a validated manifest, human-readable
  `SKILL.md` instructions, declared capabilities, JSON Schema
  input/output contracts, and zero or more tool implementations or workflow
  steps.
- Keep package metadata and instructions in portable Markdown/YAML/JSON.
  Provide explicit adapters for MCP or other external tool protocols instead
  of coupling the skill format to one agent host.
- Support layered discovery from built-in, user, and workspace skill
  directories. Workspace skills are untrusted until explicitly reviewed and
  enabled.
- Separate skill instructions from executable tools. A skill with no executable
  tools may provide instructions only; a tool-bearing skill must declare its
  operations and required permissions.
- Require explicit grants for filesystem access, network access, subprocesses,
  memory reads/writes, and sensitive actions. Default to least privilege and
  deny undeclared operations.
- Expose approved skill operations as bus capabilities. Agent/model calls
  remain subject to `interop.can_call`, `accepts_calls_from`, access levels,
  hop/TTL limits, schema validation, and user confirmation policy.
- Provide lifecycle operations to discover, inspect, validate, enable/disable,
  configure, and update skills. Report invalid manifests and execution errors
  directly.
- Treat instructions and skill-provided content as untrusted input. They cannot
  alter framework policy, grant permissions, or override system instructions.
- Keep the existing Python plugin loader as an explicitly trusted/developer
  extension mechanism; do not silently treat arbitrary plugin code as a
  sandboxed skill.

## Consequences

- Add a versioned skill manifest/schema and a validation/discovery service.
- Add a Skills UI for inspection, permission review, enablement, and test runs.
- Define a stable tool API, execution result format, and cancellation behavior.
- A process sandbox may be required for third-party executable skills. Until
  that boundary is implemented and tested, only trusted local code may execute.
- Publish an import/export compatibility profile for OpenClaw-like skills;
  unsupported permissions or operations must be rejected, not weakened.

## Implementation status

An instruction-only portable package importer is implemented. Packages are
disabled by default, administrator-managed, and may declare JSON Schemas;
external references and executable implementations are rejected. A local MCP
stdio server exposes enabled skill capabilities while preserving bus/PUPC
checks. Package export, executable tool packages, sandboxing, full permission
UX, and complete agent-runtime compatibility remain unfinished. See
[agent-skills.md](../agent-skills.md) and
[agent-interoperability.md](../agent-interoperability.md).
