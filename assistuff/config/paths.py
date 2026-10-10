"""Filesystem paths used across the framework."""

from __future__ import annotations

import os
from pathlib import Path


def get_project_root() -> Path:
    """Root of the AssiStuff source tree (where pyproject.toml lives)."""
    return Path(__file__).resolve().parents[2]


def get_user_root() -> Path:
    """Per-user AssiStuff data directory (~/.assistuff)."""
    override = os.environ.get("ASSISTUFF_HOME")
    if override:
        return Path(override).expanduser().resolve()
    return Path.home() / ".assistuff"


def get_profiles_dir() -> Path:
    return get_user_root() / "profiles"


def get_models_registry_dir() -> Path:
    return get_user_root() / "models"


def get_keys_dir() -> Path:
    return get_user_root() / "keys"


def get_logs_dir() -> Path:
    return get_user_root() / "logs"


def ensure_user_dirs() -> None:
    for path in (
        get_user_root(),
        get_profiles_dir(),
        get_models_registry_dir(),
        get_keys_dir(),
        get_logs_dir(),
    ):
        path.mkdir(parents=True, exist_ok=True)