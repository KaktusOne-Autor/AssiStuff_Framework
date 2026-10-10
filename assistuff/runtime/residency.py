"""Model residency manager for low-RAM hardware."""

from __future__ import annotations

import logging

from assistuff.config.schemas import RuntimeConfigBundle
from assistuff.runtime.ollama import OllamaClient, OllamaError

logger = logging.getLogger(__name__)


class ModelResidency:
    def __init__(self, client: OllamaClient, config: RuntimeConfigBundle) -> None:
        self.client = client
        self.config = config
        self._pinned = set(config.framework.runtime.residency.pinned)
        self._max_loaded = config.framework.runtime.residency.max_loaded
        self._utility_names = {
            config.framework.runtime.utility_models.router,
            config.framework.runtime.utility_models.planner,
            config.framework.runtime.utility_models.mpa,
        }
        if config.framework.runtime.utility_models.compiler:
            self._utility_names.add(config.framework.runtime.utility_models.compiler)

    async def loaded(self) -> set[str]:
        try:
            return await self.client.loaded_models()
        except OllamaError as exc:
            logger.warning("could not query loaded models: %s", exc)
            return set()

    async def ensure_loaded(self, model: str) -> None:
        loaded = await self.loaded()
        if model in loaded:
            return

        if len(loaded) >= self._max_loaded:
            await self._evict_one(loaded, keep=model)

        logger.info("warming up model %s", model)
        await self.client.load(model)

    async def _evict_one(self, loaded: set[str], *, keep: str) -> None:
        pinned_models = self._pinned | self._utility_names
        candidates = [
            m for m in loaded
            if m != keep and m not in pinned_models
        ]
        if not candidates:
            logger.warning(
                "cannot evict: all loaded models are pinned/utility (%s)",
                ", ".join(sorted(loaded)),
            )
            return
        victim = candidates[0]
        logger.info("evicting model %s to make room for %s", victim, keep)
        try:
            await self.client.unload(victim)
        except OllamaError as exc:
            logger.warning("failed to evict %s: %s", victim, exc)

    async def warm_pinned(self) -> None:
        for name in self._pinned:
            model = self._resolve_pinned(name)
            if model is None:
                continue
            try:
                await self.client.load(model)
            except OllamaError as exc:
                logger.warning("could not warm %s: %s", model, exc)

    def _resolve_pinned(self, name: str) -> str | None:
        fw = self.config.framework.runtime.utility_models
        if name == "router":
            return fw.router
        if name == "planner":
            return fw.planner
        if name == "mpa":
            return fw.mpa
        if name == "compiler":
            return fw.compiler
        return None