# ADR-0013: Configure the installed Ollama inventory

- **Status:** Accepted
- **Date:** 2026-10-10

## Context

The default model catalogue contained tags that were not installed locally,
which made model selection and the framework's utility roles inconsistent with
the host's Ollama inventory.

## Decision

Use the exact names returned by `ollama list` for model manifest runtime tags
and utility-role references. Model IDs remain framework identifiers and may
normalize punctuation that is not allowed in manifest IDs.

## Consequences

- The manifests describe the local Ollama installation at the time this ADR was
  accepted; the list can become stale when the user changes that installation.
- Package distribution and model redistribution remain separate operations and
  must continue to respect each model's upstream terms.
