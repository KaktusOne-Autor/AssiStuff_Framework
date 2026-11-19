# ADR-0019: Visual Output and HTML artifacts

- **Status:** Accepted
- **Date:** 2026-11-19

## Context

An assistant should be able to create useful visual and interactive work, not
only text answers. The VTT is a strong demonstration of this capability, but
visual output also includes infographics, diagrams, games, and other HTML
artifacts.

## Decision

- Define Visual Output as a general artifact contract and isolated HTML viewer.
- Use standard HTML, CSS, JavaScript, and JSON data rather than a proprietary
  rendering language.
- Give each artifact a versioned manifest describing its entry point, assets,
  data, and requested host capabilities.
- Treat generated and imported artifacts as untrusted. Deny ambient file,
  shell, secret, and network access. Expose host functions only through
  explicit permission-checked APIs.
- Start validation with a simple non-VTT artifact and viewer safety/lifecycle
  tests. Treat the VTT as a later showcase that exercises the same contract.
- Let the user manage VTT-specific play and acceptance tests.

## Consequences

- Add a sandboxed HTML viewer, artifact storage/lifecycle, and a permissioned
  bridge to approved capabilities.
- Test accessibility, responsive rendering, error handling, isolation, and
  permission denial in the general viewer.
- The VTT may use procedural maps, structured NPC/dialogue output, dice, and
  rules aids, but must not receive broader host access than other artifacts.

## Implementation status

The GUI has a Visual Output panel that generates self-contained HTML through
configured model routing, stores it with metadata, lists saved artifacts, and
previews them in Qt WebEngine. The preview applies CSP and request/navigation
restrictions, disables persistent storage and downloads, and exposes no host
bridge. A VTT showcase now uses this same artifact path for seeded maps,
validated NPC responses, and player aids. Artifact import/export, asset
bundles, host APIs, and VTT-specific acceptance tests remain unfinished. See
[visual-output.md](../visual-output.md).
