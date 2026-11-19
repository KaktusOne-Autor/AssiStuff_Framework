"""Local Piper speech synthesis and playback."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

from assistuff.config.schemas import TtsConfig

from .common import VoiceError, configured_executable, configured_path


class TTSAdapter:
    def __init__(self, config: TtsConfig, project_root: Path) -> None:
        self.config = config
        self.project_root = project_root

    def validate_setup(self) -> None:
        if not self.config.enabled:
            raise VoiceError("text-to-speech is disabled in voice.tts.enabled")
        configured_executable(self.config.binary_path, self.project_root)
        configured_executable(self.config.player, self.project_root)
        for label, value in (
            ("Piper voice model", self.config.model_path),
            ("Piper model config", self.config.config_path),
        ):
            path = configured_path(value, self.project_root)
            if not path.is_file():
                raise VoiceError(f"{label} does not exist: {path}")
        for label, value in (
            ("Piper library directory", self.config.library_path),
            ("espeak-ng data directory", self.config.espeak_data_path),
        ):
            path = configured_path(value, self.project_root)
            if not path.is_dir():
                raise VoiceError(f"{label} does not exist: {path}")

    def speak(self, text: str) -> None:
        if not self.config.enabled:
            return
        value = text.strip()
        if not value:
            return
        if len(value) > 20_000:
            raise VoiceError("speech text exceeds the 20,000 character limit")
        self.validate_setup()
        executable = configured_executable(self.config.binary_path, self.project_root)
        player = configured_executable(self.config.player, self.project_root)
        model = configured_path(self.config.model_path, self.project_root)
        model_config = configured_path(self.config.config_path, self.project_root)
        library_dir = configured_path(self.config.library_path, self.project_root)
        espeak_dir = configured_path(self.config.espeak_data_path, self.project_root)
        environment = os.environ.copy()
        variable = "DYLD_LIBRARY_PATH" if sys.platform == "darwin" else "LD_LIBRARY_PATH"
        existing_library_path = environment.get(variable)
        environment[variable] = (
            f"{library_dir}{os.pathsep}{existing_library_path}"
            if existing_library_path
            else str(library_dir)
        )
        environment["PIPER_PHONEMIZE_ESPEAKNG_DATA"] = str(espeak_dir)
        length_scale = max(0.5, min(2.0, 180 / self.config.rate))

        with tempfile.TemporaryDirectory(prefix="assistuff-tts-") as directory:
            output_path = Path(directory) / "speech.wav"
            try:
                subprocess.run(
                    [
                        str(executable),
                        "--model",
                        str(model),
                        "--config",
                        str(model_config),
                        "--output_file",
                        str(output_path),
                        "--length_scale",
                        f"{length_scale:.3f}",
                    ],
                    input=value,
                    text=True,
                    capture_output=True,
                    check=True,
                    timeout=180,
                    env=environment,
                )
                output_path.chmod(0o600)
                subprocess.run(
                    [str(player), str(output_path)],
                    capture_output=True,
                    check=True,
                    timeout=180,
                )
            except subprocess.TimeoutExpired as exc:
                raise VoiceError("Piper or the audio player timed out") from exc
            except subprocess.CalledProcessError as exc:
                detail = str(exc.stderr or "").strip()[-1000:]
                raise VoiceError(
                    f"voice synthesis/playback failed with status {exc.returncode}"
                    + (f": {detail}" if detail else "")
                ) from exc
            except OSError as exc:
                raise VoiceError(f"could not start Piper or the audio player: {exc}") from exc
