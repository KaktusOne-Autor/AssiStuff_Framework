from __future__ import annotations

import asyncio
import json
import unittest
from types import SimpleNamespace

from assistuff.bus.capability_bus import Capability, CapabilityBus
from assistuff.bus.events import ChainEvent
from assistuff.bus.output_chain import OutputChain
from assistuff.config.schemas import AccessSpec, ModelCapabilities, SkillManifest
from assistuff.interop.mcp_server import McpToolServer


def _server(min_level: int = 0):
    chain = OutputChain()
    bus = CapabilityBus(chain, user_level_getter=lambda: 0)
    received: list[dict] = []

    async def handler(**kwargs):
        received.append(kwargs["payload"])
        yield ChainEvent(
            trace_id=kwargs["trace"].trace_id,
            source="portable",
            kind="result",
            payload={"text": "skill output"},
        )

    bus.register(
        Capability(
            id="portable",
            capabilities=["portable.echo"],
            handler=handler,
            min_level=min_level,
        )
    )
    manifest = SkillManifest(
        id="portable",
        version="1.0.0",
        capabilities=ModelCapabilities(provides=["portable.echo"]),
        access=AccessSpec(min_level=min_level),
        instructions_file="SKILL.md",
        input_schema={
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        },
    )
    dispatcher = SimpleNamespace(
        bus=bus,
        skill_manifests={"portable": manifest},
        config=SimpleNamespace(
            framework=SimpleNamespace(
                framework=SimpleNamespace(version="1.0.0")
            )
        ),
    )
    return McpToolServer(dispatcher), received


class McpInteropTests(unittest.TestCase):
    def test_initialize_list_and_call_use_mcp_json_rpc(self) -> None:
        server, received = _server()

        async def run():
            initialized = await server.handle({
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {"protocolVersion": "2025-06-18"},
            })
            listed = await server.handle({
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/list",
                "params": {},
            })
            called = await server.handle({
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "portable.echo",
                    "arguments": {"text": "hello"},
                },
            })
            return initialized, listed, called

        initialized, listed, called = asyncio.run(run())
        self.assertEqual(initialized["result"]["protocolVersion"], "2025-06-18")
        self.assertEqual(listed["result"]["tools"][0]["name"], "portable.echo")
        self.assertFalse(called["result"]["isError"])
        self.assertEqual(called["result"]["content"][0]["text"], "skill output")
        self.assertEqual(received, [{"value": json.dumps({"text": "hello"})}])

    def test_guest_mcp_call_respects_pupc_minimum_level(self) -> None:
        server, _received = _server(min_level=2)
        response = asyncio.run(server.handle({
            "jsonrpc": "2.0",
            "id": "denied",
            "method": "tools/call",
            "params": {"name": "portable.echo", "arguments": {"text": "hello"}},
        }))
        self.assertTrue(response["result"]["isError"])
        self.assertIn("access_denied", response["result"]["content"][0]["text"])

    def test_unknown_method_and_unsupported_version_are_explicit_errors(self) -> None:
        server, _received = _server()
        unknown = asyncio.run(server.handle({
            "jsonrpc": "2.0",
            "id": 1,
            "method": "private/extension",
        }))
        version = asyncio.run(server.handle({
            "jsonrpc": "2.0",
            "id": 2,
            "method": "initialize",
            "params": {"protocolVersion": "future-version"},
        }))
        self.assertEqual(unknown["error"]["code"], -32601)
        self.assertEqual(version["error"]["code"], -32602)


if __name__ == "__main__":
    unittest.main()
