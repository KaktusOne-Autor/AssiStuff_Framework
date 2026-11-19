"""User-only voice capabilities exposed through the peer bus."""

from __future__ import annotations

import asyncio
import threading
from collections.abc import AsyncIterator, Mapping
from pathlib import Path
from typing import Any

from assistuff.bus.capability_bus import Capability
from assistuff.bus.events import ChainEvent
from assistuff.bus.trace import Trace
from assistuff.config.schemas import SkillManifest

from .audio import load_wav
from .pipeline import VoicePipeline


def make_voice_capabilities(
    pipeline: VoicePipeline,
    *,
    profile: str,
    manifests: Mapping[str, SkillManifest],
) -> list[Capability]:
    async def stt_handler(
        *,
        capability: str,
        payload: dict[str, Any],
        caller: str,
        trace: Trace,
        bus,
    ) -> AsyncIterator[ChainEvent]:
        path = _audio_path(payload)
        if path is None:
            yield _error(trace, capability, "payload requires an audio_path")
            return
        try:
            text = await pipeline.transcribe_file(path)
        except Exception as exc:
            yield _error(trace, capability, str(exc))
            return
        yield _result(trace, capability, {"text": text})

    async def auth_handler(
        *,
        capability: str,
        payload: dict[str, Any],
        caller: str,
        trace: Trace,
        bus,
    ) -> AsyncIterator[ChainEvent]:
        path = _audio_path(payload)
        if path is None:
            yield _error(trace, capability, "payload requires an audio_path")
            return
        try:
            clip = load_wav(path, pipeline.config.stt.sample_rate)
            score = pipeline.auth.verify(profile, clip)
        except Exception as exc:
            yield _error(trace, capability, str(exc))
            return
        yield _result(trace, capability, {"profile": profile, "similarity": score})

    async def tts_handler(
        *,
        capability: str,
        payload: dict[str, Any],
        caller: str,
        trace: Trace,
        bus,
    ) -> AsyncIterator[ChainEvent]:
        text = payload.get("text")
        if not isinstance(text, str) or not text.strip():
            yield _error(trace, capability, "payload requires non-empty text")
            return
        try:
            await asyncio.to_thread(pipeline.tts.speak, text)
        except Exception as exc:
            yield _error(trace, capability, str(exc))
            return
        yield _result(trace, capability, {"text": "spoken"})

    async def wake_handler(
        *,
        capability: str,
        payload: dict[str, Any],
        caller: str,
        trace: Trace,
        bus,
    ) -> AsyncIterator[ChainEvent]:
        timeout = payload.get("timeout_seconds", 15.0)
        if (
            isinstance(timeout, bool)
            or not isinstance(timeout, int | float)
            or not 0.1 <= timeout <= 120
        ):
            yield _error(trace, capability, "timeout_seconds must be between 0.1 and 120")
            return
        stop = threading.Event()
        try:
            phrase = await asyncio.to_thread(
                pipeline.listen_for_wake,
                stop,
                timeout_seconds=float(timeout),
            )
        except asyncio.CancelledError:
            stop.set()
            raise
        except Exception as exc:
            yield _error(trace, capability, str(exc))
            return
        yield _result(trace, capability, {"phrase": phrase or "", "detected": phrase is not None})

    handlers = (
        ("voice_stt", stt_handler),
        ("voice_auth", auth_handler),
        ("voice_tts", tts_handler),
        ("voice_wake", wake_handler),
    )
    capabilities: list[Capability] = []
    for manifest_id, handler in handlers:
        manifest = manifests.get(manifest_id)
        if manifest is None:
            raise ValueError(f"missing voice skill manifest: {manifest_id}")
        if not manifest.capabilities.provides:
            raise ValueError(f"voice skill manifest {manifest_id!r} provides no capabilities")
        capabilities.append(
            Capability(
                id=manifest.id,
                capabilities=manifest.capabilities.provides,
                handler=handler,
                accepts_calls_from=manifest.interop.accepts_calls_from,
                can_call=manifest.interop.can_call,
                min_level=manifest.access.min_level if manifest.access else 0,
                routable=False,
            )
        )
    return capabilities


def _audio_path(payload: dict[str, Any]) -> Path | None:
    value = payload.get("audio_path")
    if not isinstance(value, str) or not value.strip():
        return None
    return Path(value).expanduser().resolve()


def _error(trace: Trace, source: str, reason: str) -> ChainEvent:
    return ChainEvent(
        trace_id=trace.trace_id,
        source=source,
        kind="error",
        payload={"reason": reason},
    )


def _result(trace: Trace, source: str, payload: dict[str, Any]) -> ChainEvent:
    return ChainEvent(
        trace_id=trace.trace_id,
        source=source,
        kind="result",
        payload=payload,
    )
