"""Install and load instruction-only portable skill packages."""

from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import jsonschema
import yaml

from assistuff.access import AccountRegistry, User
from assistuff.config.schemas import SkillManifest
from assistuff.skills.registry import Skill, SkillContext

_MAX_INSTRUCTIONS_BYTES = 64_000
_MAX_SKILL_INPUT_BYTES = 256_000
_SKILL_ID = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")


@dataclass(frozen=True)
class PortableSkill:
    manifest: SkillManifest
    instructions: str
    package_dir: Path
    enabled: bool


class PortableSkillRepository:
    def __init__(
        self,
        root: str | Path,
        accounts: AccountRegistry,
    ) -> None:
        self.root = Path(root).expanduser()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.accounts = accounts

    def inspect(self, source: str | Path) -> PortableSkill:
        package_dir = Path(source).expanduser().resolve(strict=True)
        if not package_dir.is_dir():
            raise ValueError("portable skill source must be a directory")
        manifest_path = package_dir / "manifest.yaml"
        if manifest_path.is_symlink() or not manifest_path.is_file():
            raise ValueError("portable skill requires a regular manifest.yaml")
        raw = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
        manifest = SkillManifest.model_validate(raw)
        if manifest.implementation is not None or not manifest.instructions_file:
            raise ValueError(
                "portable imports support instruction-only skills; "
                "executable implementations are not loaded"
            )
        instructions_source = package_dir / manifest.instructions_file
        if instructions_source.is_symlink():
            raise ValueError("instructions_file cannot be a symbolic link")
        instructions_path = instructions_source.resolve(strict=True)
        if (
            instructions_path.is_symlink()
            or package_dir not in instructions_path.parents
            or not instructions_path.is_file()
        ):
            raise ValueError("instructions_file must be a regular file inside the package")
        instructions_bytes = instructions_path.read_bytes()
        if not instructions_bytes or len(instructions_bytes) > _MAX_INSTRUCTIONS_BYTES:
            raise ValueError(
                f"skill instructions must contain 1-{_MAX_INSTRUCTIONS_BYTES} bytes"
            )
        instructions = instructions_bytes.decode("utf-8")
        _validate_schema(manifest.input_schema)
        _validate_schema(manifest.output_schema)
        return PortableSkill(
            manifest=manifest,
            instructions=instructions,
            package_dir=package_dir,
            enabled=self._enabled(self.root / manifest.id),
        )

    def install(self, source: str | Path, *, actor: User) -> PortableSkill:
        self._authorize(actor)
        package = self.inspect(source)
        destination = self.root / package.manifest.id
        if destination.exists():
            raise FileExistsError(f"portable skill is already installed: {package.manifest.id}")
        destination.mkdir(mode=0o700)
        try:
            shutil.copyfile(
                package.package_dir / "manifest.yaml",
                destination / "manifest.yaml",
            )
            target_instructions = destination / package.manifest.instructions_file
            target_instructions.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            shutil.copyfile(
                package.package_dir / package.manifest.instructions_file,
                target_instructions,
            )
            (destination / "enabled").write_text("false\n", encoding="ascii")
            (destination / "enabled").chmod(0o600)
        except OSError:
            shutil.rmtree(destination)
            raise
        return self.inspect(destination)

    def set_enabled(
        self,
        skill_id: str,
        enabled: bool,
        *,
        actor: User,
    ) -> PortableSkill:
        self._authorize(actor)
        if not _SKILL_ID.fullmatch(skill_id):
            raise ValueError("invalid portable skill ID")
        package_dir = self.root / skill_id
        self.inspect(package_dir)
        status = package_dir / "enabled"
        temporary = package_dir / "enabled.tmp"
        temporary.write_text(f"{str(enabled).lower()}\n", encoding="ascii")
        temporary.chmod(0o600)
        temporary.replace(status)
        return self.inspect(package_dir)

    def installed(self) -> list[PortableSkill]:
        if any(path.is_symlink() for path in self.root.iterdir()):
            raise ValueError("portable skill storage must not contain symbolic links")
        packages = [
            self.inspect(path)
            for path in sorted(self.root.iterdir())
            if path.is_dir()
        ]
        return packages

    def enabled(self) -> list[PortableSkill]:
        return [package for package in self.installed() if package.enabled]

    def as_skill(self, package: PortableSkill) -> Skill:
        if package.manifest.implementation is not None:
            raise ValueError("executable portable skills cannot be loaded")

        def run(value: str, _: SkillContext) -> str:
            if len(value.encode("utf-8")) > _MAX_SKILL_INPUT_BYTES:
                raise ValueError("skill input exceeds the 256 KB limit")
            if package.manifest.input_schema is None:
                payload: Any = {"text": value}
            else:
                try:
                    payload = json.loads(value)
                except json.JSONDecodeError as exc:
                    raise ValueError("skill input must be JSON") from exc
                _validate_instance(package.manifest.input_schema, payload)

            result = {
                "instructions": package.instructions,
                "input": payload,
            }
            if package.manifest.output_schema is not None:
                _validate_instance(package.manifest.output_schema, result)
            return json.dumps(result, ensure_ascii=False)

        return Skill(
            name=package.manifest.id,
            run=run,
            description="portable-instructions",
        )

    def _authorize(self, actor: User) -> None:
        self.accounts.list_accounts(actor)

    @staticmethod
    def _enabled(package_dir: Path) -> bool:
        marker = package_dir / "enabled"
        if not marker.is_file():
            return False
        return marker.read_text(encoding="ascii").strip() == "true"


def _validate_schema(schema: dict[str, object] | None) -> None:
    if schema is None:
        return
    _check_local_refs(schema)
    validator = jsonschema.validators.validator_for(schema)
    validator.check_schema(schema)


def _validate_instance(schema: dict[str, object], instance: Any) -> None:
    _validate_schema(schema)
    try:
        jsonschema.validate(instance=instance, schema=schema)
    except jsonschema.ValidationError as exc:
        raise ValueError("skill data does not match its declared JSON Schema") from exc


def _check_local_refs(value: Any) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if key in {"$ref", "$dynamicRef"} and (
                not isinstance(child, str) or not child.startswith("#")
            ):
                raise ValueError("remote JSON Schema references are not allowed")
            _check_local_refs(child)
    elif isinstance(value, list):
        for child in value:
            _check_local_refs(child)
