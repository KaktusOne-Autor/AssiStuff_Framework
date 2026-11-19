import io
import hashlib
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

from assistuff.pack.builder import BuildError, build_package, sign_package


class PackageSigningTests(unittest.TestCase):
    def _build_package(self, root: Path) -> tuple[Path, Path]:
        source = root / "source"
        source.mkdir()
        (source / "manifest.yaml").write_text(
            yaml.safe_dump(
                {
                    "package": {
                        "id": "sample",
                        "name": "Sample",
                        "version": "1.0.0",
                    },
                    "weights": {"bundled": True},
                    "provenance": {"redistribution": "allowed"},
                },
                sort_keys=False,
            ),
            encoding="utf-8",
        )
        weights = source / "weights"
        weights.mkdir()
        weight_path = weights / "model.gguf"
        weight_path.write_bytes(b"sample model weights")
        output = root / "dist"
        package = build_package(source, output, compress="none")
        private_key = root / "test.key"
        private_key.write_bytes(b"test key")
        return package, private_key

    def test_signing_updates_signature_metadata_and_integrity(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            package, private_key = self._build_package(Path(temp_dir))
            with (
                patch(
                    "assistuff.pack.builder.public_key_fingerprint",
                    return_value="sha256:test-fingerprint",
                ),
                patch(
                    "assistuff.pack.builder.sign_manifest_and_hashes",
                    return_value=b"test-signature",
                ),
            ):
                result = sign_package(package, private_key)

            self.assertEqual(result, package.resolve())
            with tarfile.open(package, mode="r:") as archive:
                manifest = yaml.safe_load(
                    archive.extractfile("manifest.yaml").read()
                )
                hashes = archive.extractfile("integrity/weights.sha256").read()
                package_hash = archive.extractfile("integrity/package.sha256").read()
                signature = archive.extractfile("signature.sig").read()
            self.assertEqual(manifest["integrity"]["signed_by"], "sha256:test-fingerprint")
            self.assertTrue(manifest["integrity"]["signed_at"])
            self.assertEqual(
                package_hash.decode().strip(),
                hashlib.sha256(
                    archive_manifest_bytes(package, "manifest.yaml") + hashes
                ).hexdigest(),
            )
            self.assertEqual(signature, b"test-signature")

    def test_invalid_weight_hash_leaves_original_package_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            package, private_key = self._build_package(Path(temp_dir))
            with tarfile.open(package, mode="r:") as archive:
                members = {
                    item.name: archive.extractfile(item).read()
                    for item in archive.getmembers()
                    if item.isfile()
                }
            members["weights/model.gguf"] = b"corrupted weights"
            replacement = package.with_suffix(".corrupt")
            with tarfile.open(replacement, mode="w") as archive:
                for name, content in members.items():
                    info = tarfile.TarInfo(name)
                    info.size = len(content)
                    archive.addfile(info, io.BytesIO(content))
            original_bytes = replacement.read_bytes()
            with self.assertRaisesRegex(BuildError, "invalid weights"):
                sign_package(replacement, private_key)
            self.assertEqual(replacement.read_bytes(), original_bytes)


def archive_manifest_bytes(package: Path, member: str) -> bytes:
    with tarfile.open(package, mode="r:") as archive:
        return archive.extractfile(member).read()


if __name__ == "__main__":
    unittest.main()
