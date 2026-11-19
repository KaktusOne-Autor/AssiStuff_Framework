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

- A `publish` subcommand is not implemented; hosting is undecided.
- Key generation creates keys in `~/.assistuff/keys/`; users must protect
  private keys and distribute public keys out of band.

The `sign` subcommand signs or re-signs an existing `.nrdpkg` in place. It
validates the manifest and weight hashes, updates signature metadata and
integrity hashes, and preserves the archive's supported compression format.
Use the global `--verbose` option to show informational logs during commands.
