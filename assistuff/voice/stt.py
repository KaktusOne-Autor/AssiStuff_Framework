"""whisper.cpp speech-to-text adapter."""

from __future__ import annotations

import asyncio
import contextlib
import tempfile
from pathlib import Path

from assistuff.config.schemas import SttConfig

from .audio import AudioClip
from .common import VoiceError, configured_executable, configured_path


class STTAdapter:
    def __init__(self, config: SttConfig, project_root: Path) -> None:
        self.config = config
        self.project_root = project_root

    def validate_setup(self) -> None:
        configured_executable(self.config.binary_path, self.project_root)
        model = configured_path(self.config.model_path, self.project_root)
        if not model.is_file():
            raise VoiceError(f"whisper.cpp model file does not exist: {model}")

    async def transcribe_clip(self, clip: AudioClip) -> str:
        with tempfile.TemporaryDirectory(prefix="assistuff-stt-") as directory:
            audio_path = Path(directory) / "recording.wav"
            audio_path.write_bytes(clip.wav)
            audio_path.chmod(0o600)
            return await self.transcribe_file(audio_path)

    async def transcribe_file(self, audio_path: str | Path) -> str:
        source = Path(audio_path).expanduser().resolve()
        if not source.is_file():
            raise VoiceError(f"audio file does not exist: {source}")
        executable = configured_executable(self.config.binary_path, self.project_root)
        model = configured_path(self.config.model_path, self.project_root)
        if not model.is_file():
            raise VoiceError(f"whisper.cpp model file does not exist: {model}")
        try:
            process = await asyncio.create_subprocess_exec(
                str(executable),
                "--model",
                str(model),
                "--language",
                self.config.language,
                "--no-timestamps",
                "--no-prints",
                "--file",
                str(source),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except OSError as exc:
            raise VoiceError(f"could not start whisper.cpp: {exc}") from exc
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=300)
        except TimeoutError as exc:
            process.kill()
            await process.wait()
            raise VoiceError("whisper.cpp timed out after 300 seconds") from exc
        except asyncio.CancelledError:
            with contextlib.suppress(ProcessLookupError):
                process.kill()
            await process.wait()
            raise
        if process.returncode:
            detail = stderr.decode("utf-8", errors="replace").strip()[-1000:]
            raise VoiceError(
                f"whisper.cpp exited with status {process.returncode}"
                + (f": {detail}" if detail else "")
            )
        transcript = stdout.decode("utf-8", errors="replace").strip()
        if not transcript:
            raise VoiceError("whisper.cpp returned an empty transcript")
        return transcript
