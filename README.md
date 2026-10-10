# AssiStuff Framework

AssiStuff is a local-first Python assistant framework. It brings together
Ollama-backed models, skills, a capability bus, layered memory, a tabbed Qt
desktop application, and the historical `.nrdpkg` model package format.

AssiStuff is additive alongside Noredur. Noredur's name and `src/noredur/`
remain unchanged; AssiStuff imports must not depend on that tree. See
[README-assistuff.md](./README-assistuff.md) and [docs/adr/](./docs/adr/) for
the coexistence boundary and architecture decisions.

## Requirements

- Python 3.11–3.13 (use `uv` or `pyenv`; Python 3.14 is not in the tested
  support range).
- Ollama for model-backed chat and utility roles.
- macOS SQLite with FTS5 for long-term memory search.
- Optional: PyQt6 for desktop UI, `zstandard` and `cryptography` for packaging
  and signatures, and voice tools/models for the planned voice workflow.

## Install and first run

From the project root:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev,gui,voice,pack]'
```

Start Ollama and pull the models configured for your installation. Check the
current model tags in `config/models/*.yaml` and utility roles in
`config/framework.yaml`; tags must match `ollama list`.

```bash
ollama serve
ollama list
./bin/assistuff --check
./bin/assistuff --skill calculator --skill-input "2 + 2"
./bin/assistuff --ask "2 + 2"
```

The local inventory recorded for this project includes:
`mathstral:7b`, `FableForge-AI/nexus-science:latest`, `qwen2-math:7b`,
`aya-expanse:8b`, `qwen2.5-coder:7b`, `qwen2.5:3b`, `qwen2.5:7b`, and
`phi3:latest`. To restore any one that is missing, pull it by its exact Ollama
tag, for example:

```bash
ollama pull qwen2.5:3b
ollama pull qwen2.5:7b
```

The check command loads and validates the manifests, creates the user data
directories, and reports Ollama reachability and missing configured model tags.
The calculator command should print `4`. `--ask` runs the full route/execute/
memory pipeline and requires the configured utility and target models in
Ollama.

The two executable wrappers are `bin/assistuff` and `bin/assistuff-pack`. They
prefer `.venv/bin/python` when it exists, otherwise they use `python3` from
`PATH`.

## Desktop application

Install the GUI dependencies from the optional `gui` extra, then launch either
from Finder or from the project root:

```bash
open AssiStuff.app
# or
./bin/assistuff
```

Keep `AssiStuff.app` in the project directory; its launcher resolves the project
relative to the bundle. Log output is written to
`~/.assistuff/logs/gui-launch.log`. Tray-only mode is available with
`./bin/assistuff --tray-only`.

The GUI has eight tabs:

- **Chat** — send a query to the configured dispatcher. `output_chain.stream_to_gui`
  controls streamed event previews. The microphone control is not connected to
  STT yet.
- **Models** — inspect installed packages and configured manifests. Select a
  model manifest, then choose or clear its SVG avatar. Chosen SVG files are
  copied to `assets/avatars/` and the manifest is updated.
- **Tasks** — task panel shell; `TaskGraph` integration remains to be completed.
- **Memory** — inspect/search memory UI; editing the tag vocabulary in-place
  remains to be implemented.
- **Skills** — inspect available registered skills.
- **Trace** — inspect capability execution traces; graph rendering of the call
  stack remains to be implemented.
- **Settings** — current profile, theme, stream, and telemetry settings.
- **Plugins** — inspect the plugin surface.

Telemetry is a bottom dock, hidden by default. Use **View → Toggle telemetry
dock** (`Ctrl+T`) to show or hide it. **View → Reload panels** (`Ctrl+R`)
reloads panels that provide a `reload()` method. The UI theme setting exists;
applying the configured `qt-material` theme consistently remains outstanding.

## CLI reference

Run `./bin/assistuff --help` for options. Common commands:

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
./bin/assistuff --headless
```

`--model` accepts a configured manifest ID or a configured runtime tag.
`--profile ID` selects a profile for memory, skill, ask, and GUI operations.
`--debug` enables debug logging.
`--install-pkg FILE` is the convenience path for package installation from the
main CLI; use `assistuff-pack install` when you need to provide signing keys or
other package-specific options.

Memory CLI operations take a command after `--memory`:

```bash
./bin/assistuff --memory tags
./bin/assistuff --list-tags default
./bin/assistuff --memory append "Working on AssiStuff" --tags "#project,#work"
./bin/assistuff --memory search "AssiStuff"
./bin/assistuff --memory reindex
```

Memory is kept under `~/.assistuff/profiles/<profile>/`: working state is
in-memory, short-term messages and todos use SQLite, long-term notes use
Markdown plus FTS5/time indexes, and the dossier layer stores structured
profile information. Notes use the vocabulary in the `memory.md` header and
support dynamic tags. Vector search, forced reindex, fuzzy tag matches,
`memory audit-tags`, compaction, planner-connected unknown-tag retry, and
in-panel tag editing are not complete.

The parser also exposes `--audio` and `--mic`, but those options are not wired
into the execution flow yet. The end-to-end voice workflow described below is
planned, not currently usable.

## Models and configuration

Runtime configuration is declarative:

- `config/framework.yaml` — runtime, utility roles, voice, memory, profiles,
  tasks, access control, UI, telemetry, hardware, and output chain.
- `config/models/*.yaml` — model tags, roles, capabilities, permissions,
  routing hints, memory access, provenance, prompts, and optional avatar path.
- `config/skills/*.yaml` — skill capabilities, permissions, interop, and
  implementation module.
- `config/personalities/*.yaml` — personality prompt paths and applicability.
- `config/access/pupc.yaml` — six user permission levels.
- `prompts/roles/` — model role prompts referenced by `prompts.system`.
- `prompts/identities/` — default and alternate identity prompts.

The `router`, `planner`, `mpa`, and optional `compiler` utility roles are
configured under `runtime.utility_models`; they are not special hardcoded model
IDs. Keep `prompts/noredur_identity.txt` alongside the newer identity Markdown
files for compatibility. Config paths can be overridden at runtime with
`ASSISTUFF_HOME`; the default user data root is `~/.assistuff/`.

## Plugins

Plugins are explicitly enabled Python modules in the configured plugin
directory (default: `plugins/`). Each plugin consists of `<id>.py` and
`<id>.json`. Example `plugins/greeting.py`:

```python
def run(value, context):
    return f"Hello, {value.strip() or context.profile}!"
```

Example `plugins/greeting.json`:

```json
{
  "skill": "greeting",
  "permission": "greeting"
}
```

Enable it in `config/framework.yaml`:

```yaml
tasks:
  plugin_dir: plugins
  enabled_plugins: [greeting]
```

Restart AssiStuff to load the plugin, then call it:

```bash
./bin/assistuff --skill greeting --skill-input "there"
```

A plugin must export `run(value, context)` and return a string. Plugin code
executes inside the application process with the framework's Python
permissions: enable only plugins you trust. Plugin loading is implemented in
`assistuff/skills/plugins/loader.py`.

## Build and install `.nrdpkg` model packages

Install packaging dependencies with `python -m pip install -e '.[pack]'`.
Scaffold a package:

```bash
./bin/assistuff-pack init packages/mathstral \
  --id mathstral --name Mathstral --version 1.0.0
```

Review and edit `packages/mathstral/manifest.yaml`: ensure model license,
provenance, redistribution policy, capabilities, and runtime options are
accurate. Put a redistributable GGUF model file in `packages/mathstral/weights/`
and use a compatible GGUF format in the manifest. Then lint and build:

```bash
./bin/assistuff-pack lint packages/mathstral
./bin/assistuff-pack build packages/mathstral -o dist
./bin/assistuff-pack verify dist/mathstral-1.0.0.nrdpkg
```

Weight resolver forms are `file:<path>`, `hf:<repo_id>`, and
`ollama:<tag>`. For example, a compatible local GGUF source can be copied during
build with:

```bash
./bin/assistuff-pack build packages/mathstral -o dist \
  --weights-from file:/path/to/model.gguf
```

Create a signing key once and sign packages during build:

```bash
./bin/assistuff-pack keys generate --name dev
./bin/assistuff-pack build packages/mathstral -o dist \
  --sign-key ~/.assistuff/keys/dev.key
./bin/assistuff-pack verify dist/mathstral-1.0.0.nrdpkg \
  --public-key ~/.assistuff/keys/dev.pub
./bin/assistuff-pack install dist/mathstral-1.0.0.nrdpkg \
  --public-key ~/.assistuff/keys/dev.pub
```

Other package commands:

```bash
./bin/assistuff-pack list
./bin/assistuff-pack uninstall mathstral --version 1.0.0
./bin/assistuff-pack export mathstral --version 1.0.0 --to packages/exported
./bin/assistuff-pack keys list
```

Unsigned development packages can be installed with `--allow-unsigned`; do not
use this for untrusted packages. `assistuff-pack sign` is currently a
placeholder; pass `--sign-key` when building instead. Package install creates
an Ollama model from bundled GGUF weights and updates
`~/.assistuff/registry.json`.

**Ollama resolver limitation:** `ollama:<tag>` currently copies Ollama's
internal blobs, but the installer expects a `.gguf` file when creating the
Ollama model. This source can therefore fail at install time; use GGUF weights
until that limitation is fixed. Model redistribution is subject to the
upstream license and provenance restrictions. There is no `publish` command
yet; package hosting is undecided. Dedicated packaging documentation remains
to be written; see [ADR-0003](./docs/adr/ADR-0003-self-contained-nrdpkg-model-packages.md),
[ADR-0004](./docs/adr/ADR-0004-assistuff-pack-cli.md), and
[ADR-0007](./docs/adr/ADR-0007-ed25519-signing-and-provenance.md).

## Capability bus and output chain

Models and skills register as capabilities; callers address capabilities
rather than depending on a concrete model implementation. Bus policy supports
maximum hops, TTL, caller allowlists (`accepts_calls_from`), and access
`min_level`. `Trace` tracks execution; `OutputChain` emits, subscribes,
collects, and stores final results. GUI, log, and TTS emitters are present.

Remaining bus work includes tests for two-model `interop.can_call` enforcement,
uniform use of `output_chain.stream_to_gui`, and trace call-stack graph
rendering. Voice TTS subscription should speak only the final result event;
voice integration is not complete.

## Voice setup and current status

Voice settings are declarative under `voice:` in `config/framework.yaml`.
The intended peer capabilities are:

- `voice.stt.transcribe` — whisper.cpp STT.
- `voice.tts.speak` — Piper TTS and configured audio player.
- `voice.auth.identify` — Vosk speaker identification.
- `voice.wake.listen` — Vosk wake-word detection.

Configure paths for whisper.cpp, its model, Piper, the Piper voice and
espeak-ng data, Vosk language and speaker models, plus the audio player. The
optional `voice` extra supplies `sounddevice` and `vosk`:

```bash
python -m pip install -e '.[voice]'
```

The framework YAML currently provides configuration fields for:

- STT: `binary_path`, `model_path`, `language`, `sample_rate`,
  `max_record_seconds`, `silence_timeout_seconds`, and `speech_threshold`.
- Speaker authentication: enable flag, Vosk acoustic and speaker model paths,
  profile voiceprints directory, similarity and margin thresholds, and
  enrollment sample/duration limits.
- Wake-word listening: enable flag, phrase list, sample rate, frame size, and
  detection timeout.
- TTS: Piper binary, voice and rate, phonemization library and espeak-ng data
  paths, model/config paths, player path, and enable flag.

The STT/TTS/auth/wake adapters and factory, voice skill manifests, capability
registration, chat microphone wiring, and the wake → STT → Turn → TTS flow are
not yet implemented. Installing the Python extra alone does not make this
workflow operational.

Once those adapters are implemented, the intended local setup is to install
whisper.cpp and its selected model, Piper plus a compatible voice and
espeak-ng data, and Vosk language/speaker models, then set the paths in
`config/framework.yaml`. Voice enrollment and wake-word use are not currently
available commands.

## Current known gaps

- Voice adapters/capabilities and Chat microphone integration.
- Tasks panel to `TaskGraph` wiring.
- Consistent GUI stream switch handling and trace call-stack graph.
- `assistuff-pack sign` in-place signing, publish stub, shipped verification
  key, and key-rotation documentation.
- Model residency warm-up at startup.
- Dossier compiler trigger from memory writes.
- Memory tag audit, compaction, fuzzy/forced reindex, and GUI tag editor.
- Vector retrieval.
- Complete GUI styling from the configured theme.

## Architecture decision records

ADRs 0001–0010 are the original migration decisions; 0011 onward records
subsequent decisions.

1. [ADR-0001 — AssiStuff Framework alongside Noredur](./docs/adr/ADR-0001-assistuff-framework-noredur-coexistence.md)
2. [ADR-0002 — Declarative model, skill, and runtime configuration](./docs/adr/ADR-0002-declarative-model-configuration.md)
3. [ADR-0003 — Self-contained `.nrdpkg` model packages](./docs/adr/ADR-0003-self-contained-nrdpkg-model-packages.md)
4. [ADR-0004 — `assistuff-pack` package CLI](./docs/adr/ADR-0004-assistuff-pack-cli.md)
5. [ADR-0005 — Peer capability bus and output chain](./docs/adr/ADR-0005-peer-capability-bus-and-output-chain.md)
6. [ADR-0006 — Distributed tabbed desktop GUI](./docs/adr/ADR-0006-distributed-tabbed-gui.md)
7. [ADR-0007 — Package signing and provenance](./docs/adr/ADR-0007-ed25519-signing-and-provenance.md)
8. [ADR-0008 — Layered memory and model residency](./docs/adr/ADR-0008-layered-memory-and-model-residency.md)
9. [ADR-0009 — Long-term memory retrieval](./docs/adr/ADR-0009-long-term-memory-retrieval.md)
10. [ADR-0010 — Dynamic bilingual hashtag vocabulary](./docs/adr/ADR-0010-hashtag-controlled-vocabulary.md)
11. [ADR-0011 — Local model manifests and SVG avatars](./docs/adr/ADR-0011-local-models-and-avatars.md)
12. [ADR-0012 — One-click macOS application bundle](./docs/adr/ADR-0012-macos-one-click-app.md)
13. [ADR-0013 — Configure the installed Ollama inventory](./docs/adr/ADR-0013-installed-ollama-models.md)
