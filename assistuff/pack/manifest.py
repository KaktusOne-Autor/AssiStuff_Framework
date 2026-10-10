"""Package manifest — pydantic model for .nrdpkg."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


_ID_RE = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
_SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+(?:-[a-zA-Z0-9.-]+)?$")


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class PackageInfo(StrictModel):
    id: str
    name: str
    version: str
    author: str = "unknown"
    license: str = "unknown"
    noredur_api: str = ">=4.1.0"

    @field_validator("id")
    @classmethod
    def _valid_id(cls, value: str) -> str:
        if not _ID_RE.match(value):
            raise ValueError(f"invalid package id: {value!r}")
        return value

    @field_validator("version")
    @classmethod
    def _semver(cls, value: str) -> str:
        if not _SEMVER_RE.match(value):
            raise ValueError(f"version must be semver, got {value!r}")
        return value


class WeightFile(StrictModel):
    path: str
    sha256: str
    size_bytes: int = Field(ge=0)


class WeightsSpec(StrictModel):
    bundled: bool = True
    format: Literal["gguf", "safetensors", "ollama-blob", "none"] = "gguf"
    quantization: str | None = None
    size_bytes: int = Field(default=0, ge=0)
    files: list[WeightFile] = Field(default_factory=list)


class PackageRuntime(StrictModel):
    backend: Literal["ollama", "llama_cpp", "mlx"] = "ollama"
    load_from: Literal["bundled", "registry"] = "bundled"
    context_window: int = Field(default=8192, gt=0)
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)


class PackageCapabilities(StrictModel):
    provides: list[str] = Field(default_factory=list)
    requires: list[str] = Field(default_factory=list)


class PackageInterop(StrictModel):
    accepts_calls_from: list[str] = Field(default_factory=lambda: ["*"])
    can_call: list[str] = Field(default_factory=list)


class PackageAccess(StrictModel):
    min_level: int = Field(default=0, ge=0, le=5)
    pupc_required: bool = False


class ProvenanceSpec(StrictModel):
    upstream: str | None = None
    upstream_license: str | None = None
    derived_by: str | None = None
    derivation: str | None = None
    redistribution: Literal["allowed", "forbidden", "restricted"] = "allowed"


class IntegritySpec(StrictModel):
    signature_algorithm: Literal["ed25519"] = "ed25519"
    signed_by: str | None = None
    signed_at: str | None = None


class PackageManifest(StrictModel):
    package: PackageInfo
    weights: WeightsSpec = Field(default_factory=WeightsSpec)
    runtime: PackageRuntime = Field(default_factory=PackageRuntime)
    capabilities: PackageCapabilities = Field(default_factory=PackageCapabilities)
    interop: PackageInterop = Field(default_factory=PackageInterop)
    access: PackageAccess = Field(default_factory=PackageAccess)
    provenance: ProvenanceSpec = Field(default_factory=ProvenanceSpec)
    integrity: IntegritySpec = Field(default_factory=IntegritySpec)