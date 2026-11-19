# Visual Output

> **Implemented foundation:** The GUI can generate, save, list, and preview
> self-contained HTML documents in an isolated Qt WebEngine page. The VTT is a
> concrete example, while artifact import/export and host APIs remain planned.

Visual Output is a general presentation surface where an assistant can create
and display artifacts rather than returning only prose. The Virtual Tabletop
(VTT) is a substantial example and acceptance showcase for that capability,
not the definition or limit of Visual Output.

## Supported artifact direction

The Visual Output tab sends a request through configured model routing and
stores the returned HTML under the user data directory in `visual-artifacts/`.
Artifacts are limited to 1 MB, saved with owner-only file permissions, and
shown in the saved-artifact list. The viewer supports ordinary HTML, inline
CSS/JavaScript, and data/blob images. Example artifact types include:

- Infographics, charts, timelines, and diagrams.
- Small interactive games and simulations.
- Dashboards, visual explanations, and interactive learning aids.
- A VTT with procedure-generated maps, JSON-described NPCs and dialogue, and
  player aids such as dice and concise rules references.

The current storage format is a self-contained HTML document plus local JSON
metadata. The viewer displays the artifact without granting it a bridge to the
AssiStuff application. Artifact editing, import/export, manifests, and asset
bundles are not yet supported.

## Safety and interaction boundary

Generated HTML, scripts, NPC dialogue, and imported assets are untrusted. The
current viewer enables JavaScript for local interactivity but applies a
restrictive CSP: scripts and styles must be inline; images/media may use
`data:` or `blob:`; network connections, frames, forms, workers, objects, and
external fonts are blocked. Qt WebEngine also blocks non-`data:`/`blob:`
requests, external top-level navigation, downloads, local storage, clipboard
access, and JavaScript-created windows. No AssiStuff host bridge is exposed.

Interactions with memory, models, dice/rules services, or other capabilities
are not directly available inside an artifact. The VTT's model-backed NPC and
rules controls live in the Qt panel and call the normal dispatcher outside the
page; dice are rolled locally. Any future in-artifact integration must use
explicit, permission-checked host APIs.

The user explicitly starts generation and chooses which saved item to view.
Generation routes the prompt through configured model providers, so prompts
are subject to those providers' privacy policies. Artifact preview does not
silently cause external requests or privileged AssiStuff actions.

## VTT as a capability showcase

The VTT tab exercises the same artifact viewer as infographics and games. It
currently provides:

- Seeded procedural map generation with a connected route and selectable tiles.
- Hot-seat turns and an optional token-protected LAN browser client. LAN uses
  unencrypted HTTP on trusted local networks; all AI requests stay on the host.
- Profile-local character point-buy and a local 3d6 roll-under skill helper.
- Map-visible NPC roleplay and Storyteller GM replies parsed against strict
  JSON/Pydantic schemas.
- Concise AI-generated rules explanations, marked non-authoritative.
- Saved HTML scene snapshots in the same artifact list and isolated viewer.

The character and 3d6 helper uses original point-buy rules; it is not a full or
official GURPS implementation. Live campaign state is not persisted. NPC,
Storyteller, and rules requests use the configured assistant route; do not
include private campaign details unless the configured provider is trusted.
The helper does not include or reproduce published rulebook text and does not
claim edition-specific rulings. VTT-specific play and acceptance tests remain
user-owned. See the [VTT guide](./vtt.md).

See [ADR-0019](./adr/ADR-0019-visual-output-html-artifacts.md).
