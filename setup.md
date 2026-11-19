# Setup

Setup guide for **AssiStuff 1.0.1-beta** (Python package version `1.0.1b1`).
This guide covers local development, the wired voice pipeline, remote API
chat, portable instruction skills, MCP stdio tools, and HTML Visual Output.
Feature-specific guides describe their current limitations.

## 1. Install Python dependencies

Use Python 3.11–3.13 (the examples use Python 3.12):

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev,gui,voice,pack]'
```

For a smaller install, choose only what you need:

```bash
python -m pip install -e .
python -m pip install -e '.[gui]'
python -m pip install -e '.[pack]'
python -m pip install -e '.[voice]'
```

## 2. Configure local models

Install Ollama. In a separate terminal, start its service and verify the models
you want are present:

```bash
ollama serve
ollama list
```

Check `config/models/*.yaml` and `runtime.utility_models` in
`config/framework.yaml`. Pull any missing tags using their exact configured
names:

```bash
ollama pull qwen2.5:3b
ollama pull qwen2.5:7b
```

Validate the project and run a no-model skill:

```bash
./bin/assistuff --check
./bin/assistuff --skill calculator --skill-input '2 + 2'
```

For the full model pipeline, run `./bin/assistuff --ask "2 + 2"` after all
utility/model tags are installed.

## 3. Launch the GUI

```bash
./bin/assistuff
```

On macOS, the app bundle can be opened from Finder or with:

```bash
open AssiStuff.app
```

Keep the bundle in the project directory. GUI logs are written to
`~/.assistuff/logs/gui-launch.log`.

The **Graph** tab edits model/skill capability permissions and residency
configuration. Hot-plug is the default for constrained hardware. Use
Selected-for-background only when the machine can keep all selected models
loaded; the combined number of pinned and selected models must be at most
`max_loaded`. Restart AssiStuff after saving changes. Models listed in
`runtime.residency.pinned` are also warmed at startup and protected from
eviction in either mode.

The **Visual Output** tab can generate and preview self-contained HTML. The
viewer blocks network requests, external navigation, downloads, and persistent
browser storage, but generated scripts still run locally. Generation uses the
configured model route; do not include secrets in artifact prompts.

The **VTT** tab uses the configured assistant route to build a playable map,
initial NPCs, campaign history, and objective. View it as a playable tile map
or an illustrated map. The active AI GM interprets declared actions, calls for
local 3d6 checks when needed, narrates their results, and can apply validated
world updates. The History tab generates campaign history, keeps a session
chronicle, and can create an AI recap; character backstories can be generated
and saved with profile-local character sheets. In the **Multiplayer** tab,
start a LAN host and share its URL and join code with players on a trusted
network. LAN uses
unencrypted HTTP; never expose it to the public internet. The host handles all
AI requests. Configure map size under `vtt` in `config/framework.yaml`. Map and
story generation use the selected local or remote model route; see
[docs/vtt.md](./docs/vtt.md) for full play and security instructions.

## 4. Create an account

The application starts as a level-0 guest until an account is created. The
first account becomes the local administrator; its password is entered at a
hidden prompt:

```bash
./bin/assistuff --account-create owner
./bin/assistuff --account-create player --admin-account owner --profile player
./bin/assistuff --account-list --admin-account owner
```

The GUI prompts for sign-in when accounts exist. CLI requests use
`--account owner`; account administration uses `--admin-account owner`.
Account data is stored in `~/.assistuff/accounts.db`. Review
[docs/account-registry.md](./docs/account-registry.md) for security
limitations and management commands.

## 5. Set up plugins and portable skills

The current plugin loader uses trusted in-process Python modules. Add a module
and JSON manifest in the directory configured by `tasks.plugin_dir`, then add
the plugin ID to `tasks.enabled_plugins`. See the working example in
[README.md](./README.md#add-a-plugin). Enable only code you trust; this
mechanism is not a sandbox.

Instruction-only portable packages can be installed and enabled by an
administrator:

```bash
./bin/assistuff --skill-install ./skills/my-helper --admin-account owner
./bin/assistuff --skill-enable my-helper --admin-account owner
./bin/assistuff --list-skills
```

Imported packages start disabled and executable implementations are rejected.
To expose registered skills to an MCP client, run
`./bin/assistuff --mcp` using the stdio transport. See
[docs/agent-skills.md](./docs/agent-skills.md).

## 6. Remote API providers

OpenAI-compatible Chat Completions inference is supported. Configure an
endpoint profile and remote model manifest, then provide credentials through
an environment variable. Never store API keys in YAML or source control.
Review the provider's data disclosure, retention, quota, and cost terms before
routing private prompts remotely. See [docs/remote-models.md](./docs/remote-models.md).

## 7. Voice pipeline

Install `voice` (and `gui` for desktop controls) with the Python dependencies
above. Voice also needs external local assets: whisper.cpp's `whisper-cli` and
a model, Vosk language/speaker models, and Piper with a voice, config, and
espeak-ng data. Configure all paths under `voice:` in
`config/framework.yaml`; these large assets are not downloaded automatically.
Grant microphone permission to the terminal or app on macOS.

Run `./bin/assistuff --check` to diagnose missing prerequisites. Use
`--audio ./command.wav` for an existing WAV or `--mic` to record from the
default microphone. GUI audio is disabled by default; open
**Settings → Enable audio controls** to reveal Chat microphone,
voice enrollment/deletion, and opt-in wake-word controls. This preference is
saved in the operating system's AssiStuff settings. With speaker authentication
enabled, enroll the active profile before using voice. Wake listening is off
until explicitly enabled. Piper speaks final GUI turn results when configured
and ready. Recognized text uses normal model routing and may be sent to a
selected remote provider; audio capture and voice processing use the configured
local tools. See [docs/voice.md](./docs/voice.md) for details.

## 8. Data and credentials

By default, user state is stored under `~/.assistuff/`. Set `ASSISTUFF_HOME`
before launching to use a different user data root. Keep profiles and
credentials private; do not commit them into this repository.

## 9. Troubleshooting

- `./bin/assistuff --check` reports configuration issues and whether Ollama is
  reachable.
- Use `./bin/assistuff --debug ...` for more detailed logs.
- If an Ollama tag is missing, compare `ollama list` with the model manifest
  `runtime.tag` values and utility-role tags.
- A healthy Ollama `/api/tags` response does not guarantee inference works.
  If a request times out or reports a capability TTL, confirm the selected
  model is responsive with `ollama run <configured-model-tag>` and review
  model selection in the Trace panel.
- For GUI startup issues, inspect `~/.assistuff/logs/gui-launch.log`.
- The package builder requires the `pack` extra. Installing a model package
  that calls `ollama create` also requires a running Ollama service and
  compatible GGUF weights.

See [README.md](./README.md) for CLI commands, package instructions, and
current limitations.
