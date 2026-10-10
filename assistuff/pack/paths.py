"""Package-specific paths."""

from __future__ import annotations

from pathlib import Path

from assistuff.config.paths import get_models_registry_dir, get_user_root


def installed_models_dir() -> Path:
    return get_models_registry_dir()


def installed_model_dir(package_id: str, version: str) -> Path:
    return installed_models_dir() / f"{package_id}@{version}"


def registry_json_path() -> Path:
    return get_user_root() / "registry.json"


def modelfiles_dir() -> Path:
    return get_user_root() / "ollama"


def packages_cache_dir() -> Path:
    return get_user_root() / "cache" / "packages"