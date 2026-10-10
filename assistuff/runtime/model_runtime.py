"""Per-model runtime that respects the manifest."""

from __future__ import annotations

import logging
from pathlib import Path

from assistuff.config.schemas import ModelManifest, RuntimeConfigBundle
from assistuff.runtime.ollama import OllamaClient

logger = logging.getLogger(__name__)


class ModelRuntime:
    """Wraps an Ollama model with manifest-driven options and system prompt."""

    def __init__(
        self,
        manifest: ModelManifest,
        client: OllamaClient,
        config: RuntimeConfigBundle,
    ) -> None:
        self.manifest = manifest
        self.client = client
        self.config = config

    # ------------------------------------------------------------------
    # Prompt assembly
    # ------------------------------------------------------------------

    def _read_prompt(self, key: str) -> str:
        rel = self.manifest.prompts.get(key)
        if not rel:
            return ""
        path = (self.config.project_root / rel).resolve()
        if not path.is_file():
            logger.warning("prompt file missing: %s", path)
            return ""
        return path.read_text(encoding="utf-8").strip()

    def _identity_prompt(self) -> str:
        identity_path = self.config.project_root / "prompts" / "identities" / "default.md"
        if identity_path.is_file():
            return identity_path.read_text(encoding="utf-8").strip()
        return ""

    def _personality_prompt(self) -> str:
        if not self.manifest.personality:
            return ""
        personality = self.config.personalities.get(self.manifest.personality)
        if personality is None:
            logger.warning("personality %r not found", self.manifest.personality)
            return ""
        path = (self.config.project_root / personality.system_prompt).resolve()
        if not path.is_file():
            logger.warning("personality file missing: %s", path)
            return ""
        return path.read_text(encoding="utf-8").strip()

    def _capabilities_prompt(self) -> str:
        provides = self.manifest.capabilities.provides
        if not provides:
            return ""
        lines = "\n".join(f"- {cap}" for cap in provides)
        return f"Capabilities you provide:\n{lines}"

    def build_system_prompt(self) -> str:
        parts = [
            self._identity_prompt(),
            self._personality_prompt(),
            self._capabilities_prompt(),
            self._read_prompt("system"),
        ]
        return "\n\n".join(part for part in parts if part)

    # ------------------------------------------------------------------
    # Generation
    # ------------------------------------------------------------------

    def _options(self) -> dict[str, object]:
        opts: dict[str, object] = {
            "temperature": self.manifest.runtime.temperature,
            "num_ctx": self.manifest.runtime.context_window,
            "num_predict": self.manifest.runtime.max_tokens,
        }
        opts.update(self.manifest.runtime.options)
        return opts

    async def generate(self, prompt: str, *, system: str | None = None) -> str:
        system_prompt = system if system is not None else self.build_system_prompt()
        return await self.client.generate(
            model=self.manifest.runtime.tag,
            prompt=prompt,
            system=system_prompt or None,
            format="json" if self.manifest.runtime.format == "json" else None,
            options=self._options(),
            keep_alive=self.manifest.runtime.keep_alive,
        )

    async def generate_json(
        self,
        prompt: str,
        *,
        schema: dict | None = None,
        system: str | None = None,
    ) -> dict:
        system_prompt = system if system is not None else self.build_system_prompt()
        return await self.client.generate_json(
            model=self.manifest.runtime.tag,
            prompt=prompt,
            system=system_prompt or None,
            schema=schema,
            options=self._options(),
            keep_alive=self.manifest.runtime.keep_alive,
        )