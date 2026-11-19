import asyncio
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from pydantic import ValidationError

from assistuff.config.schemas import (
    LongTermTagsConfig,
    MemoryConfig,
    ModelManifest,
)
from assistuff.bus.adapters.model_adapter import _build_memory_context
from assistuff.memory.long_term import LongTermMemory
from assistuff.memory.retrieval import MemoryRetriever
from assistuff.memory.store import MemoryStore
from assistuff.turn.memory_writer import MemoryWriter


class FakeUtilityRoles:
    def __init__(self) -> None:
        self.calls = 0

    async def generate_json(self, role, prompt, *, schema):
        self.calls += 1
        return {
            "identity": ["Prefers concise responses"],
            "preferences": [],
            "projects": [],
            "recent_topics": [],
            "patterns": [],
            "relationships": [],
            "notes": [],
        }


class MemoryFeatureTests(unittest.TestCase):
    def test_append_enforces_unique_tag_limit_and_dynamic_policy(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "memory.md"
            memory = LongTermMemory(
                path,
                tags_config=LongTermTagsConfig(max_per_note=2, min_per_note=1),
            )

            with self.assertRaisesRegex(ValueError, "at most 2 tags"):
                memory.append("Too many tags", ["#identity", "#projects", "#events"])

            hit = memory.append(
                "Duplicate tags are canonicalized",
                ["#identity", "#identity"],
            )
            self.assertEqual(hit.tags, ("#identity",))

            restricted = LongTermMemory(
                Path(temp_dir) / "restricted.md",
                tags_config=LongTermTagsConfig(dynamic=False),
            )
            with self.assertRaisesRegex(ValueError, "dynamic tags are disabled"):
                restricted.append("Unknown category", ["#unlisted"])

    def test_audit_tags_reports_usage_and_unknown_tags(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            memory_path = Path(temp_dir) / "memory.md"
            memory = LongTermMemory(memory_path)
            memory.append("Known taxonomy item", ["#identity"])
            with memory_path.open("a", encoding="utf-8") as handle:
                handle.write("- [2026-01-01T00:00:00+00:00] #orphan Old tag\n")

            counts, unknown = memory.audit_tags()

            self.assertEqual(counts["#identity"], 1)
            self.assertEqual(counts["#orphan"], 1)
            self.assertEqual(unknown, ["#orphan"])

    def test_turn_memory_writer_awaits_configured_dossier_compiler(self) -> None:
        async def run() -> None:
            with tempfile.TemporaryDirectory() as temp_dir:
                config = MemoryConfig(
                    dossier={"compile_every": 1, "enabled": True}
                )
                store = MemoryStore("default", Path(temp_dir), config)
                roles = FakeUtilityRoles()
                compiler = store.make_compiler(roles)
                writer = MemoryWriter(store, compile_hook=compiler.maybe_compile)

                await writer.record(
                    user_text="I am working on a project",
                    assistant_text="I can help with that.",
                    summary="The user is working on a project.",
                )

                self.assertEqual(roles.calls, 1)
                dossier = store.load_dossier()
                self.assertEqual(dossier.identity, ["Prefers concise responses"])
                self.assertEqual(store.short_term.recent_messages(limit=2), [
                    ("user", "I am working on a project"),
                    ("assistant", "I can help with that."),
                ])

        asyncio.run(run())

    def test_dossier_compile_interval_survives_restart(self) -> None:
        async def run() -> None:
            with tempfile.TemporaryDirectory() as temp_dir:
                store = MemoryStore(
                    "default",
                    Path(temp_dir),
                    MemoryConfig(dossier={"compile_every": 2}),
                )
                store.short_term.add_message("user", "Previous question")
                store.short_term.add_message("assistant", "Previous answer")
                roles = FakeUtilityRoles()
                compiler = store.make_compiler(roles)
                writer = MemoryWriter(store, compile_hook=compiler.maybe_compile)

                await writer.record(
                    user_text="Second question",
                    assistant_text="Second answer",
                )

                self.assertEqual(roles.calls, 1)

        asyncio.run(run())

    def test_tag_minimum_cannot_exceed_maximum(self) -> None:
        with self.assertRaisesRegex(ValidationError, "min_per_note cannot exceed"):
            LongTermTagsConfig(min_per_note=3, max_per_note=2)

    def test_model_memory_context_obeys_manifest_read_permissions(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config = MemoryConfig()
            store = MemoryStore("default", Path(temp_dir), config)
            store.short_term.add_message("user", "I am building AssiStuff.")
            store.long_term.append(
                "AssiStuff uses a capability bus.",
                ["#projects"],
            )
            dossier = store.load_dossier()
            dossier.identity = ["The user prefers concise answers."]
            store.dossier_storage.save(dossier)

            denied = ModelManifest.model_validate({
                "id": "test-model",
                "version": "1.0.0",
                "runtime": {"tag": "test:latest"},
                "memory": {"reads": [], "dossier_access": "none"},
            })
            self.assertEqual(
                _build_memory_context(denied, store, "AssiStuff", None),
                "",
            )

            short_term_only = ModelManifest.model_validate({
                "id": "test-model",
                "version": "1.0.0",
                "runtime": {"tag": "test:latest"},
                "memory": {"reads": ["short_term"], "dossier_access": "none"},
            })
            context = _build_memory_context(
                short_term_only,
                store,
                "AssiStuff",
                SimpleNamespace(entries={"draft": "working value"}),
            )
            self.assertIn("Recent conversation", context)
            self.assertNotIn("Relevant long-term notes", context)
            self.assertNotIn("Dossier", context)
            self.assertNotIn("working value", context)

            authorized = ModelManifest.model_validate({
                "id": "test-model",
                "version": "1.0.0",
                "runtime": {"tag": "test:latest"},
                "memory": {
                    "reads": ["working", "short_term", "long_term"],
                    "dossier_access": "read",
                },
            })
            context = _build_memory_context(
                authorized,
                store,
                "AssiStuff",
                SimpleNamespace(entries={"draft": "working value"}),
            )
            self.assertIn("working value", context)
            self.assertIn("Relevant long-term notes", context)
            self.assertIn("Dossier", context)

    def test_fuzzy_tag_matching_resolves_close_vocabulary_entry(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            memory = LongTermMemory(Path(temp_dir) / "memory.md")
            memory.append("Project plan", ["#projects"])

            hits = MemoryRetriever(memory).search("#project")

            self.assertEqual([hit.text for hit in hits], ["Project plan"])

    def test_async_unknown_tag_retry_uses_planner_then_searches(self) -> None:
        async def run() -> None:
            with tempfile.TemporaryDirectory() as temp_dir:
                memory = LongTermMemory(Path(temp_dir) / "memory.md")
                memory.append("Meeting notes", ["#events"])
                calls = []

                async def retry(unknown, known):
                    calls.append((unknown, known))
                    return ["#events"]

                hits = await MemoryRetriever(memory).search_with_retry_async(
                    "#unlisted",
                    retry_callback=retry,
                    max_retries=1,
                )

                self.assertEqual([hit.text for hit in hits], ["Meeting notes"])
                self.assertEqual(len(calls), 1)

        asyncio.run(run())

    def test_unresolved_tag_falls_back_to_unfiltered_search(self) -> None:
        async def run() -> None:
            with tempfile.TemporaryDirectory() as temp_dir:
                memory = LongTermMemory(Path(temp_dir) / "memory.md")
                memory.append("A saved note", ["#identity"])

                async def retry(_unknown, _known):
                    return ["#still-unknown"]

                hits = await MemoryRetriever(memory).search_with_retry_async(
                    "#unknown",
                    retry_callback=retry,
                    max_retries=1,
                )

                self.assertEqual([hit.text for hit in hits], ["A saved note"])

        asyncio.run(run())

    def test_memory_cli_parses_append_tags_and_forced_reindex(self) -> None:
        from assistuff.__main__ import build_parser

        parser = build_parser()
        append = parser.parse_args([
            "--memory", "append", "A", "note", "--tags", "#projects,#events",
        ])
        self.assertEqual(append.memory, ["append", "A", "note"])
        self.assertEqual(append.tags, "#projects,#events")

        reindex = parser.parse_args(["--memory", "reindex", "--force"])
        self.assertEqual(reindex.memory, ["reindex"])
        self.assertTrue(reindex.force)

    def test_reindex_skips_fresh_index_unless_forced(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            memory = LongTermMemory(Path(temp_dir) / "memory.md")
            memory.append("Indexed note", ["#identity"])
            with (
                patch.object(memory, "_index_is_stale", return_value=False),
                patch.object(memory, "_parse_notes", wraps=memory._parse_notes) as parse,
            ):
                self.assertEqual(memory.reindex(), 1)
                parse.assert_not_called()
                self.assertEqual(memory.reindex(force=True), 1)
                parse.assert_called_once()
