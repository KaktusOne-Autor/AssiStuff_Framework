"""Local microphone capture and WAV normalization."""

from __future__ import annotations

import importlib
import io
import queue
import threading
import time
import wave
from dataclasses import dataclass
from pathlib import Path

from assistuff.config.schemas import SttConfig

from .common import VoiceError


@dataclass(frozen=True)
class AudioClip:
    pcm: bytes
    wav: bytes
    sample_rate: int

    @property
    def duration_seconds(self) -> float:
        return len(self.pcm) / (self.sample_rate * 2)


def record_microphone(
    config: SttConfig,
    *,
    stop_event: threading.Event | None = None,
    max_record_seconds: float | None = None,
    on_status=None,
) -> AudioClip:
    try:
        sd = importlib.import_module("sounddevice")
    except ImportError as exc:
        raise VoiceError(
            "microphone capture requires sounddevice; install `pip install 'assistuff[voice]'`"
        ) from exc
    np = _load_numpy()

    chunks: queue.Queue[bytes | Exception] = queue.Queue()
    block_size = max(512, int(config.sample_rate * 0.2))

    def callback(indata, _frames, _time_info, status) -> None:
        if status:
            chunks.put(VoiceError(f"microphone stream warning: {status}"))
        chunks.put(bytes(indata))

    max_seconds = config.max_record_seconds if max_record_seconds is None else max_record_seconds
    started_at = time.monotonic()
    last_speech_at = started_at
    speech_detected = False
    captured: list[bytes] = []
    if on_status:
        on_status("Listening; speak now. Recording stops after silence.")

    try:
        with sd.RawInputStream(
            samplerate=config.sample_rate,
            blocksize=block_size,
            channels=1,
            dtype="int16",
            callback=callback,
        ):
            while time.monotonic() - started_at < max_seconds:
                if stop_event is not None and stop_event.is_set():
                    break
                try:
                    chunk = chunks.get(timeout=0.1)
                except queue.Empty:
                    chunk = None
                if isinstance(chunk, Exception):
                    raise chunk
                if chunk is None:
                    continue
                captured.append(chunk)
                samples = np.frombuffer(chunk, dtype="<i2").astype(np.float32)
                rms = float(np.sqrt(np.mean(np.square(samples)))) if samples.size else 0.0
                now = time.monotonic()
                if rms >= config.speech_threshold:
                    speech_detected = True
                    last_speech_at = now
                elif speech_detected and now - last_speech_at >= config.silence_timeout_seconds:
                    break
    except VoiceError:
        raise
    except Exception as exc:
        raise VoiceError(f"could not capture microphone audio: {exc}") from exc

    pcm = b"".join(captured)
    if not speech_detected:
        raise VoiceError(
            "no speech was detected; check microphone permission, input device, "
            "and voice.stt.speech_threshold"
        )
    if not pcm:
        raise VoiceError("microphone returned an empty recording")
    return AudioClip(
        pcm=pcm, wav=_wav_bytes(pcm, config.sample_rate), sample_rate=config.sample_rate
    )


def load_wav(path: str | Path, sample_rate: int) -> AudioClip:
    np = _load_numpy()
    source = Path(path).expanduser()
    try:
        with wave.open(str(source), "rb") as handle:
            channels = handle.getnchannels()
            width = handle.getsampwidth()
            source_rate = handle.getframerate()
            frames = handle.readframes(handle.getnframes())
    except (OSError, wave.Error) as exc:
        raise VoiceError(f"voice authentication requires a readable WAV file: {exc}") from exc
    if width != 2 or channels < 1:
        raise VoiceError("voice authentication requires 16-bit PCM WAV audio")

    values = np.frombuffer(frames, dtype="<i2")
    if channels > 1:
        values = values.reshape(-1, channels).astype(np.int32).mean(axis=1).astype("<i2")
    if source_rate != sample_rate and values.size:
        new_size = max(1, round(values.size * sample_rate / source_rate))
        old_positions = np.arange(values.size, dtype=np.float64)
        new_positions = np.linspace(0, values.size - 1, new_size)
        values = np.interp(new_positions, old_positions, values).round().astype("<i2")
    pcm = values.astype("<i2", copy=False).tobytes()
    return AudioClip(pcm=pcm, wav=_wav_bytes(pcm, sample_rate), sample_rate=sample_rate)


def _wav_bytes(pcm: bytes, sample_rate: int) -> bytes:
    output = io.BytesIO()
    with wave.open(output, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(pcm)
    return output.getvalue()


def _load_numpy():
    try:
        return importlib.import_module("numpy")
    except ImportError as exc:
        raise VoiceError(
            "voice audio processing requires numpy; install `pip install 'assistuff[voice]'`"
        ) from exc
