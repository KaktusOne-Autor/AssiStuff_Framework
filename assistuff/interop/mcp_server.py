"""MCP stdio server exposing registered, permission-checked skill capabilities."""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from typing import Any, TextIO

from assistuff.bus.trace import Trace

logger = logging.getLogger(__name__)

_SUPPORTED_PROTOCOLS = {
    "2024-11-05",
    "2025-03-26",
    "2025-06-18",
    "2025-11-25",
}


class McpToolServer:
    def __init__(self, dispatcher) -> None:
        self.dispatcher = dispatcher
        self._tools: dict[str, tuple[str, Any]] = {}
        self._refresh_tools()

    def _refresh_tools(self) -> None:
        manifests = getattr(self.dispatcher, "skill_manifests", {})
        units = {unit.id: unit for unit in self.dispatcher.bus.units()}
        ambiguous: set[str] = set()
        for skill_id, manifest in manifests.items():
            unit = units.get(skill_id)
            if unit is None:
                continue
            capabilities = manifest.capabilities.provides or [skill_id]
            for capability in capabilities:
                if capability in self._tools:
                    ambiguous.add(capability)
                self._tools[capability] = (skill_id, manifest)
        for capability in ambiguous:
            logger.warning("MCP capability %s has multiple providers; not exposing it", capability)
            self._tools.pop(capability, None)

    async def handle(self, request: Any) -> dict[str, Any] | None:
        if not isinstance(request, dict) or request.get("jsonrpc") != "2.0":
            return _error(request.get("id") if isinstance(request, dict) else None,
                          -32600, "Invalid Request")
        method = request.get("method")
        request_id = request.get("id")
        if not isinstance(method, str):
            return _error(request_id, -32600, "Invalid Request")
        params = request.get("params") or {}
        if not isinstance(params, dict):
            return _error(request_id, -32602, "Invalid params")
        if method.startswith("notifications/"):
            return None

        try:
            if method == "initialize":
                result = self._initialize(params)
            elif method == "ping":
                result = {}
            elif method == "tools/list":
                result = self._list_tools()
            elif method == "tools/call":
                result = await self._call_tool(params)
            else:
                return _error(request_id, -32601, "Method not found")
        except ValueError as exc:
            return _error(request_id, -32602, str(exc))
        except Exception as exc:
            logger.exception("MCP request %s failed", method)
            if method == "tools/call":
                result = _tool_error(str(exc))
            else:
                return _error(request_id, -32603, "Internal error")
        return {"jsonrpc": "2.0", "id": request_id, "result": result}

    def _initialize(self, params: dict[str, Any]) -> dict[str, Any]:
        requested = params.get("protocolVersion")
        if not isinstance(requested, str):
            raise ValueError("protocolVersion is required")
        if requested not in _SUPPORTED_PROTOCOLS:
            raise ValueError("unsupported MCP protocol version")
        return {
            "protocolVersion": requested,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {
                "name": "assistuff",
                "version": self.dispatcher.config.framework.framework.version,
            },
        }

    def _list_tools(self) -> dict[str, Any]:
        tools: list[dict[str, Any]] = []
        for capability, (skill_id, manifest) in sorted(self._tools.items()):
            input_schema = manifest.input_schema or {
                "type": "object",
                "properties": {"value": {"type": "string"}},
                "required": ["value"],
                "additionalProperties": False,
            }
            tools.append(
                {
                    "name": capability,
                    "description": manifest.description or f"AssiStuff skill {skill_id}",
                    "inputSchema": input_schema,
                }
            )
        return {"tools": tools}

    async def _call_tool(self, params: dict[str, Any]) -> dict[str, Any]:
        name = params.get("name")
        arguments = params.get("arguments", {})
        if not isinstance(name, str) or name not in self._tools:
            return _tool_error("Unknown or disabled skill capability")
        if not isinstance(arguments, dict):
            raise ValueError("tool arguments must be a JSON object")

        skill_id, manifest = self._tools[name]
        payload = (
            {"value": json.dumps(arguments, ensure_ascii=False)}
            if manifest.input_schema is not None
            else arguments
        )
        trace = Trace(query=f"MCP tool call: {name}")
        results: list[str] = []
        failed = False
        async for event in self.dispatcher.bus.call(
            name,
            payload,
            caller="mcp",
            trace=trace,
        ):
            if event.kind == "result":
                text = event.payload.get("text")
                if isinstance(text, str):
                    results.append(text)
            elif event.kind == "error":
                failed = True
                reason = event.payload.get("reason", "capability failed")
                results.append(str(reason))
        if not results:
            results.append(f"Skill {skill_id} returned no content")
            failed = True
        return {
            "content": [{"type": "text", "text": "\n".join(results)}],
            "isError": failed,
        }

    async def serve_stdio(
        self,
        input_stream: TextIO | None = None,
        output_stream: TextIO | None = None,
    ) -> None:
        input_stream = input_stream or sys.stdin
        output_stream = output_stream or sys.stdout
        while True:
            line = await asyncio.to_thread(input_stream.readline)
            if not line:
                return
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                response = _error(None, -32700, "Parse error")
            else:
                response = await self.handle(message)
            if response is not None:
                output_stream.write(json.dumps(response, ensure_ascii=False) + "\n")
                output_stream.flush()


def _error(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": code, "message": message},
    }


def _tool_error(message: str) -> dict[str, Any]:
    return {
        "content": [{"type": "text", "text": message}],
        "isError": True,
    }
