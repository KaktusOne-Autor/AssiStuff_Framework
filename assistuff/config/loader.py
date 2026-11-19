"""Load the runtime configuration and manifests for AssiStuff."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from assistuff.config.paths import get_project_root, get_user_root
from assistuff.config.schemas import (
    FrameworkConfig,
    ModelManifest,
    PersonalityConfig,
    PupcConfig,
    RuntimeConfigBundle,
    SkillManifest,
)


class ConfigError(RuntimeError):
    """Raised when a required runtime config is missing or invalid."""


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ConfigError(f"expected a mapping in {path}")
    return data


def _load_manifests(directory: Path, *, kind: str) -> dict[str, Any]:
    manifests: dict[str, Any] = {}
    if not directory.exists():
        return manifests
    for path in sorted(directory.glob("*.yaml")):
        value = _read_yaml(path)
        if not value:
            continue
        if kind == "model":
            manifest = ModelManifest.model_validate(value)
        elif kind == "skill":
            manifest = SkillManifest.model_validate(value)
        else:
            raise ConfigError(f"unsupported manifest kind: {kind!r}")
        manifests[manifest.id] = manifest
    return manifests


def _load_personalities(directory: Path) -> dict[str, PersonalityConfig]:
    personalities: dict[str, PersonalityConfig] = {}
    if not directory.exists():
        return personalities
    for path in sorted(directory.glob("*.yaml")):
        value = _read_yaml(path)
        if not value:
            continue
        item = PersonalityConfig.model_validate(value)
        personalities[item.id] = item
    return personalities


def load_runtime_config() -> RuntimeConfigBundle:
    project_root = get_project_root()
    config_dir = project_root / "config"
    framework_data = _read_yaml(config_dir / "framework.yaml")
    if not framework_data:
        raise ConfigError(f"missing runtime config at {config_dir / 'framework.yaml'}")

    framework = FrameworkConfig.model_validate(framework_data)
    models = _load_manifests(config_dir / "models", kind="model")
    for model in models.values():
        if model.runtime.backend != "remote_api":
            continue
        profile = model.runtime.endpoint_profile
        endpoint = framework.runtime.remote_endpoints.get(profile or "")
        if endpoint is None:
            raise ConfigError(
                f"model {model.id!r} references unknown remote endpoint "
                f"profile {profile!r}"
            )
        if endpoint.provider != model.runtime.provider:
            raise ConfigError(
                f"model {model.id!r} provider does not match endpoint "
                f"profile {profile!r}"
            )
    skills = _load_manifests(config_dir / "skills", kind="skill")
    personalities = _load_personalities(config_dir / "personalities")

    pupc_data = _read_yaml(config_dir / "access" / "pupc.yaml")
    if not pupc_data:
        raise ConfigError(f"missing PUPC config at {config_dir / 'access' / 'pupc.yaml'}")
    pupc = PupcConfig.model_validate(pupc_data)

    return RuntimeConfigBundle(
        framework=framework,
        models=models,
        skills=skills,
        personalities=personalities,
        pupc=pupc,
        project_root=project_root,
        user_root=get_user_root(),
    )
