import asyncio
import unittest
from types import SimpleNamespace

from assistuff.bus.adapters.model_adapter import _callable_capabilities
from assistuff.bus.capability_bus import Capability, CapabilityBus, InteropDenied
from assistuff.bus.events import ChainEvent
from assistuff.bus.output_chain import OutputChain
from assistuff.bus.trace import Trace
from assistuff.config.schemas import ModelManifest
from assistuff.router.capability_router import CapabilityRouter


def _capability(
    unit_id: str,
    provided: str,
    *,
    can_call: list[str] | None = None,
) -> Capability:
    async def handler(*, trace, **_kwargs):
        yield ChainEvent(
            trace_id=trace.trace_id,
            source=unit_id,
            kind="result",
            payload={"text": "ok"},
        )

    return Capability(
        id=unit_id,
        capabilities=[provided],
        handler=handler,
        can_call=can_call or [],
    )


class CapabilityInteropTests(unittest.TestCase):
    def test_llm_router_prompt_formats_json_example(self) -> None:
        class FakeRoles:
            prompt = ""

            async def generate_json(self, role, prompt, *, schema):
                self.prompt = prompt
                self.asserted_role = role
                self.asserted_schema = schema
                return {"capability": "answer.general", "reason": "general"}

        async def run() -> None:
            bus = CapabilityBus(OutputChain())
            bus.register(_capability("general", "answer.general"))
            roles = FakeRoles()
            router = CapabilityRouter(
                bus,
                roles,
                None,
                SimpleNamespace(models={}, skills={}),
            )

            route = await router.route("Explain a lantern in the woods")

            self.assertEqual(route.capability, "answer.general")
            self.assertIn(
                'Return JSON: {"capability": "<name>", "reason": "<short>"}',
                roles.prompt,
            )
            self.assertEqual(roles.asserted_role, "router")
            self.assertEqual(roles.asserted_schema["required"], ["capability"])

        asyncio.run(run())

    def test_final_result_ignores_closed_queue_sentinel(self) -> None:
        chain = OutputChain()
        event = ChainEvent(
            trace_id="finished",
            source="model",
            kind="result",
            payload={"text": "The answer."},
        )
        chain.emit(event)
        chain.close("finished")

        self.assertEqual(chain.events("finished"), [event])
        self.assertEqual(chain.final_result("finished"), "The answer.")

    def test_model_cannot_call_peer_capability_not_in_can_call(self) -> None:
        async def run() -> None:
            bus = CapabilityBus(OutputChain())
            bus.register(_capability("model-a", "answer.a"))
            bus.register(_capability("model-b", "answer.b"))

            with self.assertRaisesRegex(
                InteropDenied,
                "model-a.*not allowed to call.*answer.b",
            ):
                async for _ in bus.call(
                    "answer.b",
                    {},
                    caller="model-a",
                    trace=Trace(query="test"),
                ):
                    pass

        asyncio.run(run())

    def test_model_can_call_peer_capability_when_permitted(self) -> None:
        async def run() -> None:
            bus = CapabilityBus(OutputChain())
            bus.register(
                _capability("model-a", "answer.a", can_call=["answer.b"])
            )
            bus.register(_capability("model-b", "answer.b"))

            events = [
                event
                async for event in bus.call(
                    "answer.b",
                    {},
                    caller="model-a",
                    trace=Trace(query="test"),
                )
            ]

            self.assertEqual(len(events), 1)
            self.assertEqual(events[0].payload["text"], "ok")

        asyncio.run(run())

    def test_user_entry_call_is_not_restricted_by_model_can_call(self) -> None:
        async def run() -> None:
            bus = CapabilityBus(OutputChain())
            bus.register(_capability("model-b", "answer.b"))

            events = [
                event
                async for event in bus.call(
                    "answer.b",
                    {},
                    caller="user",
                    trace=Trace(query="test"),
                )
            ]

            self.assertEqual(len(events), 1)

        asyncio.run(run())

    def test_wildcard_exposes_peer_capabilities_to_model_tool_loop(self) -> None:
        bus = CapabilityBus(OutputChain())
        bus.register(_capability("model-a", "answer.a"))
        bus.register(_capability("model-b", "answer.b"))
        manifest = ModelManifest.model_validate({
            "id": "model-a",
            "version": "1.0.0",
            "runtime": {"tag": "model-a:latest"},
            "interop": {"can_call": ["*"]},
        })

        self.assertEqual(
            _callable_capabilities(manifest, bus),
            ["answer.a", "answer.b"],
        )

    def test_nested_call_keeps_complete_path_without_duplicate_trace_events(self) -> None:
        async def run() -> None:
            bus = CapabilityBus(OutputChain())
            bus.register(_capability("model-b", "answer.b"))
            trace = Trace(query="test")

            async def caller_handler(*, trace, bus, **_kwargs):
                async for event in bus.call(
                    "answer.b",
                    {},
                    caller="model-a",
                    trace=trace,
                ):
                    yield event

            bus.register(Capability(
                id="model-a",
                capabilities=["answer.a"],
                handler=caller_handler,
                can_call=["answer.b"],
            ))
            events = [
                event
                async for event in bus.call(
                    "answer.a",
                    {},
                    caller="user",
                    trace=trace,
                )
            ]

            self.assertEqual(len(events), 1)
            self.assertEqual(events[0].call_stack, ("model-a", "model-b"))
            self.assertEqual(len(trace.events), 1)

        asyncio.run(run())
