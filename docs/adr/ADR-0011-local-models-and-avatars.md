# ADR-0011: Local model manifests and SVG avatars

- **Status:** Accepted
- **Date:** 2026-10-10

## Context

AssiStuff should use the Ollama models already installed on the host, with model
metadata kept declarative in `config/models/`. The Models tab also needs a way to
identify models visually without introducing a remote asset dependency.

## Decision

- Record locally available Ollama tags as model manifests; never add a manifest
  for a model that is not present in the local `ollama list`.
- Keep utility-role model tags in `config/framework.yaml`.
- Store optional model avatar paths in each model manifest. Avatars are SVG files
  selected in the Models tab and copied into `assets/avatars/`.
- Keep a shared built-in SVG avatar as the initial presentation.

## Consequences

- The configured model catalogue reflects this host's local Ollama inventory
  when it is populated; manifests can be adjusted when models are installed or
  removed.
- Avatar selection changes the corresponding model manifest and writes the SVG
  into the project so the UI does not depend on the source file's original path.
