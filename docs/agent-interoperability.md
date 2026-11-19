# Agent and skill interoperability

> **Implemented foundation:** OpenAI-compatible remote chat completions,
> instruction-only portable skill import, and an MCP stdio tools server are
> available. Full import/export and protocol coverage are not implemented.

## Interoperability principles

- Keep skill instructions, metadata, data schemas, and tool transport separate.
- Prefer plain Markdown, YAML/JSON, JSON Schema, HTTP, and web standards over
  framework-specific executable packages.
- Make adapters explicit and versioned. Do not describe a compatibility layer
  as a formal standard when it is only a widely used convention.
- Require declared permissions and validate inputs regardless of the source
  agent or skill format.
- Preserve local-first behavior: remote inference or external tool use must be
  selected and disclosed, never an implicit fallback.

## Planned compatibility surfaces

| Surface | Portable contract | AssiStuff direction |
| --- | --- | --- |
| Remote inference | OpenAI-compatible Chat Completions HTTP API | Implemented for configured endpoint profiles; streaming and provider-specific features remain out of scope. |
| Agent tool exchange | Model Context Protocol (MCP) | Stdio `initialize`, `tools/list`, and `tools/call` bridge for registered skills; resources/prompts and external MCP clients are not built into the GUI. |
| Skill instructions | Plain `SKILL.md` Markdown plus versioned YAML/JSON metadata | Instruction-only package import is implemented; export and broader OpenClaw-like compatibility remain planned. |
| Tool input/output | JSON Schema and JSON values | Validate at the capability boundary and keep provider/agent adapters outside the skill logic. |
| HTTP tools | OpenAPI-described HTTP operations | Planned optional transport; every operation still needs explicit network permission. |
| Visual artifacts | HTML, CSS, JavaScript, and JSON | Implemented isolated viewer, local artifact storage, and a VTT showcase; host APIs and asset bundles remain planned. |

OpenAI-compatible APIs are a de facto compatibility target, not a declaration
that the OpenAI API is a standards-body protocol. AssiStuff should use ordinary
HTTP/JSON and provider-neutral configuration rather than requiring a
provider-specific SDK.

“OpenClaw-like” describes the desired discoverable, instruction-led skill
experience. It does not imply copying OpenClaw code or claiming compatibility
with its complete runtime. The current importer rejects executable
implementations and does not grant manifest-declared permissions.

## Trust and policy

Instructions and tool results from another agent are untrusted data. Imported
skills begin disabled; executable code is not made safe merely by having a
manifest. Permission grants, PUPC checks, caller restrictions, schema
validation, cancellation, and sandbox boundaries remain AssiStuff-owned and
cannot be overridden by imported instructions.

See [agent-skills.md](./agent-skills.md),
[ADR-0020](./adr/ADR-0020-open-agent-interoperability.md),
[ADR-0015](./adr/ADR-0015-remote-model-api-providers.md), and
[ADR-0016](./adr/ADR-0016-first-class-agent-skills.md).
