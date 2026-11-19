"""Opt-in local Vosk wake-word listener."""

from __future__ import annotations

import importlib
import json
import queue
import re
import threading
import time
from pathlib import Path

from assistuff.config.schemas import WakeWordConfig

from .common import VoiceError, configured_path


class WakeWordListener:
    def __init__(
        self,
        config: WakeWordConfig,
        *,
        model_path: str,
        project_root: Path,
    ) -> None:
        self.config = config
        self.model_path = model_path
        self.project_root = project_root

    def listen(
        self,
        stop_event: threading.Event,
        *,
        timeout_seconds: float | None = None,
    ) -> str | None:
        try:
            sd = importlib.import_module("sounddevice")
            vosk = importlib.import_module("vosk")
        except ImportError as exc:
            raise VoiceError(
                "wake-word listening requires sounddevice and Vosk; install "
                "`pip install 'assistuff[voice]'`"
            ) from exc

        model_path = configured_path(self.model_path, self.project_root)
        if not model_path.is_dir():
            raise VoiceError(f"Vosk wake-word model directory does not exist: {model_path}")
        model = vosk.Model(str(model_path))
        grammar = json.dumps([*self.config.phrases, "[unk]"], ensure_ascii=False)
        recognizer = vosk.KaldiRecognizer(model, self.config.sample_rate, grammar)
        chunks: queue.Queue[bytes | Exception] = queue.Queue()

        def callback(indata, _frames, _time_info, status) -> None:
            if status:
                chunks.put(VoiceError(f"wake-word microphone warning: {status}"))
            chunks.put(bytes(indata))

        started = time.monotonic()
        try:
            with sd.RawInputStream(
                samplerate=self.config.sample_rate,
                blocksize=self.config.frame_samples,
                channels=1,
                dtype="int16",
                callback=callback,
            ):
                while not stop_event.is_set():
                    if (
                        timeout_seconds is not None
                        and time.monotonic() - started >= timeout_seconds
                    ):
                        return None
                    try:
                        chunk = chunks.get(timeout=self.config.detection_timeout_seconds)
                    except queue.Empty:
                        continue
                    if isinstance(chunk, Exception):
                        raise chunk
                    if recognizer.AcceptWaveform(chunk):
                        result = json.loads(recognizer.Result())
                    else:
                        result = json.loads(recognizer.PartialResult())
                    text = _normalized_text(str(result.get("text", result.get("partial", ""))))
                    for phrase in self.config.phrases:
                        normalized_phrase = _normalized_text(phrase)
                        if normalized_phrase and normalized_phrase in text:
                            return phrase
        except VoiceError:
            raise
        except Exception as exc:
            raise VoiceError(f"wake-word listening failed: {exc}") from exc
        return None


def _normalized_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.casefold()).strip()
