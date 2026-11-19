"""Model residency policies for Ollama-backed models."""

from __future__ import annotations

import asyncio
import logging

from assistuff.config.schemas import RuntimeConfigBundle
from assistuff.runtime.ollama import OllamaClient, OllamaError

logger = logging.getLogger(__name__)


class ResidencyError(RuntimeError):
    """Raised when a configured model cannot be made resident safely."""


class ModelResidency:
    def __init__(self, client: OllamaClient, config: RuntimeConfigBundle) -> None:
        self.client = client
        self.config = config
        self._settings = config.framework.runtime.residency
        self._max_loaded = self._settings.max_loaded
        self._lock = asyncio.Lock()
        self._persistent: set[str] = set()
        self._tags_by_id = {
            model_id: manifest.runtime.tag
            for model_id, manifest in config.models.items()
        }
        utility = config.framework.runtime.utility_models
        self._tags_by_id.update({
            "router": utility.router,
            "planner": utility.planner,
            "mpa": utility.mpa,
        })
        if utility.compiler:
            self._tags_by_id["compiler"] = utility.compiler
        self._pinned = {
            self._resolve_name(name)
            for name in self._settings.pinned
        }
        self._background = {
            self._resolve_name(name)
            for name in self._settings.background_models
        }

    def _resolve_name(self, name: str) -> str:
        return self._tags_by_id.get(name, name)

    def protected_models(self) -> set[str]:
        protected = set(self._pinned)
        if self._settings.mode == "selected_for_background":
            protected.update(self._background)
        return protected

    async def loaded(self) -> set[str]:
        try:
            return await self.client.loaded_models()
        except OllamaError as exc:
            raise ResidencyError(f"could not query loaded Ollama models: {exc}") from exc

    async def initialize(self) -> dict[str, str]:
        """Warm pinned and selected background models on startup."""
        startup_models = set(self._pinned)
        if self._settings.mode == "selected_for_background":
            startup_models.update(self._background)
        failures: dict[str, str] = {}
        for model in sorted(startup_models):
            try:
                await self._ensure_loaded(model, keep_alive="-1")
            except ResidencyError as exc:
                failures[model] = str(exc)
                logger.error("could not load startup model %s: %s", model, exc)
        return failures

    async def ensure_loaded(self, model: str) -> None:
        """Load an on-demand model while respecting the configured capacity."""
        resolved = self._resolve_name(model)
        is_persistent = (
            resolved in self._pinned
            or (
                self._settings.mode == "selected_for_background"
                and resolved in self._background
            )
        )
        keep_alive = "-1" if is_persistent else self._settings.keep_alive
        await self._ensure_loaded(resolved, keep_alive=keep_alive)

    async def _ensure_loaded(self, model: str, *, keep_alive: str) -> None:
        async with self._lock:
            loaded = await self.loaded()
            if model in loaded:
                if keep_alive == "-1" and model not in self._persistent:
                    try:
                        await self.client.load(model, keep_alive=keep_alive)
                    except OllamaError as exc:
                        raise ResidencyError(
                            f"could not keep Ollama model {model!r} loaded: {exc}"
                        ) from exc
                    self._persistent.add(model)
                return

            while len(loaded) >= self._max_loaded:
                victim = await self._evict_one(loaded, keep=model)
                loaded.remove(victim)

            logger.info("warming up model %s", model)
            try:
                await self.client.load(model, keep_alive=keep_alive)
            except OllamaError as exc:
                raise ResidencyError(f"could not load Ollama model {model!r}: {exc}") from exc
            if keep_alive == "-1":
                self._persistent.add(model)

    async def _evict_one(self, loaded: set[str], *, keep: str) -> str:
        protected = self.protected_models()
        candidates = sorted(
            model for model in loaded
            if model != keep and model not in protected
        )
        if not candidates:
            raise ResidencyError(
                "cannot load another model: residency limit is reached and all "
                "loaded models are pinned or selected for background"
            )

        victim = candidates[0]
        logger.info("evicting model %s to make room for %s", victim, keep)
        try:
            await self.client.unload(victim)
        except OllamaError as exc:
            raise ResidencyError(f"could not evict Ollama model {victim!r}: {exc}") from exc
        return victim
