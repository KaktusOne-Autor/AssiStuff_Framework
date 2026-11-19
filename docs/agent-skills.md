# Agent skills

> **Implemented foundation:** AssiStuff can install portable, instruction-only
> packages and expose enabled skill capabilities over MCP stdio. Executable
> imported skills, sandboxing, package export, and full OpenClaw compatibility
> are not implemented.

The target skill package separates readable instructions from executable
operations:

```text
skill-id/
├── manifest.yaml
├── SKILL.md
├── schemas/
└── tools/
```

This is the target package shape. The current importer reads a manifest and
one instruction file only; it does not load `schemas/` or `tools/`.

The manifest declares identity/version, capabilities, input/output schemas,
required permissions, dependencies, and implementation entry points.
`SKILL.md` describes when and how an agent should use the skill; it is
instructions, not an authorization mechanism. Tools declare concrete
operations and must pass schema validation and permission checks.

Planned UI operations include discovery, inspection, validation, configuration,
permission review, enable/disable, and test invocation. Discovered
workspace/user skills require review before enablement. Skills may be exposed
to models only through explicitly granted capability calls.

The existing `plugins/<id>.py` plus `<id>.json` mechanism executes trusted
Python in-process. It is not sandboxed. Do not install or enable untrusted
plugins. See [ADR-0016](./adr/ADR-0016-first-class-agent-skills.md).

## Portability and agent compatibility

An instruction-only portable package is a directory containing `manifest.yaml`
and the referenced `SKILL.md`. For example:

```yaml
id: infographic-helper
version: 1.0.0
kind: skill
description: Help create visual explainers.
instructions_file: SKILL.md
capabilities:
  provides: [visual.infographic]
input_schema:
  type: object
  properties:
    topic: {type: string}
  required: [topic]
permissions: [visual.output]
```

Install and enable it using an authenticated PUPC administrator account:

```bash
./bin/assistuff --skill-install ./skills/infographic-helper --admin-account owner
./bin/assistuff --skill-enable infographic-helper --admin-account owner
./bin/assistuff --list-skills
./bin/assistuff --skill infographic-helper --account owner \
  --skill-input '{"topic":"solar system"}'
```

The importer accepts only instruction files and JSON Schema data; executable
implementations are rejected. Imported skills start disabled. Declared
permissions are informational and grant no filesystem, network, subprocess,
memory, or visual-host access. JSON Schema remote references are rejected.
When invoked, a portable skill returns its instructions and validated input
as data for the caller; it does not execute tools itself.

The local MCP stdio server exposes registered skill capabilities:

```bash
./bin/assistuff --mcp
```

It implements MCP initialization, `tools/list`, and `tools/call`. By default it
runs with level-0 guest access and the isolated `guest` profile; pass
`--account USERNAME` only when the MCP host can provide an interactive
password prompt. PUPC capability levels and caller restrictions still apply.

This is a portable foundation, not full compatibility with an external agent
runtime. Package export, instruction discovery conventions beyond this
manifest, executable tools, additional MCP methods, and sandboxed third-party
code remain future work.

OpenClaw-like discoverability and instruction-led behavior are design
inspiration, not a compatibility claim. A future importer/exporter will
document its supported skill subset. It must preserve permissions and reject
unsupported executable features rather than silently granting access. See
[agent-interoperability.md](./agent-interoperability.md) and
[ADR-0020](./adr/ADR-0020-open-agent-interoperability.md).
