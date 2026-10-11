# AssiStuff Framework

AssiStuff is a local-first Python assistant framework built around Ollama,
declarative model and skill manifests, a capability bus, and profile-based
memory. It includes a PyQt desktop application and retains the historical
`.nrdpkg` model package format.

> **Development status:** AssiStuff is under active development. CLI skills,
> local model configuration, basic chat dispatch, package tooling, and memory
> storage are present. Voice integration and several GUI/memory integrations
> are not complete; see [Current limitations](#current-limitations).

AssiStuff coexists with Noredur. The `src/noredur/` tree is retained unchanged,
and AssiStuff does not depend on it. See [README-assistuff.md](./README-assistuff.md)
and the [architecture decision records](#architecture-decisions).

## Requirements

- Python 3.11–3.13
- [Ollama](https://ollama.com/) for model-backed requests
- macOS/Linux with SQLite FTS5 for long-term memory search
- Optional: GUI, package, and voice dependencies installed via extras below

## Install

From the project directory, create a Python 3.11–3.13 environment and install
the desired extras:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev,gui,voice,pack]'
```

Start Ollama in a separate terminal if it is not already running:

```bash
ollama serve
```

The model tags used by this checkout are configured in `config/models/*.yaml`
and `config/framework.yaml`. Pull the tags you intend to use with `ollama pull
<tag>`, then check configuration and run the calculator smoke test:

```bash
ollama list
./bin/assistuff --check
./bin/assistuff --skill calculator --skill-input "2 + 2"
```

The calculator should print `4`. Run `./bin/assistuff --ask "2 + 2"` to test
model-backed routing and chat; all model tags named in the utility-role
configuration need to be installed for the full pipeline.

The `bin/assistuff` and `bin/assistuff-pack` wrappers use `.venv/bin/python`
when present, otherwise `python3` from `PATH`.

## Start the desktop app

Install the `gui` extra, then launch the GUI from the project directory:

```bash
./bin/assistuff
# macOS app bundle:
open AssiStuff.app
```

Keep `AssiStuff.app` alongside the project files; the bundle locates the
project relative to itself. Logs are written to
`~/.assistuff/logs/gui-launch.log`. Use `./bin/assistuff --tray-only` to start
the tray without the main window.

The application has Chat, Models, Tasks, Memory, Skills, Trace, Settings, and
Plugins tabs. The Models tab displays configured manifests and supports
choosing an SVG avatar; selected files are copied to `assets/avatars/` and the
model manifest is updated. The telemetry dock is hidden by default and can be
toggled from **View → Toggle telemetry dock** (`Ctrl+T`). **View → Reload
panels** (`Ctrl+R`) calls `reload()` on panels that provide it.

The planned Mermaid-like model/skill graph editor and selectable Hot-plug /
Selected-for-background Ollama residency modes are specified in
[ADR-0014](./docs/adr/ADR-0014-graph-configuration-and-ollama-residency-modes.md);
they are not implemented yet.

## CLI

Run `./bin/assistuff --help` for all options. Common commands:

```bash
./bin/assistuff --check
./bin/assistuff --list-models
./bin/assistuff --list-skills
./bin/assistuff --prompt "Explain this briefly" --model qwen2-5-7b
./bin/assistuff --ask "What is 2 + 2?"
./bin/assistuff --ask "What is 2 + 2?" --stream
./bin/assistuff --skill calculator --skill-input "2 + 2"
./bin/assistuff --bus-test
./bin/assistuff --unload qwen2.5:7b
./bin/assistuff --install-pkg dist/example-1.0.0.nrdpkg
```

`--model` accepts a configured model ID or runtime tag. `--profile ID` selects
the profile for supported operations; `--debug` enables debug logging.
`--headless` suppresses GUI launch when no command is selected.

### Memory commands

Memory is profile-scoped beneath `~/.assistuff/profiles/` (or
`$ASSISTUFF_HOME/profiles/` when overriding the user data root):

```bash
./bin/assistuff --memory tags
./bin/assistuff --list-tags default
./bin/assistuff --memory append "Working on AssiStuff" --tags "#project,#work"
./bin/assistuff --memory search "AssiStuff"
./bin/assistuff --memory reindex
```

The memory implementation has working state in-process, short-term messages
and todos in SQLite, long-term Markdown notes with FTS5/time indexes, and a
structured dossier. Turns record the user/assistant exchange to short-term
memory; generated summaries may be appended to long-term memory. The `recall`
skill can search long-term memory when explicitly invoked:

```bash
./bin/assistuff --skill recall --skill-input "AssiStuff"
```

**Models do not currently read memory automatically.** The model adapter sends
the query and model prompt to Ollama; it does not add short-term history,
retrieved notes, or dossier context. Although manifests declare `memory.reads`
and `dossier_access`, those declarations are not currently wired into runtime
prompt construction. Model manifests also have `interop.can_call: []`, so a
model cannot call the `recall` skill through the capability bus by default.
Skills and plugins receive a `SkillContext` containing the profile's memory
store, so a memory-aware skill can read or write it directly.

Tags are stored in the long-term memory Markdown header and can be added
dynamically by the memory/tag code. Vector retrieval, fuzzy tag matching,
forced reindex, tag auditing, compaction, planner-connected unknown-tag retry,
and in-panel tag editing are not complete.

## Configuration

Configuration is YAML-based:

- `config/framework.yaml` — Ollama, utility roles, voice, memory, profiles,
  tasks, access, UI, telemetry, hardware, and output-chain settings.
- `config/models/*.yaml` — model tag, role, capabilities, routing, access,
  interop, memory declarations, provenance, prompt paths, and avatar.
- `config/skills/*.yaml` — skill capability and implementation manifests.
- `config/personalities/*.yaml` — personality prompt paths.
- `config/access/pupc.yaml` — six access levels.
- `prompts/roles/` and `prompts/identities/` — model prompts and identities.

Utility roles (`router`, `planner`, `mpa`, and optional `compiler`) are set in
`runtime.utility_models` in `config/framework.yaml`. The default user root is
`~/.assistuff`; override it with `ASSISTUFF_HOME`.

## Add a plugin

A plugin is an explicitly enabled `<id>.py` module and `<id>.json` manifest in
the configured plugin directory (default `plugins/`). Create
`plugins/greeting.py`:

```python
def run(value, context):
    return f"Hello, {value.strip() or context.profile}!"
```

Create `plugins/greeting.json`:

```json
{
  "skill": "greeting",
  "permission": "greeting"
}
```

Enable the plugin in `config/framework.yaml`:

```yaml
tasks:
  plugin_dir: plugins
  enabled_plugins: [greeting]
```

Restart the application and invoke it:

```bash
./bin/assistuff --skill greeting --skill-input "there"
```

Plugins execute Python code in the application process and have the
permissions of the running user. Enable only code you trust. A plugin's
`run(value, context)` must return a string.

## Build and install `.nrdpkg` packages

Install the `pack` extra, scaffold a package, and edit its manifest:

```bash
python -m pip install -e '.[pack]'
./bin/assistuff-pack init packages/example \
  --id example --name Example --version 1.0.0
```

Set accurate license, provenance, redistribution, runtime, and capability
metadata in `packages/example/manifest.yaml`. Add compatible, redistributable
GGUF weights to `packages/example/weights/`, then lint, build, and verify:

```bash
./bin/assistuff-pack lint packages/example
./bin/assistuff-pack build packages/example -o dist
./bin/assistuff-pack verify dist/example-1.0.0.nrdpkg
```

Packages can be signed during build with an Ed25519 key:

```bash
./bin/assistuff-pack keys generate --name dev
./bin/assistuff-pack build packages/example -o dist \
  --sign-key ~/.assistuff/keys/dev.key
./bin/assistuff-pack verify dist/example-1.0.0.nrdpkg \
  --public-key ~/.assistuff/keys/dev.pub
./bin/assistuff-pack install dist/example-1.0.0.nrdpkg \
  --public-key ~/.assistuff/keys/dev.pub
```

The package CLI also supports `list`, `uninstall`, `export`, and `keys list`;
use `./bin/assistuff-pack --help` for syntax. Unsigned development packages
require `--allow-unsigned` when installed. Protect private signing keys and
verify packages with a trusted public key.

Weight source forms are `file:<path>`, `hf:<repo_id>`, and `ollama:<tag>`.
**Known limitation:** the Ollama resolver copies Ollama's internal blobs, but
the installer currently expects a `.gguf` weight file when creating the
Ollama model. Use GGUF weights for package installation. `assistuff-pack sign`
is currently a placeholder; sign while building with `--sign-key`. There is no
publish command yet. Follow upstream licenses and redistribution requirements.

## Capability bus and output chain

Models and skills register as capabilities. The bus routes capability calls
and applies hop, caller, and access-level restrictions. `Trace` records
execution, and `OutputChain` publishes events to subscribers such as GUI and
logging emitters.

`interop.can_call` controls which capabilities a model may call. Calls to
memory-aware skills are possible only when explicitly allowed by configuration
and when those skills are registered. Current model manifests have empty
`can_call` lists, so models cannot call `recall` automatically.

## Voice status

`config/framework.yaml` includes settings for whisper.cpp STT, Vosk speaker
authentication and wake-word detection, and Piper TTS. Install the Python
dependencies with `python -m pip install -e '.[voice]'` and configure the
binary/model paths for local voice engines.

The voice adapters, factory, skill manifests, capability registration, and
Chat microphone integration are not implemented yet. The configured voice
settings and optional dependencies alone do not provide transcription,
authentication, wake-word detection, or speech output. The CLI's `--audio`
and `--mic` options are also not connected to a voice pipeline.

## Current limitations

- Models do not receive memory context, and manifest memory-read declarations
  are not enforced or injected at runtime.
- Voice pipeline and microphone integration are not implemented.
- Tasks panel is not connected to a task graph; Memory panel tag editing and
  Trace call-stack graph are unfinished.
- Vector retrieval, fuzzy/forced reindex, tag audit, memory compaction, and
  automatic dossier compilation are unfinished.
- Model residency warm-up and complete GUI theme application are unfinished.
- Mermaid-like graph configuration and the Hot-plug /
  Selected-for-background residency modes are specified but unfinished.
- In-place package signing, publishing, bundled verification key, and key
  rotation workflow are unfinished.

## Architecture decisions

- [ADR-0001 — AssiStuff and Noredur coexistence](./docs/adr/ADR-0001-assistuff-framework-noredur-coexistence.md)
- [ADR-0002 — Declarative configuration](./docs/adr/ADR-0002-declarative-model-configuration.md)
- [ADR-0003 — Self-contained `.nrdpkg` packages](./docs/adr/ADR-0003-self-contained-nrdpkg-model-packages.md)
- [ADR-0004 — `assistuff-pack` CLI](./docs/adr/ADR-0004-assistuff-pack-cli.md)
- [ADR-0005 — Capability bus and output chain](./docs/adr/ADR-0005-peer-capability-bus-and-output-chain.md)
- [ADR-0006 — Tabbed GUI](./docs/adr/ADR-0006-distributed-tabbed-gui.md)
- [ADR-0007 — Package signing and provenance](./docs/adr/ADR-0007-ed25519-signing-and-provenance.md)
- [ADR-0008 — Layered memory and residency](./docs/adr/ADR-0008-layered-memory-and-model-residency.md)
- [ADR-0009 — Long-term memory retrieval](./docs/adr/ADR-0009-long-term-memory-retrieval.md)
- [ADR-0010 — Controlled hashtag vocabulary](./docs/adr/ADR-0010-hashtag-controlled-vocabulary.md)
- [ADR-0011 — Model manifests and SVG avatars](./docs/adr/ADR-0011-local-models-and-avatars.md)
- [ADR-0012 — macOS app bundle](./docs/adr/ADR-0012-macos-one-click-app.md)
- [ADR-0013 — Installed Ollama models](./docs/adr/ADR-0013-installed-ollama-models.md)
- [ADR-0014 — Graph configuration and Ollama residency modes](./docs/adr/ADR-0014-graph-configuration-and-ollama-residency-modes.md)
