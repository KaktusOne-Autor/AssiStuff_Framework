"""Runtime configuration API."""

from __future__ import annotations

from .loader import ConfigError, load_runtime_config
from .paths import (
    ensure_user_dirs,
    get_keys_dir,
    get_logs_dir,
    get_models_registry_dir,
    get_profiles_dir,
    get_project_root,
    get_user_root,
)

__all__ = [
    "ConfigError",
    "ensure_user_dirs",
    "get_keys_dir",
    "get_logs_dir",
    "get_models_registry_dir",
    "get_profiles_dir",
    "get_project_root",
    "get_user_root",
    "load_runtime_config",
]
