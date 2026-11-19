"""Factory and lifecycle for the local voice stages."""

from __future__ import annotations

import asyncio
import importlib.util
import threading
from pathlib import Path

from assistuff.config.schemas import VoiceConfig

from .audio import AudioClip, load_wav, record_microphone
from .auth import VoiceAuthenticator, VoiceprintStore, voiceprint_root
from .common import VoiceError, configured_path
from .stt import STTAdapter
from .tts import TTSAdapter
from .wake import WakeWordListener


class VoicePipeline:
    def __init__(
        self,
        config: VoiceConfig,
        *,
        project_root: Path,
        user_root: Path,
        profile: str,
    ) -> None:
        self.config = config
        self.project_root = project_root
        self.user_root = user_root
        self.profile = profile
        store = VoiceprintStore(
            voiceprint_root(
                config.auth.voiceprints_dir,
                user_root,
                project_root,
            )
        )
        self.auth = VoiceAuthenticator(
            config.auth,
            sample_rate=config.stt.sample_rate,
            project_root=project_root,
            store=store,
        )
        self.stt = STTAdapter(config.stt, project_root)
        self.tts = TTSAdapter(config.tts, project_root)
        self.wake = WakeWordListener(
            config.wake,
            model_path=config.auth.model_path,
            project_root=project_root,
        )

    def capture(
        self,
        *,
        stop_event: threading.Event | None = None,
        max_record_seconds: float | None = None,
        on_status=None,
    ) -> AudioClip:
        return record_microphone(
            self.config.stt,
            stop_event=stop_event,
            max_record_seconds=max_record_seconds,
            on_status=on_status,
        )

    def capture_enrollment_sample(
        self,
        *,
        stop_event: threading.Event | None = None,
    ) -> AudioClip:
        sample_limit = self.config.auth.enrollment_max_seconds / self.config.auth.enrollment_samples
        return self.capture(
            stop_event=stop_event,
            max_record_seconds=min(self.config.stt.max_record_seconds, sample_limit),
        )

    async def transcribe_clip(self, clip: AudioClip) -> str:
        await asyncio.to_thread(self.auth.verify, self.profile, clip)
        return await self.stt.transcribe_clip(clip)

    async def transcribe_file(self, path: str | Path) -> str:
        if self.config.auth.enabled:
            clip = await asyncio.to_thread(
                load_wav,
                path,
                self.config.stt.sample_rate,
            )
            await asyncio.to_thread(self.auth.verify, self.profile, clip)
        return await self.stt.transcribe_file(path)

    def extract_enrollment_sample(self, clip: AudioClip) -> list[float]:
        return self.auth.extract_embedding(clip)

    def save_enrollment(self, samples: list[list[float]]) -> None:
        self.auth.save_enrollment(self.profile, samples)

    def listen_for_wake(
        self,
        stop_event: threading.Event,
        *,
        timeout_seconds: float | None = None,
    ) -> str | None:
        return self.wake.listen(stop_event, timeout_seconds=timeout_seconds)

    def diagnostics(self) -> dict[str, tuple[bool, str]]:
        results: dict[str, tuple[bool, str]] = {}
        results["microphone"] = (
            (True, "sounddevice available")
            if importlib.util.find_spec("sounddevice")
            else (False, "install the voice extra for sounddevice")
        )
        results["audio processing"] = (
            (True, "numpy available")
            if importlib.util.find_spec("numpy")
            else (False, "install the voice extra for numpy")
        )
        results["whisper.cpp"] = _check_call(self.stt.validate_setup)

        if self.config.auth.enabled or self.config.wake.enabled:
            if importlib.util.find_spec("vosk") is None:
                results["Vosk"] = (False, "install the voice extra for Vosk")
            else:
                results["Vosk"] = (True, "Vosk Python package available")
        else:
            results["Vosk"] = (True, "speaker verification and wake word disabled")

        if self.config.auth.enabled or self.config.wake.enabled:
            language_model = configured_path(self.config.auth.model_path, self.project_root)
            results["Vosk language model"] = (
                (True, str(language_model))
                if language_model.is_dir()
                else (False, f"directory not found: {language_model}")
            )

        if self.config.auth.enabled:
            speaker_model = configured_path(
                self.config.auth.speaker_model_path,
                self.project_root,
            )
            results["Vosk speaker model"] = (
                (True, str(speaker_model))
                if speaker_model.is_dir()
                else (False, f"directory not found: {speaker_model}")
            )
            results["voiceprint"] = (
                (True, f"enrolled for profile {self.profile}")
                if self.auth.has_voiceprint(self.profile)
                else (False, f"enroll a voiceprint for profile {self.profile}")
            )
        else:
            results["voice authentication"] = (True, "disabled")

        if self.config.wake.enabled:
            results["wake word"] = (True, "enabled; opt in from Chat to listen")
        else:
            results["wake word"] = (True, "disabled")

        if self.config.tts.enabled:
            results["Piper TTS"] = _check_call(self.tts.validate_setup)
        else:
            results["Piper TTS"] = (True, "disabled")
        return results


def _check_call(callback) -> tuple[bool, str]:
    try:
        callback()
    except (OSError, VoiceError) as exc:
        return False, str(exc)
    return True, "ready"
