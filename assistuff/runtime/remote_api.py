"""OpenAI-compatible remote chat-completions client."""

from __future__ import annotations

import json
import logging
import os
from typing import Any

import httpx
import keyring
from keyring.errors import KeyringError

from assistuff.config.api_connections import KEYRING_SERVICE
from assistuff.config.schemas import RemoteEndpointConfig

logger = logging.getLogger(__name__)


class RemoteApiError(RuntimeError):
    """A remote provider request failed without exposing its response body."""


class OpenAICompatibleClient:
    def __init__(
        self,
        config: RemoteEndpointConfig,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.config = config
        self._client = httpx.AsyncClient(
            base_url=f"{config.base_url}/",
            timeout=httpx.Timeout(
                connect=config.connect_timeout_seconds,
                read=config.read_timeout_seconds,
                write=config.read_timeout_seconds,
                pool=config.connect_timeout_seconds,
            ),
            transport=transport,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def generate(
        self,
        *,
        model: str,
        prompt: str,
        system: str | None = None,
        format: str | None = None,
        options: dict[str, Any] | None = None,
    ) -> str:
        api_key = os.environ.get(self.config.api_key_env, "").strip()
        if not api_key:
            try:
                api_key = (
                    keyring.get_password(KEYRING_SERVICE, self.config.api_key_env) or ""
                ).strip()
            except KeyringError as exc:
                raise RemoteApiError(
                    "the operating system credential store could not provide the API key"
                ) from exc
        if not api_key:
            raise RemoteApiError(
                f"API key is not configured for {self.config.api_key_env}"
            )

        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
        }
        if options:
            payload.update(options)
        if format == "json":
            payload["response_format"] = {"type": "json_object"}

        data = await self._post(payload, api_key)
        try:
            choices = data["choices"]
            message = choices[0]["message"]
            text = message["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RemoteApiError("provider returned a malformed chat completion") from exc
        if not isinstance(text, str) or not text.strip():
            raise RemoteApiError("provider returned an empty chat completion")
        usage = data.get("usage")
        if isinstance(usage, dict):
            logger.info(
                "remote completion: provider=%s model=%s prompt_tokens=%s "
                "completion_tokens=%s",
                self.config.provider,
                model,
                usage.get("prompt_tokens", "unknown"),
                usage.get("completion_tokens", "unknown"),
            )
        return text.strip()

    async def generate_json(
        self,
        *,
        model: str,
        prompt: str,
        system: str | None = None,
        options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        raw = await self.generate(
            model=model,
            prompt=prompt,
            system=system,
            format="json",
            options=options,
        )
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RemoteApiError("provider returned invalid JSON") from exc
        if not isinstance(value, dict):
            raise RemoteApiError("provider returned JSON that is not an object")
        return value

    async def _post(
        self,
        payload: dict[str, Any],
        api_key: str,
    ) -> dict[str, Any]:
        attempts = self.config.max_retries + 1
        for attempt in range(attempts):
            try:
                response = await self._client.post(
                    "chat/completions",
                    json=payload,
                    headers={"Authorization": f"Bearer {api_key}"},
                )
            except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
                if attempt + 1 < attempts:
                    continue
                raise RemoteApiError(
                    f"could not connect to remote provider ({type(exc).__name__})"
                ) from exc
            except httpx.HTTPError as exc:
                raise RemoteApiError(
                    f"remote provider request failed ({type(exc).__name__})"
                ) from exc

            if response.status_code >= 400:
                raise RemoteApiError(
                    f"remote provider returned HTTP {response.status_code}"
                )
            try:
                data = response.json()
            except (json.JSONDecodeError, ValueError) as exc:
                raise RemoteApiError("remote provider returned invalid JSON") from exc
            if not isinstance(data, dict):
                raise RemoteApiError("remote provider returned an invalid response")
            return data

        raise RemoteApiError("remote provider connection retries exhausted")
