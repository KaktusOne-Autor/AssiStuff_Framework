"""Persistence helpers for user-configured OpenAI-compatible APIs."""

from __future__ import annotations

import os
import re
import tempfile
from collections.abc import Collection, Mapping
from pathlib import Path
from typing import Any

import keyring
import yaml
from keyring.errors import KeyringError

from assistuff.config.schemas import (
    ModelCapabilities,
    ModelManifest,
    ModelRuntime,
    RemoteEndpointConfig,
)

KEYRING_SERVICE = "AssiStuff OpenAI-compatible API"
_PROFILE_RE = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")


class ApiConnectionError(RuntimeError):
    """A user-configured API could not be saved."""


def save_api_connection(
    user_root: Path,
    *,
    profile: str,
    model_id: str,
    model_name: str,
    base_url: str,
    api_key: str,
    existing_model_ids: Collection[str] = frozenset(),
    existing_profiles: Mapping[str, RemoteEndpointConfig] | None = None,
    allow_insecure_http: bool = False,
) -> ModelManifest:
    if not _PROFILE_RE.fullmatch(profile):
        raise ValueError("API profile must be lowercase letters, digits, '_' or '-'")
    if not api_key.strip():
        raise ValueError("API key must not be empty")
    if not model_name.strip():
        raise ValueError("provider model name must not be empty")
    if model_id in existing_model_ids:
        raise ValueError(f"model id {model_id!r} already exists")

    api_key_env = f"ASSISTUFF_API_{profile.upper().replace('-', '_')}"
    endpoint = RemoteEndpointConfig(
        base_url=base_url,
        api_key_env=api_key_env,
        allow_insecure_http=allow_insecure_http,
    )
    manifest = ModelManifest(
        id=model_id,
        version="1.0.0",
        runtime=ModelRuntime(
            backend="remote_api",
            tag=model_name.strip(),
            provider="openai_compatible",
            endpoint_profile=profile,
        ),
        capabilities=ModelCapabilities(provides=["chat"]),
    )

    config_dir = user_root / "config"
    try:
        config_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(config_dir, 0o700)
    except OSError as exc:
        raise ApiConnectionError(
            "Could not create the private API configuration directory."
        ) from exc
    config_path = config_dir / "apis.yaml"
    data: dict[str, Any] = {"endpoints": {}, "models": {}}
    if config_path.exists():
        try:
            loaded = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, yaml.YAMLError) as exc:
            raise ApiConnectionError("Could not read the API configuration file.") from exc
        if not isinstance(loaded, dict):
            raise ApiConnectionError(f"invalid API configuration in {config_path}")
        if set(loaded) - {"endpoints", "models"}:
            raise ApiConnectionError(f"unsupported fields in {config_path}")
        data.update(loaded)

    endpoints = data.setdefault("endpoints", {})
    models = data.setdefault("models", {})
    if not isinstance(endpoints, dict) or not isinstance(models, dict):
        raise ApiConnectionError(f"invalid API configuration in {config_path}")
    existing_endpoint = endpoints.get(profile)
    if existing_endpoint is not None and existing_endpoint != endpoint.model_dump():
        raise ValueError(f"API profile {profile!r} already exists with different settings")
    runtime_endpoint = (existing_profiles or {}).get(profile)
    if runtime_endpoint is not None and existing_endpoint is None:
        raise ValueError(f"API profile {profile!r} already exists")
    if (
        runtime_endpoint is not None
        and runtime_endpoint.model_dump(mode="json") != endpoint.model_dump(mode="json")
    ):
        raise ValueError(f"API profile {profile!r} already exists with different settings")
    if model_id in models:
        raise ValueError(f"model id {model_id!r} already exists in API configuration")

    endpoints[profile] = endpoint.model_dump(mode="json")
    models[model_id] = manifest.model_dump(mode="json")
    text = yaml.safe_dump(data, sort_keys=True, allow_unicode=True)
    try:
        keyring.set_password(KEYRING_SERVICE, api_key_env, api_key.strip())
    except KeyringError as exc:
        raise ApiConnectionError(
            "The operating system credential store could not save this API key."
        ) from exc

    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=config_dir,
            prefix=".apis-",
            suffix=".yaml",
            delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            os.chmod(temporary_path, 0o600)
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, config_path)
    except OSError as exc:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        try:
            keyring.delete_password(KEYRING_SERVICE, api_key_env)
        except KeyringError as cleanup_exc:
            raise ApiConnectionError(
                "Could not save the API configuration, and the OS credential store "
                "could not remove the saved key."
            ) from cleanup_exc
        raise ApiConnectionError("Could not save the API configuration file.") from exc

    return manifest
