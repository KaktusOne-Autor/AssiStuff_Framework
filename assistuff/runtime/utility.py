"""Utility roles — internal framework models, not peers."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from assistuff.config.schemas import RuntimeConfigBundle
from assistuff.runtime.ollama import OllamaClient

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class UtilityRole:
    name: str
    model: str


class UtilityRoles:
    def __init__(self, client: OllamaClient, config: RuntimeConfigBundle) -> None:
        self.client = client
        self.config = config
        fw = config.framework.runtime.utility_models
        self._roles: dict[str, UtilityRole] = {
            "router": UtilityRole("router", fw.router),
            "planner": UtilityRole("planner", fw.planner),
            "mpa": UtilityRole("mpa", fw.mpa),
        }
        if fw.compiler:
            self._roles["compiler"] = UtilityRole("compiler", fw.compiler)

    def get(self, name: str) -> UtilityRole:
        try:
            return self._roles[name]
        except KeyError as exc:
            raise KeyError(f"unknown utility role: {name!r}") from exc

    async def generate(
        self,
        role: str,
        prompt: str,
        *,
        system: str | None = None,
        format: str | dict | None = None,
        options: dict | None = None,
    ) -> str:
        r = self.get(role)
        return await self.client.generate(
            model=r.model,
            prompt=prompt,
            system=system,
            format=format,
            options=options,
        )

    async def generate_json(
        self,
        role: str,
        prompt: str,
        *,
        system: str | None = None,
        schema: dict | None = None,
        options: dict | None = None,
    ) -> dict:
        r = self.get(role)
        return await self.client.generate_json(
            model=r.model,
            prompt=prompt,
            system=system,
            schema=schema,
            options=options,
        )