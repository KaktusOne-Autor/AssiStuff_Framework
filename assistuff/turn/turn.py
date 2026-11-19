"""Turn — handle a single user query end-to-end."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator

from assistuff.bus.capability_bus import CapabilityBus, CapabilityError
from assistuff.bus.events import ChainEvent
from assistuff.bus.output_chain import OutputChain
from assistuff.bus.trace import Trace
from assistuff.router.capability_router import CapabilityRouter
from assistuff.runtime.utility import UtilityRoles

from .memory_writer import MemoryWriter
from .session import Session
from .summarizer import Summarizer

logger = logging.getLogger(__name__)


class Turn:
    def __init__(
        self,
        bus: CapabilityBus,
        router: CapabilityRouter,
        output_chain: OutputChain,
        roles: UtilityRoles,
        *,
        summarizer: Summarizer | None = None,
        memory_writer: MemoryWriter | None = None,
    ) -> None:
        self.bus = bus
        self.router = router
        self.output_chain = output_chain
        self.roles = roles
        self.summarizer = summarizer or Summarizer(roles)
        self.memory_writer = memory_writer

    async def handle(self, session: Session, query: str) -> AsyncIterator[ChainEvent]:
        if not query or not query.strip():
            event = ChainEvent(
                trace_id="empty",
                source="turn",
                kind="error",
                payload={"reason": "empty query"},
            )
            yield event
            return

        trace = Trace(query=query)
        logger.info(
            "turn start: trace=%s profile=%s query=%r",
            trace.trace_id[:8],
            session.profile,
            query[:120],
        )

        try:
            route = await self.router.route(query)
        except Exception as exc:
            logger.exception("routing failed")
            event = ChainEvent(
                trace_id=trace.trace_id,
                source="router",
                kind="error",
                payload={"reason": str(exc)},
            )
            self.output_chain.emit(event)
            yield event
            self.output_chain.close(trace.trace_id)
            return

        logger.info(
            "turn route: trace=%s capability=%s unit=%s reason=%s",
            trace.trace_id[:8],
            route.capability,
            route.unit_id,
            route.reason,
        )

        final_text = ""
        working_memory = session.memory.new_working(trace.trace_id)
        async for event in self.bus.call(
            route.capability,
            {
                "value": query,
                "input": query,
                "_working_memory": working_memory,
            },
            caller="user",
            trace=trace,
        ):
            if event.kind == "result":
                text = event.payload.get("text")
                if isinstance(text, str):
                    final_text = text
            yield event

        trace.finish()
        self.output_chain.close(trace.trace_id)

        logger.info(
            "turn end: trace=%s hops=%d events=%d elapsed=%.0fms",
            trace.trace_id[:8],
            trace.hops,
            len(trace.events),
            trace.elapsed_ms,
        )

        if self.memory_writer is not None and final_text:
            summary = ""
            try:
                summary = await self.summarizer.summarize(query, final_text)
            except Exception:
                logger.exception("summarizer failed")
            await self.memory_writer.record(
                user_text=query,
                assistant_text=final_text,
                summary=summary,
            )