"""Capability Bus — peer-to-peer dispatch by capability name."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from .events import ChainEvent
from .output_chain import OutputChain
from .trace import Trace

logger = logging.getLogger(__name__)


class CapabilityError(RuntimeError):
    pass


class CapabilityNotFound(CapabilityError):
    pass


class InteropDenied(CapabilityError):
    pass


class HopsExceeded(CapabilityError):
    pass


@dataclass
class Capability:
    """A registered unit — model or skill."""

    id: str
    capabilities: list[str]
    handler: Callable[..., Awaitable[AsyncIterator[ChainEvent]]]
    accepts_calls_from: list[str] = field(default_factory=lambda: ["*"])
    can_call: list[str] = field(default_factory=list)
    min_level: int = 0

    def accepts(self, caller: str) -> bool:
        if "*" in self.accepts_calls_from:
            return True
        return caller in self.accepts_calls_from

    def may_call(self, capability: str) -> bool:
        if "*" in self.can_call:
            return True
        return capability in self.can_call


class CapabilityBus:
    def __init__(
        self,
        output_chain: OutputChain,
        *,
        max_hops: int = 5,
        user_level_getter: Callable[[], int] | None = None,
    ) -> None:
        self._registry: dict[str, Capability] = {}
        self._output_chain = output_chain
        self._max_hops = max_hops
        self._user_level_getter = user_level_getter or (lambda: 5)

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(self, cap: Capability) -> None:
        if cap.id in self._registry:
            raise CapabilityError(f"unit already registered: {cap.id}")
        for name in cap.capabilities:
            if not name or not isinstance(name, str):
                raise CapabilityError(f"invalid capability name on unit {cap.id}")
        self._registry[cap.id] = cap

    def units(self) -> list[Capability]:
        return list(self._registry.values())

    def find(self, capability: str) -> list[Capability]:
        return [u for u in self._registry.values() if capability in u.capabilities]

    def resolve(self, capability: str) -> Capability:
        matches = self.find(capability)
        if not matches:
            raise CapabilityNotFound(f"no unit provides {capability!r}")
        # Deterministic choice: first registered wins.
        return matches[0]

    # ------------------------------------------------------------------
    # Dispatch
    # ------------------------------------------------------------------

    async def call(
        self,
        capability: str,
        payload: dict[str, Any],
        *,
        caller: str,
        trace: Trace,
        ttl: float = 30.0,
    ) -> AsyncIterator[ChainEvent]:
        if trace.hops >= self._max_hops:
            raise HopsExceeded(
                f"trace {trace.trace_id} exceeded max_hops={self._max_hops}"
            )

        unit = self.resolve(capability)

        if not unit.accepts(caller):
            raise InteropDenied(
                f"unit {unit.id!r} does not accept calls from {caller!r}"
            )

        user_level = self._user_level_getter()
        if user_level < unit.min_level:
            denial = ChainEvent(
                trace_id=trace.trace_id,
                source=unit.id,
                kind="error",
                payload={
                    "reason": "access_denied",
                    "required_level": unit.min_level,
                    "user_level": user_level,
                },
            )
            self._output_chain.emit(denial)
            yield denial
            return

        trace.push(unit.id)
        try:
            async for event in self._run_with_ttl(
                unit, capability, payload, caller=caller, trace=trace, ttl=ttl
            ):
                self._output_chain.emit(event)
                yield event
        finally:
            trace.pop()

    async def _run_with_ttl(
        self,
        unit: Capability,
        capability: str,
        payload: dict[str, Any],
        *,
        caller: str,
        trace: Trace,
        ttl: float,
    ) -> AsyncIterator[ChainEvent]:
        agen = unit.handler(
            capability=capability,
            payload=payload,
            caller=caller,
            trace=trace,
            bus=self,
        )
        try:
            while True:
                try:
                    event = await asyncio.wait_for(agen.__anext__(), timeout=ttl)
                except StopAsyncIteration:
                    return
                except asyncio.TimeoutError as exc:
                    raise CapabilityError(
                        f"unit {unit.id!r} exceeded TTL={ttl}s for {capability!r}"
                    ) from exc
                yield event
        finally:
            await agen.aclose()