# ADR-0003: Self-contained `.nrdpkg` model packages

- **Status:** Accepted
- **Date:** 2026-10-10

## Context

Model packages need to be transferable and verifiable without relying on
external weight files at install time.

## Decision

- Bundle weights into `.nrdpkg` archives and record SHA-256 hashes.
- Build and extract package archives as streams to avoid loading large models
  into memory.
- On installation, verify weight hashes and, when requested, the package
  signature; create an Ollama model and record it in
  `~/.assistuff/registry.json`.
- Keep installed packages and generated Modelfiles under `~/.assistuff/`.

## Implementation record

The package manifest, builder, installer, path helpers, hashing, and weight
resolvers are implemented in `assistuff/pack/`.

## Known limitation

The Ollama resolver copies Ollama's internal blobs, while installer model
creation currently searches for a `.gguf` file. Use a compatible GGUF package
for the install-to-Ollama workflow until that format mismatch is resolved.
Check upstream redistribution terms before bundling any model.
