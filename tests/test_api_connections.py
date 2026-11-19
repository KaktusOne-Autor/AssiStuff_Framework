from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from assistuff.config.api_connections import save_api_connection
from assistuff.config.loader import load_runtime_config


class ApiConnectionTests(unittest.TestCase):
    def test_saves_model_and_endpoint_without_saving_the_api_key(self) -> None:
        secret = "test-api-secret"
        with tempfile.TemporaryDirectory() as temporary:
            user_root = Path(temporary)
            with patch("assistuff.config.api_connections.keyring.set_password") as store:
                manifest = save_api_connection(
                    user_root,
                    profile="test-provider",
                    model_id="test-remote",
                    model_name="vendor/model-v1",
                    base_url="https://api.example/v1",
                    api_key=secret,
                )

            store.assert_called_once_with(
                "AssiStuff OpenAI-compatible API",
                "ASSISTUFF_API_TEST_PROVIDER",
                secret,
            )
            config_path = user_root / "config" / "apis.yaml"
            self.assertNotIn(secret, config_path.read_text(encoding="utf-8"))

            with patch(
                "assistuff.config.loader.get_user_root",
                return_value=user_root,
            ):
                config = load_runtime_config()

        self.assertEqual(config.models[manifest.id].runtime.backend, "remote_api")
        self.assertEqual(config.models[manifest.id].runtime.tag, "vendor/model-v1")
        self.assertEqual(
            config.framework.runtime.remote_endpoints["test-provider"].base_url,
            "https://api.example/v1",
        )

    def test_rejects_ids_that_collide_with_built_in_models(self) -> None:
        with (
            tempfile.TemporaryDirectory() as temporary,
            self.assertRaisesRegex(ValueError, "already exists"),
        ):
            save_api_connection(
                Path(temporary),
                profile="test-provider",
                model_id="simple",
                model_name="model",
                base_url="https://api.example/v1",
                api_key="test-key",
                existing_model_ids={"simple"},
            )


if __name__ == "__main__":
    unittest.main()
