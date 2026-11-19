# AssiStuff Framework

**Release: 1.0.1-beta — VTT multiplayer and framework hardening**

AssiStuff is a local-first assistant framework with a Python CLI, a desktop
GUI, configurable model and skill manifests, profile-scoped memory, and an
HTML Visual Output surface. Run local models through Ollama or explicitly
configure an OpenAI-compatible remote endpoint.

This is a beta: interfaces and configuration may change. Some planned
integrations are incomplete; the feature status and limitations below describe
what this release actually provides.

AssiStuff coexists with Noredur. The historical `.nrdpkg` package name is
retained, and `src/noredur/` remains a separate reference tree. See
[README-assistuff.md](./README-assistuff.md).

## What is in 1.0.1-beta

| Area | Beta status |
| --- | --- |
| CLI and desktop GUI | Available; GUI requires the `gui` extra |
| Local models | Ollama-backed routing, hot-plug and background residency |
| Remote models | OpenAI-compatible chat-completions profiles |
| Memory | Working, SQLite short-term, Markdown/FTS long-term, and dossier layers |
| Accounts | Local password accounts, profile binding, and PUPC levels |
| Visual Output | Isolated HTML artifact storage and viewer |
| Virtual Tabletop | Hot-seat and LAN play, point-buy characters, NPCs, Storyteller GM |
| Skills and tools | Built-ins, instruction-only imports, and MCP stdio tools |
| Model packages | `.nrdpkg` build, verify, sign, install, list, and uninstall |
| Voice | Local capture, whisper.cpp, Vosk, Piper, and wake-word wiring; GUI audio is opt-in and local assets are required |

This release uses Python package version `1.0.1b1` (PEP 440); the GUI displays
`1.0.1-beta`. The VTT now supports per-player turns, profile-local character
sheets, map-visible NPCs, structured Storyteller responses, and token-protected
LAN browser clients. The release also fixes LLM-route prompt formatting and
final-result retrieval from closed output chains. LAN uses unencrypted HTTP
and is intended only for trusted local networks. See the
[VTT guide](./docs/vtt.md) before hosting.

## Quick start

### Requirements

- Python 3.11–3.13
- macOS or Linux
- Ollama for local model-backed requests
- Optional GUI dependencies for the desktop app

Create an environment and install the GUI:

```bash
git clone https://github.com/KaktusOne-Autor/AssiStuff_Frmwrk.git
cd AssiStuff_Frmwrk
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[gui]'
```

For packaging and signing tools, install the `pack` extra. For development
tests and linting, install `dev`. The `voice` extra installs Python audio
dependencies; whisper.cpp, Vosk models, Piper, and voice assets are separate.

### Check and run

Start Ollama if it is not already running. Inspect the configured model tags
in `config/framework.yaml` and `config/models/*.yaml`, and pull the tags you
intend to use:

```bash
ollama serve
ollama list
ollama pull <configured-model-tag>
./bin/assistuff --check
```

The calculator skill does not need a model:

```bash
./bin/assistuff --skill calculator --skill-input "2 + 2"
```

It should return `4`. For model-backed chat, install the model tags referenced
by the configured utility roles, then run:

```bash
./bin/assistuff --ask "What is 2 + 2?"
```

`--check` reports a warning if Ollama is unavailable; model-backed requests
will need a reachable configured provider.

## Desktop application

Launch from the repository directory:

```bash
./bin/assistuff
```

On macOS, the included app bundle can also be opened with `open AssiStuff.app`.
The GUI contains Chat, Models, Tasks, Memory, Visual Output, VTT, Skills,
Graph, Trace, Settings, and Plugins tabs. The telemetry dock is hidden by
default; toggle it from **View → Toggle telemetry dock** (`Ctrl+T`). **View →
Reload panels** (`Ctrl+R`) reloads panels that support it.

The **Models** tab lists configured manifests and lets you choose or clear an
SVG avatar; selected files are copied into `assets/avatars/` and the manifest
is updated.

The **Graph** tab shows configured model/skill capability connections and
configures Ollama residency:

- **Hot-plug** loads models on demand and observes `runtime.residency.max_loaded`.
- **Selected for background** loads selected models when AssiStuff starts.
- Pinned models are warmed at startup and protected from eviction in either
  mode.

Graph permission and residency edits require a level-5 administrator when
accounts exist. Restart AssiStuff to apply changes to active registrations.

The **Tasks** tab asks the planner for a dependency-validated plan. Review the
steps, then explicitly select **Run** to execute them through normal request
routing. Plans are currently in-memory and cannot be resumed after exit.

## Accounts and PUPC

The first local account becomes the level-5 administrator. Passwords are
entered through a hidden prompt:

```bash
./bin/assistuff --account-create owner
./bin/assistuff --account-create player --admin-account owner --profile player
./bin/assistuff --account-list --admin-account owner
```

The GUI prompts for sign-in when accounts exist. CLI requests use
`--account USERNAME`; account management uses `--admin-account USERNAME`.
Unauthenticated requests receive level-0 guest access and use the isolated
`guest` profile. Model unloading and `.nrdpkg` installation/removal also
require an administrator when accounts are configured.

The registry is stored under `~/.assistuff/accounts.db` (or the configured
`ASSISTUFF_HOME`). Account setup, permissions, and limitations are documented
in [docs/account-registry.md](./docs/account-registry.md).

## Memory

Memory is profile-scoped beneath `~/.assistuff/profiles/`. Common operations:

```bash
./bin/assistuff --memory tags
./bin/assistuff --memory append "Working on AssiStuff" --tags "#project,#work"
./bin/assistuff --memory search "AssiStuff"
./bin/assistuff --memory audit-tags
./bin/assistuff --memory reindex
./bin/assistuff --memory reindex --force
```

The framework has in-process working memory, SQLite short-term messages and
todos, Markdown long-term notes with FTS5/time indexes, and a structured
dossier. Models receive memory context only according to their manifests:
`memory.reads` controls working/recent/todo/long-term context, while
`memory.dossier_access` controls dossier access. Remove a layer from a
manifest to withhold it. Model memory writes and `memory.writes` enforcement
are not implemented.

Long-term notes use the profile's Markdown file and FTS5 index. Tags can be
listed, searched, audited, and reindexed; forced reindex is available with
`--force`. Each note is limited to the configured maximum number of tags.

The `recall` skill searches long-term memory when invoked:

```bash
./bin/assistuff --skill recall --skill-input "AssiStuff"
```

See the [memory and retrieval ADRs](#architecture-decisions) for layer and
tag behavior.

## Visual Output and VTT

The **Visual Output** tab generates, saves, lists, and previews self-contained
HTML artifacts. Scripts can run locally for interactivity, but the viewer
blocks network requests, external navigation, downloads, persistent browser
storage, and Qt host access. Treat generated HTML as untrusted. Artifact
prompts are sent through the configured model route; do not include secrets.

The **VTT** tab is a playable tabletop scene with hot-seat play and an
optional token-protected LAN browser host. It provides:

- Generate repeatable procedural maps from a seed; map dimensions are
  configured under `vtt` in `config/framework.yaml`.
- Click reachable tiles to move the player token. Terrain has movement costs;
  water and ridges are impassable. End turns to replenish movement points.
- Find and investigate hidden locations, track each player's grid position, and
  reach the exit objective.
- Create profile-local characters with original point-buy attributes and
  skills; make 3d6 roll-under skill checks.
- Place map-visible NPCs and ask them for structured replies. Request original
  scene continuations from the Storyteller GM and concise AI-generated rules
  summaries.
- Host LAN browser players from the GUI; the host handles all AI requests.
- Save the current map and conversation state as view-only HTML snapshots in
  `~/.assistuff/visual-artifacts/`.

The point-buy helper and 3d6 mechanic are original and are not a full or
official GURPS rules engine. NPC, Storyteller, and rules summaries use the
configured assistant route, may be sent to a remote provider, and are not
authoritative. LAN transport uses unencrypted HTTP and is intended only for a
trusted local network. Live campaign state is not persisted; character sheets
are saved to the active profile. VTT acceptance tests remain user-owned. See
[docs/visual-output.md](./docs/visual-output.md) and [docs/vtt.md](./docs/vtt.md).

## Skills, plugins, and MCP

Built-in skills can be listed and invoked from the CLI:

```bash
./bin/assistuff --list-skills
./bin/assistuff --skill calculator --skill-input "2 + 2"
```

Portable imports currently support instruction-only packages with a
`manifest.yaml`, `SKILL.md`, and optional JSON Schemas. Imports start disabled;
executable imported tools are rejected and declared permissions do not grant
host access:

```bash
./bin/assistuff --skill-install ./skills/my-helper --admin-account owner
./bin/assistuff --skill-enable my-helper --admin-account owner
./bin/assistuff --list-skills
```

Run the MCP stdio server with `./bin/assistuff --mcp`. It exposes registered
skill capabilities through `initialize`, `tools/list`, and `tools/call`, with
capability-bus and PUPC checks.

Python plugins are a separate legacy mechanism. Enabled plugins execute
in-process with the application's permissions and are **not sandboxed**.
Only enable code you trust. See [docs/agent-skills.md](./docs/agent-skills.md)
and [docs/agent-interoperability.md](./docs/agent-interoperability.md).

## Remote model APIs

Remote models use explicitly configured OpenAI-compatible Chat Completions
profiles; there is no silent fallback from a local model. Configure an
endpoint and model manifest, then provide the API key through the named
environment variable. Never commit credentials. Remote requests disclose
prompts and attached context to the configured provider. Streaming, remote
tool-calls, and provider-specific features are not included. Setup details are
in [docs/remote-models.md](./docs/remote-models.md).

## Build `.nrdpkg` model packages

Install the pack tools and scaffold a package:

```bash
python -m pip install -e '.[pack]'
./bin/assistuff-pack init packages/example \
  --id example --name Example --version 1.0.0
```

Add redistributable GGUF weights, complete the manifest's license/provenance
metadata, then lint, build, and verify:

```bash
./bin/assistuff-pack lint packages/example
./bin/assistuff-pack keys generate --name dev
./bin/assistuff-pack build packages/example -o dist \
  --sign-key ~/.assistuff/keys/dev.key
./bin/assistuff-pack verify dist/example-1.0.0.nrdpkg \
  --public-key ~/.assistuff/keys/dev.pub
```

Install with a trusted public key:

```bash
./bin/assistuff-pack install dist/example-1.0.0.nrdpkg \
  --public-key ~/.assistuff/keys/dev.pub --admin-account owner
```

The pack CLI also supports `list`, `uninstall`, `export`, `sign`, and key
management. Use `./bin/assistuff-pack --help` for complete syntax. Unsigned
development packages require `--allow-unsigned`. The Ollama resolver currently
copies internal blobs while installation expects a GGUF weight file. Package
publishing, bundled verification keys, and a key-rotation workflow are not
available. Follow upstream licensing and redistribution terms; see
the package ADRs in [Architecture decisions](#architecture-decisions).

## Configuration and data

- `config/framework.yaml` — runtime, utility roles, memory, access, UI,
  residency, voice settings, and VTT map dimensions.
- `config/models/*.yaml` — model backend/tag, routing, access, memory, and
  capability declarations.
- `config/skills/*.yaml` — built-in skill manifests.
- `config/personalities/*.yaml` — personality prompts.
- `config/access/pupc.yaml` — six PUPC levels.

The default user data directory is `~/.assistuff/`; set `ASSISTUFF_HOME` to
use another location. Back up profiles and account data before beta upgrades.
Local model prompts remain local unless you explicitly configure a remote
provider. Review each provider's privacy, retention, quota, and cost policies.

## Beta limitations

- Voice requires local executables, models, audio dependencies, and microphone
  permission. GUI controls are disabled by default; wake listening is opt-in.
  Speaker authentication requires profile enrollment; see
  [docs/voice.md](./docs/voice.md).
- Portable skills do not execute tools. Full OpenClaw compatibility, package
  export, and sandboxed third-party code are not implemented.
- Remote tool calls, streaming, and providers beyond the OpenAI-compatible
  chat-completions profile are not supported.
- Accounts have no MFA, password recovery, rate limiting, or GUI management.
- Visual Output has no host capability bridge or artifact import/export.
- VTT is not a complete tabletop or GURPS implementation; live campaign state
  is not persisted and LAN hosting uses unencrypted HTTP on trusted networks.
- Model-to-model capability calls require explicit manifest permissions;
  current model manifests do not automatically call `recall`.
- Memory compaction, vector retrieval, and complete memory-write enforcement
  remain unfinished.
- The package CLI has no publishing service; package installs need compatible
  weights and Ollama.

## Documentation

- [Setup guide](./setup.md)
- [Account registry and PUPC](./docs/account-registry.md)
- [Remote models](./docs/remote-models.md)
- [Agent skills](./docs/agent-skills.md)
- [Interoperability](./docs/agent-interoperability.md)
- [Visual Output](./docs/visual-output.md)
- [Virtual Tabletop](./docs/vtt.md)
- [Voice status](./docs/voice.md)

<details>
<summary>Architecture decisions (ADR-0001 through ADR-0021)</summary>

- [ADR-0001 — AssiStuff and Noredur coexistence](./docs/adr/ADR-0001-assistuff-framework-noredur-coexistence.md)
- [ADR-0002 — Declarative configuration](./docs/adr/ADR-0002-declarative-model-configuration.md)
- [ADR-0003 — Self-contained `.nrdpkg` packages](./docs/adr/ADR-0003-self-contained-nrdpkg-model-packages.md)
- [ADR-0004 — Package CLI](./docs/adr/ADR-0004-assistuff-pack-cli.md)
- [ADR-0005 — Capability bus and output chain](./docs/adr/ADR-0005-peer-capability-bus-and-output-chain.md)
- [ADR-0006 — Tabbed GUI](./docs/adr/ADR-0006-distributed-tabbed-gui.md)
- [ADR-0007 — Package signing and provenance](./docs/adr/ADR-0007-ed25519-signing-and-provenance.md)
- [ADR-0008 — Layered memory and residency](./docs/adr/ADR-0008-layered-memory-and-model-residency.md)
- [ADR-0009 — Long-term memory retrieval](./docs/adr/ADR-0009-long-term-memory-retrieval.md)
- [ADR-0010 — Controlled hashtag vocabulary](./docs/adr/ADR-0010-hashtag-controlled-vocabulary.md)
- [ADR-0011 — Model manifests and SVG avatars](./docs/adr/ADR-0011-local-models-and-avatars.md)
- [ADR-0012 — macOS app bundle](./docs/adr/ADR-0012-macos-one-click-app.md)
- [ADR-0013 — Installed Ollama models](./docs/adr/ADR-0013-installed-ollama-models.md)
- [ADR-0014 — Graph configuration and residency](./docs/adr/ADR-0014-graph-configuration-and-ollama-residency-modes.md)
- [ADR-0015 — Remote model APIs](./docs/adr/ADR-0015-remote-model-api-providers.md)
- [ADR-0016 — First-class agent skills](./docs/adr/ADR-0016-first-class-agent-skills.md)
- [ADR-0017 — End-to-end voice](./docs/adr/ADR-0017-end-to-end-voice-pipeline.md)
- [ADR-0018 — PUPC account registry](./docs/adr/ADR-0018-pupc-account-registry.md)
- [ADR-0019 — Visual Output and HTML artifacts](./docs/adr/ADR-0019-visual-output-html-artifacts.md)
- [ADR-0020 — Open agent interoperability](./docs/adr/ADR-0020-open-agent-interoperability.md)
- [ADR-0021 — Virtual Tabletop showcase](./docs/adr/ADR-0021-virtual-tabletop-showcase.md)

</details>
