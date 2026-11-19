"""Async Ollama client."""

from __future__ import annotations

import json
import logging
import time
from typing import Any

import httpx

from assistuff.config.schemas import OllamaConfig

logger = logging.getLogger(__name__)


class OllamaError(RuntimeError):
    pass


class OllamaTimeout(OllamaError):
    pass


class OllamaClient:
    def __init__(self, config: OllamaConfig) -> None:
        self.config = config
        self._client = httpx.AsyncClient(
            base_url=config.host,
            timeout=httpx.Timeout(
                connect=10.0,
                read=float(config.read_timeout_seconds),
                write=30.0,
                pool=30.0,
            ),
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "OllamaClient":
        return self

    async def __aexit__(self, *_exc) -> None:
        await self.aclose()

    # ------------------------------------------------------------------
    # HTTP primitives
    # ------------------------------------------------------------------

    async def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            response = await self._client.post(path, json=payload)
        except httpx.ReadTimeout as exc:
            raise OllamaTimeout(
                f"Ollama did not respond within "
                f"{self.config.read_timeout_seconds}s"
            ) from exc
        except httpx.HTTPError as exc:
            raise OllamaError(f"Ollama request failed: {exc}") from exc

        if response.status_code >= 400:
            detail = response.text.strip() or response.reason_phrase
            raise OllamaError(f"Ollama HTTP {response.status_code}: {detail}")

        try:
            return response.json()
        except json.JSONDecodeError as exc:
            raise OllamaError(f"Ollama returned invalid JSON: {exc}") from exc

    async def _get(self, path: str) -> dict[str, Any]:
        try:
            response = await self._client.get(path)
        except httpx.HTTPError as exc:
            raise OllamaError(f"Ollama request failed: {exc}") from exc
        if response.status_code >= 400:
            raise OllamaError(f"Ollama HTTP {response.status_code}: {response.text}")
        return response.json()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def list_models(self) -> set[str]:
        data = await self._get("/api/tags")
        return {str(m.get("name", "")) for m in data.get("models", [])}

    async def loaded_models(self) -> set[str]:
        data = await self._get("/api/ps")
        return {str(m.get("name", "")) for m in data.get("models", [])}

    async def generate(
        self,
        *,
        model: str,
        prompt: str,
        system: str | None = None,
        format: str | dict[str, Any] | None = None,
        options: dict[str, Any] | None = None,
        keep_alive: str | None = None,
    ) -> str:
        payload: dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "keep_alive": keep_alive or self.config.keep_alive,
        }
        if system:
            payload["system"] = system
        if format is not None:
            payload["format"] = format
        if options:
            payload["options"] = options

        started = time.perf_counter()
        data = await self._post("/api/generate", payload)
        elapsed = time.perf_counter() - started

        eval_count = int(data.get("eval_count", 0) or 0)
        eval_duration_ns = float(data.get("eval_duration", 0) or 0)
        tps = eval_count / (eval_duration_ns / 1e9) if eval_duration_ns else 0.0

        logger.info(
            "Ollama generate: model=%s elapsed=%.2fs prompt_tokens=%d "
            "generated=%d tps=%.1f",
            model,
            elapsed,
            int(data.get("prompt_eval_count", 0) or 0),
            eval_count,
            tps,
        )

        text = str(data.get("response", "")).strip()
        if not text:
            raise OllamaError(f"Ollama returned empty response for model {model}")
        return text

    async def generate_json(
        self,
        *,
        model: str,
        prompt: str,
        system: str | None = None,
        schema: dict[str, Any] | None = None,
        options: dict[str, Any] | None = None,
        keep_alive: str | None = None,
    ) -> dict[str, Any]:
        fmt: str | dict[str, Any] = schema if schema else "json"
        raw = await self.generate(
            model=model,
            prompt=prompt,
            system=system,
            format=fmt,
            options=options,
            keep_alive=keep_alive,
        )
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise OllamaError(f"model {model} returned invalid JSON: {raw[:200]!r}") from exc
        if not isinstance(parsed, dict):
            raise OllamaError(f"model {model} returned JSON that is not an object")
        return parsed

    async def load(self, model: str, *, keep_alive: str | None = None) -> None:
        """Warm up a model without generating."""
        await self._post("/api/generate", {
            "model": model,
            "prompt": "",
            "stream": False,
            "keep_alive": keep_alive or self.config.keep_alive,
        })

    async def unload(self, model: str) -> None:
        await self._post("/api/generate", {
            "model": model,
            "prompt": "",
            "stream": False,
            "keep_alive": "0s",
        })