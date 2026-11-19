"""Capability router — chooses the target capability for a query."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from assistuff.bus.capability_bus import CapabilityBus
from assistuff.config.schemas import RuntimeConfigBundle
from assistuff.runtime.residency import ModelResidency
from assistuff.runtime.utility import UtilityRoles

logger = logging.getLogger(__name__)

_ROUTER_SCHEMA = {
    "type": "object",
    "properties": {
        "capability": {"type": "string"},
        "reason": {"type": "string"},
    },
    "required": ["capability"],
}

_ROUTER_PROMPT = """You classify a user request into one capability from the list.

Return JSON: {{"capability": "<name>", "reason": "<short>"}}

Rules:
- Choose exactly one capability from the list.
- If uncertain, choose the general-purpose one.
- Do not answer the user.

Available capabilities:
{capabilities}

User request:
{query}
"""


@dataclass
class Route:
    capability: str
    unit_id: str
    reason: str = ""
    candidates: list[str] = field(default_factory=list)


class CapabilityRouter:
    def __init__(
        self,
        bus: CapabilityBus,
        roles: UtilityRoles,
        residency: ModelResidency,
        config: RuntimeConfigBundle,
    ) -> None:
        self.bus = bus
        self.roles = roles
        self.residency = residency
        self.config = config

    async def route(self, query: str) -> Route:
        all_caps = self._all_capabilities()
        if not all_caps:
            raise RuntimeError("no capabilities registered")

        # 1. Deterministic keyword match
        keyword_route = self._keyword_route(query, all_caps)
        if keyword_route is not None:
            logger.info("router: deterministic -> %s", keyword_route.capability)
            return keyword_route

        # 2. LLM classification
        llm_route = await self._llm_route(query, all_caps)
        if llm_route is not None:
            logger.info("router: llm -> %s", llm_route.capability)
            return llm_route

        # 3. Fallback: generalist
        fallback = self._fallback(all_caps)
        logger.info("router: fallback -> %s", fallback.capability)
        return fallback

    # ------------------------------------------------------------------
    # Capability listing
    # ------------------------------------------------------------------

    def _all_capabilities(self) -> list[str]:
        caps: set[str] = set()
        for unit in self.bus.units():
            if not unit.routable:
                continue
            caps.update(unit.capabilities)
        return sorted(caps)

    # ------------------------------------------------------------------
    # Keyword matching
    # ------------------------------------------------------------------

    def _keyword_route(self, query: str, all_caps: list[str]) -> Route | None:
        normalized = query.casefold()
        best: tuple[int, str, str] | None = None

        for unit in self.bus.units():
            manifest = self.config.models.get(unit.id) or self.config.skills.get(unit.id)
            if manifest is None:
                continue
            routing = getattr(manifest, "routing", None)
            keywords = list(getattr(routing, "keywords", []) or [])
            priority = int(getattr(routing, "priority", 50))
            for kw in keywords:
                if not kw:
                    continue
                if kw.casefold() in normalized:
                    for cap in unit.capabilities:
                        candidate = (priority, kw, cap)
                        if best is None or candidate[0] > best[0]:
                            best = candidate

        if best is None:
            return None
        _, _, cap = best
        unit = self.bus.resolve(cap)
        return Route(capability=cap, unit_id=unit.id, reason="keyword")

    # ------------------------------------------------------------------
    # LLM classification
    # ------------------------------------------------------------------

    async def _llm_route(self, query: str, all_caps: list[str]) -> Route | None:
        prompt = _ROUTER_PROMPT.format(
            capabilities=", ".join(all_caps),
            query=query,
        )
        try:
            data = await self.roles.generate_json("router", prompt, schema=_ROUTER_SCHEMA)
        except Exception as exc:
            logger.warning("router LLM failed: %s", exc)
            return None

        cap = str(data.get("capability", "")).strip()
        if cap not in all_caps:
            logger.warning("router LLM returned unknown capability: %r", cap)
            return None

        unit = self.bus.resolve(cap)
        return Route(
            capability=cap,
            unit_id=unit.id,
            reason=str(data.get("reason", "llm")),
        )

    # ------------------------------------------------------------------
    # Fallback
    # ------------------------------------------------------------------

    def _fallback(self, all_caps: list[str]) -> Route:
        preferred = [
            "answer.general",
            "answer",
            "simple",
        ]
        for name in preferred:
            if name in all_caps:
                unit = self.bus.resolve(name)
                return Route(capability=name, unit_id=unit.id, reason="fallback")

        cap = all_caps[0]
        unit = self.bus.resolve(cap)
        return Route(capability=cap, unit_id=unit.id, reason="fallback-first")
