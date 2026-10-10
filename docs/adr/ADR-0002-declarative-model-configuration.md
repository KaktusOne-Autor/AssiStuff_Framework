# ADR-0002: Declarative model, skill, and runtime configuration

- **Status:** Accepted
- **Date:** 2026-10-10

## Context

Model and skill configuration should be inspectable and extensible without
hardcoding model names into framework code. Internal utility roles are runtime
configuration, not model manifests.

## Decision

- Validate framework, model, skill, personality, and PUPC YAML with Pydantic
  schemas.
- Load `config/framework.yaml`, `config/models/*.yaml`,
  `config/skills/*.yaml`, `config/personalities/*.yaml`, and
  `config/access/pupc.yaml`.
- Keep utility roles (`router`, `planner`, `mpa`, and optional `compiler`) in
  the `runtime.utility_models` section of `framework.yaml`.
- Keep path resolution in the config paths API.

## Implementation record

The schemas, loader, paths, and initial manifests live under `assistuff/config/`
and `config/`. Model manifests can reference system prompts through
`prompts.system`; runtime prompt files belong in `prompts/roles/`.

## Setup

Install the runtime requirements with `pip install pyyaml 'pydantic>=2.6,<3'`.
