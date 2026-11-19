from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from assistuff.visual.artifacts import ArtifactStore, build_view_document


class VisualArtifactTests(unittest.TestCase):
    def test_artifact_round_trip_and_host_csp(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ArtifactStore(Path(temp_dir) / "artifacts")
            source = (
                "<!doctype html><html><head><title>demo</title></head>"
                "<body><script>document.body.dataset.ready='yes';</script></body></html>"
            )
            artifact = store.create("  Demo   infographic ", source)

            self.assertEqual(artifact.title, "Demo infographic")
            self.assertEqual(store.read(artifact.artifact_id), source)
            self.assertIn("connect-src 'none'", build_view_document(source))
            self.assertIn("script-src 'unsafe-inline'", build_view_document(source))
            self.assertEqual(store.list(), [artifact])

    def test_artifact_store_rejects_bad_documents_and_ids(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ArtifactStore(Path(temp_dir) / "artifacts")
            with self.assertRaisesRegex(ValueError, "complete html"):
                store.create("invalid", "<html>missing close")
            with self.assertRaisesRegex(ValueError, "ID"):
                store.read("../outside")


if __name__ == "__main__":
    unittest.main()
