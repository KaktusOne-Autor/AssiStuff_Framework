"""Dispatcher — assembles all layers for a single query."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator

from assistuff.access.pupc import Pupc
from assistuff.bus.capability_bus import CapabilityBus
from assistuff.bus.events import ChainEvent
from assistuff.bus.output_chain import OutputChain
from assistuff.config.schemas import RuntimeConfigBundle
from assistuff.memory.profiles import ProfileManager
from assistuff.memory.store import MemoryStore
from assistuff.router.capability_router import CapabilityRouter
from assistuff.runtime.model_runtime import ModelRuntime
from assistuff.runtime.ollama import OllamaClient
from assistuff.runtime.residency import ModelResidency
from assistuff.runtime.utility import UtilityRoles
from assistuff.turn.memory_writer import MemoryWriter
from assistuff.turn.session import Session
from assistuff.turn.summarizer import Summarizer
from assistuff.turn.turn import Turn

logger = logging.getLogger(__name__)


class Dispatcher:
    def __init__(
        self,
        config: RuntimeConfigBundle,
        *,
        profile: str | None = None,
        ollama_client: OllamaClient | None = None,
    ) -> None:
        self.config = config
        self.client = ollama_client or OllamaClient(config.framework.runtime.ollama)
        self.roles = UtilityRoles(self.client, config)
        self.residency = ModelResidency(self.client, config)

        self.profile_manager = ProfileManager(config.framework.profiles.storage_dir)
        self.profile = self.profile_manager.create(
            profile or self.profile_manager.get_active()
        )
        self.profile_dir = self.profile_manager.profile_dir(self.profile)

        self.memory = MemoryStore(
            self.profile,
            self.profile_dir,
            config.framework.memory,
        )

        self.pupc = Pupc(config.framework.access, config.pupc)
        self.user = self.pupc.user_for_profile(self.profile)

        self.chain = OutputChain()
        self.bus = CapabilityBus(
            self.chain,
            max_hops=config.framework.runtime.max_hops,
            user_level_getter=lambda: self.user.level,
        )

        self._register_skills()
        self._register_models()

        self.router = CapabilityRouter(self.bus, self.roles, self.residency, config)
        self.summarizer = Summarizer(self.roles)
        self.memory_writer = MemoryWriter(self.memory)
        self.turn = Turn(
            self.bus,
            self.router,
            self.chain,
            self.roles,
            summarizer=self.summarizer,
            memory_writer=self.memory_writer,
        )

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def _register_skills(self) -> None:
        from assistuff.skills.builtin.factory import register_builtins
        from assistuff.skills.plugins.loader import load_plugins
        from assistuff.skills.registry import SkillContext, SkillRegistry

        registry = SkillRegistry()
        register_builtins(registry, self.config.skills)
        try:
            load_plugins(
                registry,
                plugin_dir=self.config.framework.tasks.plugin_dir,
                enabled_plugins=self.config.framework.tasks.enabled_plugins,
            )
        except Exception:
            logger.exception("plugin loading failed")

        from assistuff.bus.adapters.skill_adapter import make_skill_capability

        def context_provider() -> SkillContext:
            # Inject utility_roles for skills that need them
            ctx = SkillContext(
                profile=self.profile,
                memory=self.memory,
                user=self.user,
            )
            object.__setattr__(ctx, "utility_roles", self.roles)  # non-frozen workaround
            return ctx

        for skill in registry.all():
            manifest = self.config.skills.get(skill.name)
            if manifest is None:
                # Skill without manifest — register with defaults
                from assistuff.config.schemas import (
                    AccessSpec,
                    EmitsSpec,
                    InteropSpec,
                    ModelCapabilities,
                    SkillImplementation,
                    SkillManifest,
                    SkillNetworkSpec,
                )
                manifest = SkillManifest(
                    id=skill.name,
                    version="1.0.0",
                    capabilities=ModelCapabilities(provides=[skill.name]),
                    access=AccessSpec(min_level=0),
                    interop=InteropSpec(accepts_calls_from=["*"], can_call=[]),
                    emits=EmitsSpec(default_kind="result", can_emit=["result"]),
                    network=SkillNetworkSpec(),
                    implementation=SkillImplementation(
                        module=f"assistuff.skills.builtin.{skill.name}",
                        entrypoint="run",
                    ),
                )
            cap = make_skill_capability(manifest, skill, context_provider=context_provider)
            try:
                self.bus.register(cap)
            except Exception as exc:
                logger.warning("skip skill %s: %s", skill.name, exc)

    def _register_models(self) -> None:
        from assistuff.bus.adapters.model_adapter import make_model_capability

        for model_id, manifest in self.config.models.items():
            runtime = ModelRuntime(manifest, self.client, self.config)
            cap = make_model_capability(manifest, runtime)
            try:
                self.bus.register(cap)
            except Exception as exc:
                logger.warning("skip model %s: %s", model_id, exc)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def handle(self, query: str) -> AsyncIterator[ChainEvent]:
        session = Session(
            profile=self.profile,
            user=self.user,
            memory=self.memory,
        )
        async for event in self.turn.handle(session, query):
            yield event

    async def final_text(self, query: str) -> str:
        trace_id: str | None = None
        last_text = ""
        async for event in self.handle(query):
            trace_id = event.trace_id
            if event.kind == "result":
                text = event.payload.get("text")
                if isinstance(text, str):
                    last_text = text
        if trace_id:
            final = self.chain.final_result(trace_id)
            if final:
                return final
        return last_text

    async def aclose(self) -> None:
        await self.client.aclose()