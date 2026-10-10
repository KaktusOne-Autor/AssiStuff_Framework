"""Adapt a Model (LLM) into a Capability with a tool-calling loop."""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from typing import Any

from assistuff.config.schemas import ModelManifest
from assistuff.runtime.model_runtime import ModelRuntime

from ..capability_bus import Capability
from ..events import ChainEvent
from ..trace import Trace

logger = logging.getLogger(__name__)

_TOOL_CALL_SYSTEM = """You are a peer in a capability graph.

You may either answer the user directly, or call another capability.

To call a capability, respond with ONLY JSON:
{"call": "<capability_name>", "payload": {"value": "<text>"}}

To answer, respond with plain text (no JSON).

Available capabilities you may call:
{available}

Call a capability only when you need information you do not have.
When you have enough information, answer directly.
"""


def make_model_capability(
    manifest: ModelManifest,
    runtime: ModelRuntime,
) -> Capability:
    async def handler(
        *,
        capability: str,
        payload: dict[str, Any],
        caller: str,
        trace: Trace,
        bus,
    ) -> AsyncIterator[ChainEvent]:
        query = payload.get("value") or payload.get("input") or ""
        if not isinstance(query, str) or not query.strip():
            yield ChainEvent(
                trace_id=trace.trace_id,
                source=manifest.id,
                kind="error",
                payload={"reason": "empty_query"},
            )
            return

        callable_caps = list(manifest.interop.can_call or [])
        prompt = query
        max_iterations = 5

        for iteration in range(max_iterations):
            system = runtime.build_system_prompt()
            if callable_caps:
                system = system + "\n\n" + _TOOL_CALL_SYSTEM.format(
                    available=", ".join(callable_caps)
                )

            try:
                raw = await runtime.generate(prompt, system=system)
            except Exception as exc:
                logger.exception("model %s failed", manifest.id)
                yield ChainEvent(
                    trace_id=trace.trace_id,
                    source=manifest.id,
                    kind="error",
                    payload={"reason": str(exc)},
                )
                return

            tool_call = _parse_tool_call(raw)
            if tool_call is None:
                yield ChainEvent(
                    trace_id=trace.trace_id,
                    source=manifest.id,
                    kind="result",
                    payload={"text": raw},
                )
                return

            cap_name, cap_payload = tool_call
            if cap_name not in callable_caps:
                logger.warning(
                    "model %s tried to call %r which is not in can_call",
                    manifest.id,
                    cap_name,
                )
                prompt = (
                    f"{query}\n\n"
                    f"You tried to call {cap_name!r}, but you may only call: "
                    f"{', '.join(callable_caps)}. Answer directly."
                )
                continue

            collected: list[str] = []
            try:
                async for event in bus.call(
                    cap_name,
                    cap_payload,
                    caller=manifest.id,
                    trace=trace,
                ):
                    if event.kind == "result":
                        text = event.payload.get("text")
                        if isinstance(text, str):
                            collected.append(text)
            except Exception as exc:
                logger.exception("call to %s failed", cap_name)
                prompt = (
                    f"{query}\n\n"
                    f"Call to {cap_name!r} failed: {exc}. Answer directly."
                )
                continue

            joined = "\n".join(collected) if collected else "(no result)"
            prompt = (
                f"{query}\n\n"
                f"Result of {cap_name!r}:\n{joined}\n\n"
                f"Now answer the user directly."
            )

        # Loop exhausted
        yield ChainEvent(
            trace_id=trace.trace_id,
            source=manifest.id,
            kind="result",
            payload={"text": raw},
        )

    caps = manifest.capabilities.provides or [manifest.id]
    return Capability(
        id=manifest.id,
        capabilities=list(caps),
        handler=handler,
        accepts_calls_from=list(manifest.interop.accepts_calls_from or ["*"]),
        can_call=list(manifest.interop.can_call or []),
        min_level=manifest.access.min_level if manifest.access else 0,
    )


def _parse_tool_call(raw: str) -> tuple[str, dict] | None:
    text = raw.strip()
    if not text.startswith("{"):
        return None
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict) or "call" not in data:
        return None
    cap = data.get("call")
    payload = data.get("payload") or {}
    if not isinstance(cap, str) or not isinstance(payload, dict):
        return None
    return cap, payload