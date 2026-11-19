# ADR-0017: End-to-end voice pipeline

- **Status:** Accepted
- **Date:** 2026-11-19

## Context

Voice engine settings exist in `config/framework.yaml`, but capture, STT,
speaker authentication, wake-word detection, and TTS are not connected to the
assistant turn lifecycle.

## Decision

- Implement voice stages as replaceable peer adapters/capabilities:
  `voice.wake.listen`, `voice.stt.transcribe`, `voice.auth.identify`, and
  `voice.tts.speak`.
- Use the pipeline: optional wake-word detection → microphone capture →
  optional speaker authentication → STT → normal `Turn`/capability routing →
  final `OutputChain` result → optional TTS.
- Make microphone capture, wake-word listening, speaker authentication, and
  speech playback independently configurable and controllable from the GUI.
- Keep wake-word listening off by default. Make speaker authentication opt-in,
  expose enrollment/deletion controls, and keep voiceprints within the selected
  local profile unless the user explicitly configures otherwise.
- Do not transmit captured audio to a remote service by default. Any remote STT
  option requires explicit provider configuration and clear UI disclosure
  before use.
- Speak only the final result event for the active turn; do not read progress,
  errors, intermediate tool/model output, or duplicate results aloud.
- Support cancellation, device errors, unavailable binaries/models, and
  permission denial with visible status and actionable messages.
- Keep engine adapters behind interfaces so local whisper.cpp/Vosk/Piper
  implementations and any future explicitly selected remote service can be
  substituted without changing the turn/router APIs.

## Consequences

- Add asynchronous audio capture and adapter lifecycle management, capability
  manifests, and profile-scoped enrollment storage.
- Chat, tray, and settings UI need explicit recording/listening/speaking states
  and controls.
- Tests need fake audio devices and fake engine adapters; hardware-backed tests
  remain optional.
- Platform-specific microphone permissions, playback devices, and binary/model
  installation must be documented.

## Implementation status

The local pipeline is implemented: microphone capture, whisper.cpp STT,
profile-scoped Vosk enrollment/verification, opt-in Vosk wake listening, Piper
playback, user-only bus capabilities, CLI input, and Chat integration are
wired. Runtime use still requires installing the configured binaries/models
and granting microphone permission. Hardware-backed behavior depends on those
local assets and is not covered by the automated test suite.
