"""Adapt a Skill (sync function) into a Capability."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import Any

from assistuff.config.schemas import SkillManifest
from assistuff.skills.registry import Skill, SkillContext

from ..capability_bus import Capability
from ..events import ChainEvent
from ..trace import Trace

logger = logging.getLogger(__name__)


def make_skill_capability(
    manifest: SkillManifest,
    skill: Skill,
    *,
    context_provider,
) -> Capability:
    """Wrap a Skill as a Capability.

    context_provider is called on each invocation to get the current
    SkillContext (profile, memory, user).
    """

    async def handler(
        *,
        capability: str,
        payload: dict[str, Any],
        caller: str,
        trace: Trace,
        bus,
    ) -> AsyncIterator[ChainEvent]:
        value = payload.get("value") or payload.get("input") or ""
        if not isinstance(value, str):
            yield ChainEvent(
                trace_id=trace.trace_id,
                source=manifest.id,
                kind="error",
                payload={"reason": "invalid_payload", "expected": "string value"},
            )
            return

        context: SkillContext = context_provider()

        try:
            result = skill.run(value, context)
        except Exception as exc:
            logger.exception("skill %s failed", manifest.id)
            yield ChainEvent(
                trace_id=trace.trace_id,
                source=manifest.id,
                kind="error",
                payload={"reason": str(exc)},
            )
            return

        yield ChainEvent(
            trace_id=trace.trace_id,
            source=manifest.id,
            kind="result",
            payload={"text": result},
        )

    caps = manifest.capabilities.provides or [manifest.id]
    accepts = manifest.interop.accepts_calls_from or ["*"]
    return Capability(
        id=manifest.id,
        capabilities=list(caps),
        handler=handler,
        accepts_calls_from=list(accepts),
        can_call=list(manifest.interop.can_call),
        min_level=manifest.access.min_level if manifest.access else 0,
    )