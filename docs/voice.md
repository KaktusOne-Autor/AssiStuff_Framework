# Voice pipeline

The local voice pipeline is wired through the same `Turn`, capability bus, and
`OutputChain` used for text chat:

```text
optional wake word → microphone → optional speaker check → whisper.cpp
    → normal assistant turn → final result → optional Piper playback
```

Voice capabilities are registered as user-only bus capabilities:
`voice.stt.transcribe`, `voice.auth.identify`, `voice.tts.speak`, and
`voice.wake.listen`. They are not offered as ordinary text-routing targets.
Their `config/skills/voice_*.yaml` manifests declare the capability names,
input/output contracts, and access rules; the dispatcher binds them to the
local adapters.
Audio recognition and synthesis run locally; the transcription becomes a
normal prompt and may be sent to a configured remote model if remote routing
is selected.

## Install Python and OS dependencies

Use the project's supported Python version and install the optional voice
dependencies:

```bash
python -m pip install -e '.[voice,gui]'
```

Install and configure these local assets separately:

- `whisper-cli` from whisper.cpp and a Whisper model file.
- Vosk language and speaker models if speaker authentication or wake-word
  detection is enabled.
- Piper, its voice model and JSON config, and the required espeak-ng data.
- A microphone and an available audio input device. On macOS, grant microphone
  access to the terminal or app hosting AssiStuff.

No models or binaries are downloaded automatically. Set the paths and desired
language, sample rate, and thresholds under `voice:` in
[`config/framework.yaml`](../config/framework.yaml). Paths may be absolute or
relative to the project root. Run `./bin/assistuff --check` to see which
configured prerequisites are missing; absent voice assets do not prevent
text-only startup.

## Use voice

Audio controls are **disabled by default**. Open **Settings** and enable
**Audio controls** to reveal the Chat microphone, voice enrollment, voiceprint
deletion, wake-word, and configured speech-output controls. The choice is
saved in the operating system's AssiStuff application preferences. Disabling
audio hides the controls, stops an active capture, and suppresses speech
output. Explicit CLI options remain available when invoked directly.

### GUI microphone

After enabling audio controls in Settings, open Chat and click **Mic** to
record until silence is detected or the configured maximum duration is
reached. Click again to stop early. The recognized text is inserted into the
normal chat turn. If speaker authentication is enabled, the active profile
must have a voiceprint first.

Use **Enroll voice** to record the configured number of samples for the
active profile. Each sample is limited so the total recorded enrollment audio
does not exceed `enrollment_max_seconds`. Only speaker vectors are persisted;
the captured enrollment audio is discarded. Use **Delete voiceprint** to
remove that profile's vector. Voiceprints are stored under the active profile
in `~/.assistuff/` (or the configured user root), with owner-only file
permissions.

Wake-word listening is disabled by default. Check **Wake word** to opt in for
the current GUI session. It listens locally for one of the configured phrases,
then records and transcribes the command. Uncheck it to stop listening.

### CLI

Transcribe an existing WAV file and run the recognized text as a normal turn:

```bash
./bin/assistuff --audio ./command.wav
```

Record from the default microphone and run the turn:

```bash
./bin/assistuff --mic
```

The CLI returns an actionable setup error if required executables, models,
audio devices, or an enrolled voiceprint are unavailable. CLI voice input
does not enable continuous wake listening.

## Configuration and privacy

- `voice.auth.enabled` controls speaker verification. When enabled, use the
  GUI enrollment control for each profile that will submit voice turns.
- `voice.enabled` controls whether GUI audio controls and TTS output are
  enabled. The default is `false`; the Settings toggle persists independently
  of `config/framework.yaml`.
- `voice.wake.enabled` is a configuration default; GUI wake listening still
  requires explicit opt-in.
- `voice.tts.enabled` controls Piper playback. In the GUI, only the final
  `OutputChain` result is spoken, not intermediate model or skill events.
- Voiceprint JSON contains embeddings rather than raw recordings. Keep the
  user's profile directory private and delete voiceprints when no longer
  needed.
- Audio is processed by the configured local tools. Recognized text follows
  normal model-routing privacy rules and can be sent to a remote provider if
  that provider is selected.

See [ADR-0017](./adr/ADR-0017-end-to-end-voice-pipeline.md) for the design.
