# ADR-0007: Package signing and provenance

- **Status:** Accepted
- **Date:** 2026-10-10

## Context

Packages need integrity and provenance information, and redistribution limits
must be enforced before installation.

## Decision

- Use Ed25519 signatures over the package manifest and weight hashes.
- Include provenance and integrity metadata in every package manifest.
- Reject packages whose provenance explicitly sets
  `redistribution: forbidden`.
- Allow verification with an explicitly supplied public key.

## Implementation record

Key generation and signature helpers live in `assistuff/pack/signer.py`;
provenance and integrity schemas are in `assistuff/pack/manifest.py`; build and
install paths create and verify signatures.

## Remaining work

Ship a framework verification public key and document public-key rotation.
Build and in-place signing both record the signer fingerprint and use
`assistuff-pack verify --public-key PATH` to validate the resulting signature.
