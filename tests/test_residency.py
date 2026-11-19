import asyncio
from types import SimpleNamespace
import unittest

from pydantic import ValidationError

from assistuff.config.schemas import ResidencyConfig
from assistuff.runtime.residency import ModelResidency, ResidencyError


class FakeOllamaClient:
    def __init__(self, loaded: set[str] | None = None) -> None:
        self.loaded = set(loaded or ())
        self.loads: list[tuple[str, str]] = []
        self.unloads: list[str] = []

    async def loaded_models(self) -> set[str]:
        return set(self.loaded)

    async def load(self, model: str, *, keep_alive: str) -> None:
        self.loads.append((model, keep_alive))
        self.loaded.add(model)

    async def unload(self, model: str) -> None:
        self.unloads.append(model)
        self.loaded.discard(model)


def make_config(residency: ResidencyConfig):
    models = {
        "background": SimpleNamespace(
            runtime=SimpleNamespace(tag="background:latest")
        ),
        "on-demand": SimpleNamespace(
            runtime=SimpleNamespace(tag="on-demand:latest")
        ),
    }
    framework = SimpleNamespace(
        runtime=SimpleNamespace(
            residency=residency,
            utility_models=SimpleNamespace(
                router="router:latest",
                planner="planner:latest",
                mpa="mpa:latest",
                compiler=None,
            ),
        )
    )
    return SimpleNamespace(framework=framework, models=models)


class ModelResidencyTests(unittest.TestCase):
    def test_hot_plug_evicts_an_unprotected_model_at_capacity(self) -> None:
        async def run() -> None:
            client = FakeOllamaClient({"old:latest"})
            residency = ModelResidency(
                client,
                make_config(ResidencyConfig(max_loaded=1)),
            )

            await residency.ensure_loaded("on-demand:latest")

            self.assertEqual(client.unloads, ["old:latest"])
            self.assertEqual(client.loads, [("on-demand:latest", "5m")])
            self.assertEqual(client.loaded, {"on-demand:latest"})

        asyncio.run(run())

    def test_selected_background_model_loads_with_indefinite_keep_alive(self) -> None:
        async def run() -> None:
            client = FakeOllamaClient()
            config = make_config(
                ResidencyConfig(
                    mode="selected_for_background",
                    background_models=["background"],
                    max_loaded=1,
                )
            )
            residency = ModelResidency(client, config)

            self.assertEqual(await residency.initialize(), {})
            self.assertEqual(client.loads, [("background:latest", "-1")])
            self.assertEqual(
                residency.protected_models(),
                {"background:latest"},
            )

        asyncio.run(run())

    def test_pinned_model_is_warmed_in_hot_plug_mode(self) -> None:
        async def run() -> None:
            client = FakeOllamaClient()
            residency = ModelResidency(
                client,
                make_config(
                    ResidencyConfig(
                        pinned=["background"],
                        max_loaded=1,
                    )
                ),
            )

            self.assertEqual(await residency.initialize(), {})
            self.assertEqual(client.loads, [("background:latest", "-1")])

        asyncio.run(run())

    def test_pinned_model_already_loaded_gets_indefinite_keep_alive(self) -> None:
        async def run() -> None:
            client = FakeOllamaClient({"background:latest"})
            residency = ModelResidency(
                client,
                make_config(
                    ResidencyConfig(
                        pinned=["background"],
                        max_loaded=1,
                    )
                ),
            )

            self.assertEqual(await residency.initialize(), {})
            self.assertEqual(client.loads, [("background:latest", "-1")])

        asyncio.run(run())

    def test_selected_background_models_cannot_be_evicted(self) -> None:
        async def run() -> None:
            client = FakeOllamaClient({"background:latest"})
            config = make_config(
                ResidencyConfig(
                    mode="selected_for_background",
                    background_models=["background"],
                    max_loaded=1,
                )
            )
            residency = ModelResidency(client, config)

            with self.assertRaisesRegex(
                ResidencyError,
                "all loaded models are pinned",
            ):
                await residency.ensure_loaded("on-demand:latest")

            self.assertEqual(client.unloads, [])

        asyncio.run(run())

    def test_selected_background_models_must_fit_the_load_limit(self) -> None:
        with self.assertRaisesRegex(
            ValidationError,
            "pinned and background models cannot exceed",
        ):
            ResidencyConfig(
                mode="selected_for_background",
                background_models=["first", "second"],
                max_loaded=1,
            )
        with self.assertRaisesRegex(
            ValidationError,
            "pinned and background models cannot exceed",
        ):
            ResidencyConfig(
                pinned=["first", "second"],
                max_loaded=1,
            )
