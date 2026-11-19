from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from assistuff.bus.emitters.tts import TtsEmitter
from assistuff.bus.events import ChainEvent
from assistuff.bus.output_chain import OutputChain
from assistuff.config import load_runtime_config
from assistuff.config.schemas import VoiceAuthConfig
from assistuff.voice.audio import AudioClip, _load_numpy
from assistuff.voice.auth import VoiceAuthenticator, VoiceprintStore
from assistuff.voice.capabilities import make_voice_capabilities
from assistuff.voice.common import VoiceError
from assistuff.voice.pipeline import VoicePipeline
from assistuff.voice.stt import STTAdapter


class VoicePipelineTests(unittest.TestCase):
    def test_gui_audio_controls_are_disabled_in_default_config(self) -> None:
        runtime = load_runtime_config()

        self.assertFalse(runtime.framework.voice.enabled)

    def test_tts_emitter_receives_only_final_result(self) -> None:
        spoken: list[str] = []
        chain = OutputChain()
        chain.subscribe_final(TtsEmitter(spoken.append))
        chain.emit(
            ChainEvent(
                trace_id="turn",
                source="model",
                kind="result",
                payload={"text": "intermediate"},
            )
        )
        chain.emit(
            ChainEvent(
                trace_id="turn",
                source="assistant",
                kind="result",
                payload={"text": "final answer"},
            )
        )
        chain.close("turn")

        self.assertEqual(spoken, ["final answer"])

    def test_final_emitter_does_not_speak_when_turn_ends_in_error(self) -> None:
        spoken: list[str] = []
        chain = OutputChain()
        chain.subscribe_final(TtsEmitter(spoken.append))
        chain.emit(
            ChainEvent(
                trace_id="turn",
                source="tool",
                kind="result",
                payload={"text": "tool output"},
            )
        )
        chain.emit(
            ChainEvent(
                trace_id="turn",
                source="model",
                kind="error",
                payload={"reason": "model failed"},
            )
        )
        chain.close("turn")

        self.assertEqual(spoken, [])

    def test_voiceprint_permissions_and_profile_scoped_verification(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "profiles"
            store = VoiceprintStore(root)
            store.save("default", [1.0, 0.0], sample_count=5)
            store.save("other", [0.0, 1.0], sample_count=5)
            voiceprint = root / "default" / "voiceprint.json"
            self.assertEqual(voiceprint.stat().st_mode & 0o777, 0o600)

            auth = VoiceAuthenticator(
                VoiceAuthConfig(
                    enabled=True,
                    model_path="missing-language-model",
                    speaker_model_path="missing-speaker-model",
                    voiceprints_dir=str(root),
                    similarity_threshold=0.35,
                    minimum_margin=0.06,
                    enrollment_samples=5,
                    enrollment_max_seconds=45,
                ),
                sample_rate=16_000,
                project_root=Path(directory),
                store=store,
            )
            clip = AudioClip(pcm=b"\x00\x00", wav=b"", sample_rate=16_000)
            with patch.object(auth, "extract_embedding", return_value=[1.0, 0.0]):
                self.assertAlmostEqual(auth.verify("default", clip), 1.0)
            with (
                patch.object(auth, "extract_embedding", return_value=[0.0, 1.0]),
                self.assertRaisesRegex(VoiceError, "verification failed"),
            ):
                auth.verify("default", clip)

    def test_stt_setup_reports_missing_executable(self) -> None:
        from assistuff.config.schemas import SttConfig

        with tempfile.TemporaryDirectory() as directory:
            adapter = STTAdapter(
                SttConfig(
                    binary_path="missing-whisper-cli",
                    model_path="missing-model.bin",
                ),
                Path(directory),
            )
            with self.assertRaisesRegex(VoiceError, "executable"):
                adapter.validate_setup()

    def test_numpy_is_optional_until_audio_processing_is_requested(self) -> None:
        with (
            patch(
                "assistuff.voice.audio.importlib.import_module",
                side_effect=ImportError("numpy unavailable"),
            ),
            self.assertRaisesRegex(VoiceError, "requires numpy"),
        ):
            _load_numpy()

    def test_enrollment_sample_duration_obeys_total_limit(self) -> None:
        runtime = load_runtime_config()
        with tempfile.TemporaryDirectory() as directory:
            pipeline = VoicePipeline(
                runtime.framework.voice,
                project_root=Path(directory),
                user_root=Path(directory) / "user",
                profile="default",
            )
            clip = AudioClip(pcm=b"\x00\x00", wav=b"", sample_rate=16_000)
            with patch(
                "assistuff.voice.pipeline.record_microphone",
                return_value=clip,
            ) as record:
                self.assertIs(pipeline.capture_enrollment_sample(), clip)

            expected = min(
                runtime.framework.voice.stt.max_record_seconds,
                runtime.framework.voice.auth.enrollment_max_seconds
                / runtime.framework.voice.auth.enrollment_samples,
            )
            self.assertEqual(record.call_args.kwargs["max_record_seconds"], expected)

    def test_wake_diagnostics_check_language_model_without_auth(self) -> None:
        runtime = load_runtime_config()
        voice_config = runtime.framework.voice.model_copy(
            update={
                "auth": runtime.framework.voice.auth.model_copy(update={"enabled": False}),
                "wake": runtime.framework.voice.wake.model_copy(update={"enabled": True}),
            }
        )
        with tempfile.TemporaryDirectory() as directory:
            pipeline = VoicePipeline(
                voice_config,
                project_root=Path(directory),
                user_root=Path(directory) / "user",
                profile="default",
            )
            with patch("assistuff.voice.pipeline.importlib.util.find_spec", return_value=object()):
                diagnostics = pipeline.diagnostics()

        self.assertFalse(diagnostics["Vosk language model"][0])
        self.assertNotIn("Vosk speaker model", diagnostics)

    def test_voice_capabilities_are_loaded_from_user_only_manifests(self) -> None:
        runtime = load_runtime_config()
        with tempfile.TemporaryDirectory() as directory:
            pipeline = VoicePipeline(
                runtime.framework.voice,
                project_root=Path(directory),
                user_root=Path(directory) / "user",
                profile="default",
            )
            capabilities = make_voice_capabilities(
                pipeline,
                profile="default",
                manifests=runtime.skills,
            )

        provided = {name for capability in capabilities for name in capability.capabilities}
        self.assertEqual(
            provided,
            {
                "voice.stt.transcribe",
                "voice.auth.identify",
                "voice.tts.speak",
                "voice.wake.listen",
            },
        )
        self.assertTrue(
            all(
                capability.accepts("user")
                and not capability.accepts("model")
                and not capability.routable
                for capability in capabilities
            )
        )


if __name__ == "__main__":
    unittest.main()
