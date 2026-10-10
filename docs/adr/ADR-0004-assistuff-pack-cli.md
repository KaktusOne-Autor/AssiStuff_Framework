# ADR-0004: `assistuff-pack` package CLI

- **Status:** Accepted
- **Date:** 2026-10-10

## Context

Package authoring and installation should be available through a single
command-line tool.

## Decision

Provide subcommands for package initialization, build, lint, verify, sign,
install, list, uninstall, key management, and export. Support local file,
Hugging Face, and Ollama weight sources.

## Implementation record

The CLI is implemented by `assistuff/pack/cli.py`, with the executable wrapper
in `bin/assistuff-pack`.

## Known limitations

- The `sign` subcommand is currently a placeholder. Sign during the build with
  `build --sign-key PATH`.
- A `publish` subcommand is not implemented; hosting is undecided.
- Key generation creates keys in `~/.assistuff/keys/`; users must protect
  private keys and distribute public keys out of band.
