from __future__ import annotations

import asyncio
import json
import os
import unittest
from unittest.mock import patch

import httpx
from pydantic import ValidationError

from assistuff.config.loader import load_runtime_config
from assistuff.config.schemas import ModelManifest, RemoteEndpointConfig
from assistuff.runtime.model_runtime import ModelRuntime
from assistuff.runtime.ollama import OllamaClient
from assistuff.runtime.remote_api import OpenAICompatibleClient, RemoteApiError


class RemoteApiTests(unittest.TestCase):
    def test_requires_https_unless_http_is_explicitly_allowed(self) -> None:
        with self.assertRaises(ValidationError):
            RemoteEndpointConfig(
                base_url="http://provider.example/v1",
                api_key_env="TEST_REMOTE_KEY",
                allow_insecure_http=True,
            )

        config = RemoteEndpointConfig(
            base_url="http://127.0.0.1:8080/v1",
            api_key_env="TEST_REMOTE_KEY",
            allow_insecure_http=True,
        )
        self.assertEqual(config.base_url, "http://127.0.0.1:8080/v1")

    def test_sends_chat_request_and_parses_json_object(self) -> None:
        requests: list[httpx.Request] = []

        def respond(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(
                200,
                json={
                    "choices": [{"message": {"content": '{"answer": 42}'}}],
                    "usage": {"prompt_tokens": 3, "completion_tokens": 2},
                },
            )

        config = RemoteEndpointConfig(
            base_url="https://provider.example/v1",
            api_key_env="TEST_REMOTE_KEY",
        )
        client = OpenAICompatibleClient(
            config,
            transport=httpx.MockTransport(respond),
        )

        async def run() -> dict:
            try:
                return await client.generate_json(
                    model="provider-model",
                    system="Be concise",
                    prompt="Return a JSON object",
                )
            finally:
                await client.aclose()

        with patch.dict(os.environ, {"TEST_REMOTE_KEY": "test-secret"}):
            result = asyncio.run(run())

        self.assertEqual(result, {"answer": 42})
        self.assertEqual(requests[0].url.path, "/v1/chat/completions")
        self.assertEqual(
            requests[0].headers["Authorization"],
            "Bearer test-secret",
        )
        body = json.loads(requests[0].content)
        self.assertEqual(body["model"], "provider-model")
        self.assertEqual(body["response_format"], {"type": "json_object"})
        self.assertEqual(body["messages"][0], {
            "role": "system",
            "content": "Be concise",
        })

    def test_provider_error_does_not_expose_response_body_or_key(self) -> None:
        secret = "sensitive-test-key"

        def respond(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                401,
                text=f"invalid token: {secret}",
                request=request,
            )

        config = RemoteEndpointConfig(
            base_url="https://provider.example/v1",
            api_key_env="TEST_REMOTE_KEY",
        )
        client = OpenAICompatibleClient(
            config,
            transport=httpx.MockTransport(respond),
        )

        async def run() -> None:
            try:
                await client.generate(model="provider-model", prompt="hello")
            finally:
                await client.aclose()

        with (
            patch.dict(os.environ, {"TEST_REMOTE_KEY": secret}),
            self.assertRaises(RemoteApiError) as error,
        ):
            asyncio.run(run())

        self.assertIn("HTTP 401", str(error.exception))
        self.assertNotIn(secret, str(error.exception))

    def test_missing_credential_fails_before_network_request(self) -> None:
        config = RemoteEndpointConfig(
            base_url="https://provider.example/v1",
            api_key_env="MISSING_REMOTE_KEY_FOR_TEST",
        )
        client = OpenAICompatibleClient(
            config,
            transport=httpx.MockTransport(
                lambda request: httpx.Response(500, request=request)
            ),
        )

        async def run() -> None:
            try:
                await client.generate(model="provider-model", prompt="hello")
            finally:
                await client.aclose()

        with (
            patch.dict(os.environ, {}, clear=True),
            self.assertRaisesRegex(RemoteApiError, "MISSING_REMOTE_KEY_FOR_TEST"),
        ):
            asyncio.run(run())

    def test_reads_api_key_from_os_credential_store(self) -> None:
        requests: list[httpx.Request] = []

        def respond(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(
                200,
                json={"choices": [{"message": {"content": "ok"}}]},
            )

        client = OpenAICompatibleClient(
            RemoteEndpointConfig(
                base_url="https://provider.example/v1",
                api_key_env="KEYRING_REMOTE_KEY",
            ),
            transport=httpx.MockTransport(respond),
        )

        async def run() -> str:
            try:
                return await client.generate(model="provider-model", prompt="hello")
            finally:
                await client.aclose()

        with (
            patch.dict(os.environ, {}, clear=True),
            patch(
                "assistuff.runtime.remote_api.keyring.get_password",
                return_value="keyring-secret",
            ) as get_password,
        ):
            result = asyncio.run(run())

        self.assertEqual(result, "ok")
        self.assertEqual(requests[0].headers["Authorization"], "Bearer keyring-secret")
        get_password.assert_called_once_with(
            "AssiStuff OpenAI-compatible API",
            "KEYRING_REMOTE_KEY",
        )

    def test_model_runtime_uses_remote_adapter_without_ollama(self) -> None:
        requests: list[httpx.Request] = []

        def respond(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(
                200,
                json={"choices": [{"message": {"content": "remote answer"}}]},
            )

        config = load_runtime_config()
        manifest = ModelManifest.model_validate({
            "id": "remote-test",
            "version": "1.0.0",
            "runtime": {
                "backend": "remote_api",
                "provider": "openai_compatible",
                "endpoint_profile": "test-provider",
                "tag": "remote-model-id",
            },
        })
        remote_client = OpenAICompatibleClient(
            RemoteEndpointConfig(
                base_url="https://provider.example/v1",
                api_key_env="TEST_REMOTE_KEY",
            ),
            transport=httpx.MockTransport(respond),
        )
        ollama_client = OllamaClient(config.framework.runtime.ollama)
        runtime = ModelRuntime(
            manifest,
            ollama_client,
            config,
            remote_client=remote_client,
        )

        async def run() -> str:
            try:
                return await runtime.generate("hello", system="system")
            finally:
                await remote_client.aclose()
                await ollama_client.aclose()

        with patch.dict(os.environ, {"TEST_REMOTE_KEY": "test-secret"}):
            result = asyncio.run(run())

        self.assertEqual(result, "remote answer")
        self.assertEqual(
            json.loads(requests[0].content)["model"],
            "remote-model-id",
        )


if __name__ == "__main__":
    unittest.main()
