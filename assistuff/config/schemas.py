"""Pydantic schemas for AssiStuff configuration and manifests."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator  # pyright: ignore[reportMissingImports]


# ---------------------------------------------------------------------------
# Shared primitives
# ---------------------------------------------------------------------------

_ID_RE = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
_SEMVER_RE = re.compile(
    r"^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$"
)


class StrictModel(BaseModel):
    """Base model: forbid unknown fields, validate on assignment."""

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
        str_strip_whitespace=True,
    )


# ---------------------------------------------------------------------------
# framework.yaml
# ---------------------------------------------------------------------------

class FrameworkInfo(StrictModel):
    name: str = "AssiStuff"
    version: str
    mode: Literal["local-first", "hybrid"] = "local-first"

    @field_validator("version")
    @classmethod
    def _semver(cls, value: str) -> str:
        if not _SEMVER_RE.match(value):
            raise ValueError(f"version must be semver, got {value!r}")
        return value


class OllamaConfig(StrictModel):
    host: str = "http://localhost:11434"
    keep_alive: str = "5m"
    read_timeout_seconds: int = Field(default=180, gt=0)
    flash_attention: bool = True
    kv_cache_type: str = "q8_0"


class UtilityModels(StrictModel):
    router: str
    planner: str
    mpa: str
    compiler: str | None = None


class ResidencyConfig(StrictModel):
    pinned: list[str] = Field(default_factory=lambda: ["router", "planner"])
    keep_alive: str = "5m"
    max_loaded: int = Field(default=2, ge=1)


class RuntimeConfig(StrictModel):
    ollama: OllamaConfig = Field(default_factory=OllamaConfig)
    utility_models: UtilityModels
    registry: str = "~/.assistuff/models"
    max_hops: int = Field(default=5, ge=1, le=20)
    residency: ResidencyConfig = Field(default_factory=ResidencyConfig)


class SttConfig(StrictModel):
    engine: Literal["whisper_cpp"] = "whisper_cpp"
    binary_path: str
    model_path: str
    language: str = "ru"
    sample_rate: int = Field(default=16000, gt=0)
    max_record_seconds: float = Field(default=60.0, gt=0)
    silence_timeout_seconds: float = Field(default=1.2, gt=0)
    speech_threshold: float = Field(default=300.0, ge=0)


class VoiceAuthConfig(StrictModel):
    enabled: bool = True
    model_path: str
    speaker_model_path: str
    voiceprints_dir: str = "~/.assistuff/profiles"
    similarity_threshold: float = Field(default=0.35, ge=0.0, le=1.0)
    minimum_margin: float = Field(default=0.06, ge=0.0, le=1.0)
    enrollment_samples: int = Field(default=5, ge=3)
    enrollment_max_seconds: float = Field(default=45.0, gt=0)


class WakeWordConfig(StrictModel):
    enabled: bool = False
    phrases: list[str] = Field(default_factory=lambda: ["north", "hey north", "норт", "эй норт"])
    sample_rate: int = Field(default=16000, gt=0)
    frame_samples: int = Field(default=4000, gt=0)
    detection_timeout_seconds: float = Field(default=0.4, gt=0)

    @field_validator("phrases")
    @classmethod
    def _non_empty(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("wake_word.phrases must not be empty")
        return value


class TtsConfig(StrictModel):
    engine: Literal["piper"] = "piper"
    voice: str = "ru_RU-irina-medium"
    rate: int = Field(default=180, gt=0)
    binary_path: str
    library_path: str
    espeak_data_path: str
    model_path: str
    config_path: str
    player: str = "/usr/bin/afplay"
    enabled: bool = True


class VoiceConfig(StrictModel):
    stt: SttConfig
    auth: VoiceAuthConfig
    wake: WakeWordConfig
    tts: TtsConfig


class ShortTermMemoryConfig(StrictModel):
    backend: Literal["sqlite"] = "sqlite"
    max_messages: int = Field(default=20, gt=0)


class LongTermTagsConfig(StrictModel):
    source: Literal["header"] = "header"
    bilingual: bool = True
    dynamic: bool = True
    new_tag_position: Literal["top", "bottom"] = "top"
    max_per_note: int = Field(default=3, ge=1, le=10)
    min_per_note: int = Field(default=1, ge=0, le=10)
    fallback: str = "#misc"
    search_on_unknown_tag: Literal["retry", "warn"] = "retry"
    max_retries: int = Field(default=1, ge=0, le=3)


class LongTermIndexConfig(StrictModel):
    time: bool = True
    keyword: bool = True
    vector: bool = False
    vector_model: str = "paraphrase-multilingual-MiniLM-L12-v2"
    reindex_on_start: bool = True
    reindex_batch_size: int = Field(default=100, gt=0)


class LongTermMemoryConfig(StrictModel):
    backend: Literal["markdown"] = "markdown"
    index: LongTermIndexConfig = Field(default_factory=LongTermIndexConfig)
    tags: LongTermTagsConfig = Field(default_factory=LongTermTagsConfig)


class DossierSectionsConfig(StrictModel):
    identity: Literal["always", "never"] = "always"
    preferences: Literal["always", "never"] = "always"
    projects: Literal["on_keyword", "always", "never"] = "on_keyword"
    recent_topics: Literal["on_time_query", "always", "never"] = "on_time_query"
    patterns: Literal["on_habit_query", "always", "never"] = "on_habit_query"
    relationships: Literal["on_person_query", "always", "never"] = "on_person_query"


class DossierConfig(StrictModel):
    enabled: bool = True
    compile_every: int = Field(default=20, gt=0)
    compile_model: str = "planner"
    max_slice_tokens: int = Field(default=800, gt=0)
    sections: DossierSectionsConfig = Field(default_factory=DossierSectionsConfig)


class MemoryConfig(StrictModel):
    short_term: ShortTermMemoryConfig = Field(default_factory=ShortTermMemoryConfig)
    long_term: LongTermMemoryConfig = Field(default_factory=LongTermMemoryConfig)
    dossier: DossierConfig = Field(default_factory=DossierConfig)


class ProfilesConfig(StrictModel):
    storage_dir: str = "~/.assistuff/profiles"
    default: str = "default"


class TasksConfig(StrictModel):
    max_steps: int = Field(default=12, gt=0)
    plugin_dir: str = "plugins"
    enabled_plugins: list[str] = Field(default_factory=list)


class AccessConfig(StrictModel):
    default_level: int = Field(default=0, ge=0, le=5)
    profile_levels: dict[str, int] = Field(default_factory=dict)
    require_confirmation_level: int = Field(default=5, ge=0, le=5)
    deny_is_final: bool = True
    no_confirmation_dialogs: bool = True
    log_all_denials: bool = True

    @field_validator("profile_levels")
    @classmethod
    def _levels_in_range(cls, value: dict[str, int]) -> dict[str, int]:
        for profile, level in value.items():
            if not 0 <= level <= 5:
                raise ValueError(f"access.profile_levels[{profile!r}] must be 0..5, got {level}")
        return value


class UiConfig(StrictModel):
    theme: Literal["dark", "light"] = "dark"
    start_minimized: bool = False
    show_telemetry_in_main: bool = False
    telemetry_interval_ms: int = Field(default=1000, ge=250)
    tray_icon_size: int = Field(default=22, gt=0)
    tabs: list[str] = Field(
        default_factory=lambda: [
            "chat", "models", "tasks", "memory",
            "skills", "trace", "settings", "plugins",
        ]
    )


class TelemetryConfig(StrictModel):
    cpu: bool = True
    ram: bool = True
    gpu: bool = False
    temperature: bool = False


class HardwareConfig(StrictModel):
    profile: str = "generic"
    ram_gb: int = Field(default=16, gt=0)
    cpu_cores: int = Field(default=8, gt=0)
    gpu: str | None = None
    gpu_usable: bool = False


class OutputChainConfig(StrictModel):
    emitters: list[str] = Field(default_factory=lambda: ["gui", "tts", "log"])
    filters_min_kind: Literal["result", "progress", "error"] = "result"
    stream_to_gui: bool = False


class FrameworkConfig(StrictModel):
    framework: FrameworkInfo
    runtime: RuntimeConfig
    voice: VoiceConfig
    memory: MemoryConfig
    profiles: ProfilesConfig
    tasks: TasksConfig
    access: AccessConfig = Field(default_factory=AccessConfig)
    ui: UiConfig = Field(default_factory=UiConfig)
    telemetry: TelemetryConfig = Field(default_factory=TelemetryConfig)
    hardware: HardwareConfig = Field(default_factory=HardwareConfig)
    output_chain: OutputChainConfig = Field(default_factory=OutputChainConfig)


# ---------------------------------------------------------------------------
# Model manifest (config/models/*.yaml)
# ---------------------------------------------------------------------------

class ModelRuntime(StrictModel):
    backend: Literal["ollama", "llama_cpp", "mlx"] = "ollama"
    tag: str
    context_window: int = Field(default=8192, gt=0)
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    max_tokens: int = Field(default=2048, gt=0)
    keep_alive: str = "5m"
    format: Literal["text", "json"] = "text"
    options: dict[str, object] = Field(default_factory=dict)


class ModelCapabilities(StrictModel):
    provides: list[str] = Field(default_factory=list)
    requires: list[str] = Field(default_factory=list)

    @field_validator("provides", "requires")
    @classmethod
    def _non_empty_items(cls, value: list[str]) -> list[str]:
        for item in value:
            if not item.strip():
                raise ValueError("capability names must not be empty")
        return value


class ModelIo(StrictModel):
    input_schema: str | None = None
    output_schema: str | None = None


class AccessSpec(StrictModel):
    """Optional access spec. If absent, the unit is available to everyone."""

    min_level: int = Field(default=0, ge=0, le=5)
    pupc_action: str | None = None


class RoutingHints(StrictModel):
    keywords: list[str] = Field(default_factory=list)
    priority: int = Field(default=50, ge=0, le=100)
    cost_hint: Literal["low", "medium", "high"] = "medium"


class InteropSpec(StrictModel):
    accepts_calls_from: list[str] = Field(default_factory=lambda: ["*"])
    can_call: list[str] = Field(default_factory=list)


class EmitsSpec(StrictModel):
    default_kind: Literal["result", "progress", "error"] = "result"
    can_emit: list[Literal["result", "citation", "progress", "error"]] = Field(
        default_factory=lambda: ["result"]
    )


class MemoryAccessSpec(StrictModel):
    reads: list[str] = Field(default_factory=list)
    writes: list[str] = Field(default_factory=list)
    dossier_access: Literal["none", "read", "readwrite"] = "read"


class ProvenanceSpec(StrictModel):
    upstream: str | None = None
    upstream_license: str | None = None
    derived_by: str | None = None
    derivation: str | None = None
    redistribution: Literal["allowed", "forbidden", "restricted"] = "allowed"


class ModelManifest(StrictModel):
    id: str
    version: str
    role: Literal["specialist", "generalist", "utility", "skill"] = "generalist"
    domain: list[str] = Field(default_factory=list)
    avatar: str | None = None

    runtime: ModelRuntime
    capabilities: ModelCapabilities = Field(default_factory=ModelCapabilities)
    io: ModelIo = Field(default_factory=ModelIo)
    access: AccessSpec | None = None
    routing: RoutingHints = Field(default_factory=RoutingHints)
    interop: InteropSpec = Field(default_factory=InteropSpec)
    emits: EmitsSpec = Field(default_factory=EmitsSpec)
    memory: MemoryAccessSpec = Field(default_factory=MemoryAccessSpec)
    provenance: ProvenanceSpec = Field(default_factory=ProvenanceSpec)

    personality: str | None = None
    prompts: dict[str, str] = Field(default_factory=dict)

    @field_validator("id")
    @classmethod
    def _valid_id(cls, value: str) -> str:
        if not _ID_RE.match(value):
            raise ValueError(f"invalid model id: {value!r}")
        return value

    @field_validator("version")
    @classmethod
    def _semver(cls, value: str) -> str:
        if not _SEMVER_RE.match(value):
            raise ValueError(f"version must be semver, got {value!r}")
        return value


# ---------------------------------------------------------------------------
# Skill manifest (config/skills/*.yaml)
# ---------------------------------------------------------------------------

class SkillImplementation(StrictModel):
    module: str
    entrypoint: str = "run"


class SkillNetworkSpec(StrictModel):
    outbound: bool = False
    hosts: list[str] = Field(default_factory=list)


class SkillManifest(StrictModel):
    id: str
    version: str
    kind: Literal["skill"] = "skill"

    capabilities: ModelCapabilities = Field(default_factory=ModelCapabilities)
    access: AccessSpec | None = None
    interop: InteropSpec = Field(default_factory=InteropSpec)
    emits: EmitsSpec = Field(default_factory=EmitsSpec)
    memory: MemoryAccessSpec = Field(default_factory=MemoryAccessSpec)
    network: SkillNetworkSpec = Field(default_factory=SkillNetworkSpec)

    implementation: SkillImplementation

    @field_validator("id")
    @classmethod
    def _valid_id(cls, value: str) -> str:
        if not _ID_RE.match(value):
            raise ValueError(f"invalid skill id: {value!r}")
        return value

    @field_validator("version")
    @classmethod
    def _semver(cls, value: str) -> str:
        if not _SEMVER_RE.match(value):
            raise ValueError(f"version must be semver, got {value!r}")
        return value


# ---------------------------------------------------------------------------
# Personality (config/personalities/*.yaml)
# ---------------------------------------------------------------------------

class PersonalityConfig(StrictModel):
    id: str
    system_prompt: str
    applies_to: list[str] = Field(default_factory=list)

    @field_validator("id")
    @classmethod
    def _valid_id(cls, value: str) -> str:
        if not _ID_RE.match(value):
            raise ValueError(f"invalid personality id: {value!r}")
        return value


# ---------------------------------------------------------------------------
# PUPC (config/access/pupc.yaml)
# ---------------------------------------------------------------------------

class PupcLevel(StrictModel):
    id: str
    description: str


class PupcConfig(StrictModel):
    levels: dict[int, PupcLevel]
    default_level: int = Field(default=0, ge=0, le=5)
    require_confirmation_level: int = Field(default=5, ge=0, le=5)
    deny_is_final: bool = True
    no_confirmation_dialogs: bool = True
    log_all_denials: bool = True

    @model_validator(mode="after")
    def _validate_levels(self) -> "PupcConfig":
        if self.default_level not in self.levels:
            raise ValueError(f"default_level {self.default_level} not in levels")
        return self


# ---------------------------------------------------------------------------
# Aggregated runtime config
# ---------------------------------------------------------------------------

class RuntimeConfigBundle(StrictModel):
    """Everything loaded and validated at startup."""

    framework: FrameworkConfig
    models: dict[str, ModelManifest]
    skills: dict[str, SkillManifest]
    personalities: dict[str, PersonalityConfig]
    pupc: PupcConfig
    project_root: Path
    user_root: Path

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)