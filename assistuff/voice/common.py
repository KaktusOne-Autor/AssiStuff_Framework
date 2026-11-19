"""Shared voice errors and configured path resolution."""

from __future__ import annotations

import shutil
from pathlib import Path


class VoiceError(RuntimeError):
    """A voice stage cannot complete with the available local setup."""


def configured_path(value: str, project_root: Path) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else (project_root / path).resolve()


def configured_executable(value: str, project_root: Path) -> Path:
    path = Path(value).expanduser()
    if path.is_absolute() or path.parent != Path("."):
        candidate = path if path.is_absolute() else project_root / path
        if candidate.is_file():
            return candidate.resolve()
    else:
        found = shutil.which(value)
        if found:
            return Path(found).resolve()
    raise VoiceError(
        f"voice executable {value!r} was not found; install it or update "
        "voice settings in config/framework.yaml"
    )
