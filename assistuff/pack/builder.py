"""Build a .nrdpkg package from a source directory."""

from __future__ import annotations

import io
import logging
import os
import shutil
import stat
import tarfile
import tempfile
from pathlib import Path

import yaml

from .hashing import sha256_file
from .manifest import PackageManifest, WeightFile
from .resolvers import resolve_weights
from .signer import (
    public_key_fingerprint,
    sign_manifest_and_hashes,
    utc_now_iso,
)

logger = logging.getLogger(__name__)


class BuildError(RuntimeError):
    pass


def build_package(
    source_dir: Path,
    output_dir: Path,
    *,
    compress: str = "zstd",
    threads: int = 8,
    sign_key: Path | None = None,
    weights_spec: str | None = None,
) -> Path:
    """Build <id>-<version>.nrdpkg from a source directory."""
    source_dir = source_dir.resolve()
    manifest_path = source_dir / "manifest.yaml"
    if not manifest_path.is_file():
        raise BuildError(f"manifest.yaml not found in {source_dir}")

    manifest_data = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    manifest = PackageManifest.model_validate(manifest_data)

    output_dir.mkdir(parents=True, exist_ok=True)
    pkg_name = f"{manifest.package.id}-{manifest.package.version}.nrdpkg"
    pkg_path = output_dir / pkg_name

    with tempfile.TemporaryDirectory(prefix="assistuff-build-") as staging_str:
        staging = Path(staging_str)

        # 1. Copy source tree (excluding weights dir — resolved separately)
        _copy_source(source_dir, staging)

        # 2. Resolve weights
        weights_dir = staging / "weights"
        weights_dir.mkdir(parents=True, exist_ok=True)

        if weights_spec:
            resolved = resolve_weights(weights_spec, weights_dir)
        elif manifest.weights.bundled and (source_dir / "weights").is_dir():
            resolved = _copy_existing_weights(source_dir / "weights", weights_dir)
        else:
            resolved = []

        # 3. Compute hashes
        weight_files: list[WeightFile] = []
        total_size = 0
        for path in resolved:
            rel = path.relative_to(staging).as_posix()
            size = path.stat().st_size
            digest = sha256_file(path)
            weight_files.append(WeightFile(path=rel, sha256=digest, size_bytes=size))
            total_size += size

        manifest.weights.files = weight_files
        manifest.weights.size_bytes = total_size
        manifest.weights.bundled = bool(weight_files)

        # 4. Write integrity file
        integrity_dir = staging / "integrity"
        integrity_dir.mkdir(parents=True, exist_ok=True)
        weights_hashes_text = "\n".join(
            f"{wf.sha256}  {wf.path}" for wf in weight_files
        )
        (integrity_dir / "weights.sha256").write_text(weights_hashes_text, encoding="utf-8")

        # 5. Rewrite manifest with hashes
        manifest.integrity.signed_at = utc_now_iso()
        if sign_key is not None:
            manifest.integrity.signed_by = public_key_fingerprint(sign_key)
        manifest_bytes = yaml.safe_dump(
            manifest.model_dump(mode="json"),
            allow_unicode=True,
            sort_keys=False,
        ).encode("utf-8")
        (staging / "manifest.yaml").write_bytes(manifest_bytes)

        # 6. Sign (optional)
        if sign_key is not None:
            signature = sign_manifest_and_hashes(
                manifest_bytes,
                weights_hashes_text.encode("utf-8"),
                sign_key,
            )
            (staging / "signature.sig").write_bytes(signature)
            logger.info("signed package with key %s", sign_key)

        # 7. Compute package hash (manifest + weights hashes)
        from .hashing import sha256_bytes
        package_hash = sha256_bytes(manifest_bytes + weights_hashes_text.encode("utf-8"))
        (integrity_dir / "package.sha256").write_text(package_hash + "\n", encoding="utf-8")

        # 8. Archive
        _create_archive(staging, pkg_path, compress=compress)

    logger.info("built %s (%d bytes)", pkg_path, pkg_path.stat().st_size)
    return pkg_path


def sign_package(pkg_path: Path, private_key_path: Path) -> Path:
    """Re-sign a package in place, preserving its archive compression."""
    pkg_path = pkg_path.resolve()
    if not pkg_path.is_file():
        raise BuildError(f"package not found: {pkg_path}")
    if not private_key_path.is_file():
        raise BuildError(f"private key not found: {private_key_path}")

    original_mode = stat.S_IMODE(pkg_path.stat().st_mode)
    with tempfile.TemporaryDirectory(prefix="assistuff-sign-") as staging_str:
        staging = Path(staging_str)
        _extract_package(pkg_path, staging)
        manifest_path = staging / "manifest.yaml"
        if not manifest_path.is_file():
            raise BuildError("package has no manifest.yaml")
        try:
            manifest = PackageManifest.model_validate(
                yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
            )
        except Exception as exc:
            raise BuildError(f"invalid package manifest: {exc}") from exc

        from .installer import InstallError, _verify_weights

        try:
            _verify_weights(staging, manifest)
        except InstallError as exc:
            raise BuildError(f"cannot sign package with invalid weights: {exc}") from exc

        hashes_path = staging / "integrity" / "weights.sha256"
        if not hashes_path.is_file():
            raise BuildError("package has no integrity/weights.sha256")
        hashes_bytes = hashes_path.read_bytes()
        manifest.integrity.signed_at = utc_now_iso()
        manifest.integrity.signed_by = public_key_fingerprint(private_key_path)
        manifest_bytes = yaml.safe_dump(
            manifest.model_dump(mode="json"),
            allow_unicode=True,
            sort_keys=False,
        ).encode("utf-8")
        manifest_path.write_bytes(manifest_bytes)
        from .hashing import sha256_bytes

        (staging / "integrity" / "package.sha256").write_text(
            sha256_bytes(manifest_bytes + hashes_bytes) + "\n",
            encoding="utf-8",
        )
        (staging / "signature.sig").write_bytes(
            sign_manifest_and_hashes(
                manifest_bytes,
                hashes_bytes,
                private_key_path,
            )
        )

        with tempfile.NamedTemporaryFile(
            dir=pkg_path.parent,
            prefix=f".{pkg_path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            archive_path = Path(handle.name)
        try:
            compression = _package_compression(pkg_path)
            _create_archive(staging, archive_path, compress=compression)
            archive_path.chmod(original_mode)
            os.replace(archive_path, pkg_path)
        except Exception:
            archive_path.unlink(missing_ok=True)
            raise

    logger.info("signed package %s with %s", pkg_path, manifest.integrity.signed_by)
    return pkg_path


def _package_compression(pkg_path: Path) -> str:
    with pkg_path.open("rb") as handle:
        magic = handle.read(4)
    if magic == b"\x28\xb5\x2f\xfd":
        return "zstd"
    if magic.startswith(b"\x1f\x8b"):
        return "gz"
    return "none"


def _extract_package(pkg_path: Path, staging: Path) -> None:
    from .installer import InstallError, _safe_extract

    try:
        compression = _package_compression(pkg_path)
        if compression == "zstd":
            try:
                import zstandard as zstd
            except ImportError as exc:
                raise BuildError(
                    "zstandard is required to sign this package; "
                    "install with: pip install 'assistuff[pack]'"
                ) from exc
            with pkg_path.open("rb") as raw:
                with zstd.ZstdDecompressor().stream_reader(raw) as decompressed:
                    with tarfile.open(fileobj=decompressed, mode="r|") as archive:
                        _safe_extract(archive, staging)
        else:
            mode = "r:gz" if compression == "gz" else "r:"
            with tarfile.open(pkg_path, mode=mode) as archive:
                _safe_extract(archive, staging)
    except (BuildError, InstallError):
        raise
    except Exception as exc:
        raise BuildError(f"failed to extract package for signing: {exc}") from exc


def _copy_source(source_dir: Path, staging: Path) -> None:
    for item in source_dir.rglob("*"):
        if not item.is_file():
            continue
        rel = item.relative_to(source_dir)
        if rel.parts[0] in {"weights", ".git", "__pycache__", "dist"}:
            continue
        dest = staging / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(item, dest)


def _copy_existing_weights(src: Path, dest: Path) -> list[Path]:
    copied: list[Path] = []
    for item in sorted(src.rglob("*")):
        if not item.is_file():
            continue
        rel = item.relative_to(src)
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(item, target)
        copied.append(target)
    return copied


def _create_archive(staging: Path, pkg_path: Path, *, compress: str) -> None:
    if compress == "zstd":
        try:
            import zstandard as zstd
        except ImportError as exc:
            raise BuildError(
                "zstandard is required for --compress zstd; "
                "install with: pip install 'assistuff[pack]'"
            ) from exc

        cctx = zstd.ZstdCompressor(level=19)
        with pkg_path.open("wb") as raw_out:
            with cctx.stream_writer(raw_out) as zstd_out:
                with tarfile.open(fileobj=zstd_out, mode="w|") as tar:
                    _add_tree(tar, staging)
        return

    if compress == "none":
        with tarfile.open(pkg_path, mode="w") as tar:
            _add_tree(tar, staging)
        return

    if compress == "gz":
        with tarfile.open(pkg_path, mode="w:gz") as tar:
            _add_tree(tar, staging)
        return

    raise BuildError(f"unsupported compression: {compress!r}")


def _add_tree(tar: tarfile.TarFile, root: Path) -> None:
    for item in sorted(root.rglob("*")):
        rel = item.relative_to(root)
        arcname = rel.as_posix()
        if item.is_file():
            tar.add(item, arcname=arcname, recursive=False)
        elif item.is_dir():
            tar.add(item, arcname=arcname, recursive=False)