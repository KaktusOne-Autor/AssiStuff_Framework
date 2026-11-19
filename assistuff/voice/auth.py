"""Profile-scoped Vosk speaker verification without storing raw recordings."""

from __future__ import annotations

import importlib
import json
import math
import os
import re
import tempfile
import threading
from pathlib import Path
from typing import Any

from assistuff.config.schemas import VoiceAuthConfig

from .audio import AudioClip
from .common import VoiceError, configured_path

_PROFILE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")


class VoiceprintStore:
    def __init__(self, root: Path) -> None:
        self.root = root.expanduser().resolve()

    def exists(self, profile: str) -> bool:
        return self._path(profile).is_file()

    def save(self, profile: str, vector: list[float], sample_count: int) -> None:
        if sample_count < 1:
            raise VoiceError("voice enrollment needs at least one sample")
        path = self._path(profile)
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        path.parent.chmod(0o700)
        document = json.dumps(
            {"version": 1, "sample_count": sample_count, "vector": vector},
            separators=(",", ":"),
        ).encode("utf-8")
        descriptor, temporary = tempfile.mkstemp(prefix=".voiceprint-", dir=path.parent)
        try:
            os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(document)
            os.replace(temporary, path)
        except OSError:
            Path(temporary).unlink(missing_ok=True)
            raise

    def load(self, profile: str) -> list[float] | None:
        path = self._path(profile)
        if not path.is_file():
            return None
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            vector = value["vector"]
            if value.get("version") != 1 or not isinstance(vector, list):
                raise ValueError("unsupported voiceprint format")
            return _validated_vector(vector)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise VoiceError(f"could not read voiceprint for profile {profile!r}: {exc}") from exc

    def load_all(self) -> dict[str, list[float]]:
        result: dict[str, list[float]] = {}
        if not self.root.is_dir():
            return result
        for path in self.root.glob("*/voiceprint.json"):
            profile = path.parent.name
            result[profile] = self.load(profile) or []
        return result

    def delete(self, profile: str) -> bool:
        path = self._path(profile)
        existed = path.exists()
        path.unlink(missing_ok=True)
        return existed

    def _path(self, profile: str) -> Path:
        if not _PROFILE_ID.fullmatch(profile) or profile in {".", ".."}:
            raise VoiceError("voiceprint profile ID contains unsupported characters")
        path = self.root / profile / "voiceprint.json"
        if path.resolve().parent.parent != self.root:
            raise VoiceError("voiceprint path escapes the configured profile directory")
        return path


class VoiceAuthenticator:
    def __init__(
        self,
        config: VoiceAuthConfig,
        *,
        sample_rate: int,
        project_root: Path,
        store: VoiceprintStore,
    ) -> None:
        self.config = config
        self.sample_rate = sample_rate
        self.project_root = project_root
        self.store = store
        self._model: Any = None
        self._speaker_model: Any = None
        self._lock = threading.Lock()

    def has_voiceprint(self, profile: str) -> bool:
        return self.store.exists(profile)

    def extract_embedding(self, clip: AudioClip) -> list[float]:
        if clip.sample_rate != self.sample_rate:
            raise VoiceError("voice sample rate does not match the configured STT rate")
        vosk = self._load_vosk()
        with self._lock:
            if self._model is None:
                language_model = configured_path(self.config.model_path, self.project_root)
                speaker_model = configured_path(
                    self.config.speaker_model_path,
                    self.project_root,
                )
                if not language_model.is_dir():
                    raise VoiceError(
                        f"Vosk language model directory does not exist: {language_model}"
                    )
                if not speaker_model.is_dir():
                    raise VoiceError(
                        f"Vosk speaker model directory does not exist: {speaker_model}"
                    )
                self._model = vosk.Model(str(language_model))
                self._speaker_model = vosk.SpkModel(str(speaker_model))
            recognizer = vosk.KaldiRecognizer(self._model, self.sample_rate)
            recognizer.SetSpkModel(self._speaker_model)
            recognizer.AcceptWaveform(clip.pcm)
            response = json.loads(recognizer.FinalResult())
        if not isinstance(response, dict):
            raise VoiceError("Vosk returned an invalid speaker response")
        vector = response.get("spk")
        if not isinstance(vector, list) or not vector:
            raise VoiceError(
                "Vosk did not produce a speaker embedding; record a longer, clear speech sample"
            )
        return _normalize(_validated_vector(vector))

    def save_enrollment(self, profile: str, samples: list[list[float]]) -> None:
        required = self.config.enrollment_samples
        if len(samples) != required:
            raise VoiceError(f"voice enrollment requires exactly {required} samples")
        dimensions = {len(sample) for sample in samples}
        if len(dimensions) != 1:
            raise VoiceError("voice enrollment samples returned incompatible embeddings")
        average = [
            sum(sample[index] for sample in samples) / len(samples)
            for index in range(next(iter(dimensions)))
        ]
        self.store.save(profile, _normalize(average), len(samples))

    def verify(self, profile: str, clip: AudioClip) -> float:
        if not self.config.enabled:
            return 1.0
        expected = self.store.load(profile)
        if expected is None:
            raise VoiceError(
                f"no voiceprint is enrolled for profile {profile!r}; "
                "select Enroll voice in Chat first"
            )
        actual = self.extract_embedding(clip)
        if len(actual) != len(expected):
            raise VoiceError("speaker embedding size changed; enroll the voiceprint again")
        scores: dict[str, float] = {}
        for candidate_profile, candidate_vector in self.store.load_all().items():
            if len(candidate_vector) == len(actual):
                scores[candidate_profile] = _cosine(actual, candidate_vector)
        score = scores.get(profile, _cosine(actual, expected))
        second_score = max(
            (value for candidate, value in scores.items() if candidate != profile),
            default=0.0,
        )
        wrong_best_match = bool(scores) and max(scores, key=scores.get) != profile
        if (
            wrong_best_match
            or score < self.config.similarity_threshold
            or score - second_score < self.config.minimum_margin
        ):
            raise VoiceError("speaker verification failed for the active profile")
        return score

    def _load_vosk(self):
        try:
            return importlib.import_module("vosk")
        except ImportError as exc:
            raise VoiceError(
                "speaker verification requires Vosk; install `pip install 'assistuff[voice]'`"
            ) from exc


def voiceprint_root(value: str, user_root: Path, project_root: Path) -> Path:
    prefix = "~/.assistuff/"
    if value.startswith(prefix):
        return user_root / value[len(prefix) :]
    return configured_path(value, project_root)


def _validated_vector(value: list[Any]) -> list[float]:
    try:
        vector = [float(item) for item in value]
    except (TypeError, ValueError) as exc:
        raise ValueError("speaker embedding must contain numeric values") from exc
    if not vector or any(not math.isfinite(item) for item in vector):
        raise ValueError("speaker embedding must be non-empty and finite")
    return vector


def _normalize(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(item * item for item in vector))
    if norm <= 0:
        raise VoiceError("speaker embedding has zero magnitude")
    return [item / norm for item in vector]


def _cosine(left: list[float], right: list[float]) -> float:
    return sum(a * b for a, b in zip(left, right, strict=True))
