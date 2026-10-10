"""Install .nrdpkg packages."""

from __future__ import annotations

import json
import logging
import shutil
import tarfile
import tempfile
from pathlib import Path

import yaml

from .hashing import sha256_file
from .manifest import PackageManifest
from .paths import (
    installed_model_dir,
    modelfiles_dir,
    registry_json_path,
)

logger = logging.getLogger(__name__)


class InstallError(RuntimeError):
    pass


def install_package(
    pkg_path: Path,
    *,
    allow_unsigned: bool = False,
    verify_signature: bool = True,
    public_key_path: Path | None = None,
    ollama_host: str = "http://localhost:11434",
) -> dict:
    pkg_path = pkg_path.resolve()
    if not pkg_path.is_file():
        raise InstallError(f"package not found: {pkg_path}")

    with tempfile.TemporaryDirectory(prefix="assistuff-install-") as staging_str:
        staging = Path(staging_str)
        manifest = _extract_and_validate(pkg_path, staging)

        if verify_signature and not allow_unsigned:
            _verify_or_raise(staging, public_key_path)

        _verify_weights(staging, manifest)

        dest = installed_model_dir(manifest.package.id, manifest.package.version)
        if dest.exists():
            logger.warning("overwriting existing installation at %s", dest)
            shutil.rmtree(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)

        # Move staged files into final location
        for item in staging.iterdir():
            shutil.move(str(item), str(dest / item.name))

        # Register in registry.json
        entry = _register(dest, manifest)

        # Create Ollama model if backend is ollama
        if manifest.runtime.backend == "ollama":
            try:
                _ollama_create(dest, manifest, host=ollama_host)
                entry["ollama_tag"] = f"assistuff/{manifest.package.id}:{manifest.package.version}"
            except Exception as exc:
                logger.warning("ollama create failed: %s", exc)
                entry["ollama_tag"] = None

        _update_registry(entry)
        logger.info("installed %s@%s", manifest.package.id, manifest.package.version)
        return entry


def _extract_and_validate(pkg_path: Path, staging: Path) -> PackageManifest:
    try:
        _stream_extract(pkg_path, staging)
    except Exception as exc:
        raise InstallError(f"failed to extract {pkg_path}: {exc}") from exc

    manifest_path = staging / "manifest.yaml"
    if not manifest_path.is_file():
        raise InstallError("package has no manifest.yaml")

    data = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    try:
        manifest = PackageManifest.model_validate(data)
    except Exception as exc:
        raise InstallError(f"invalid manifest: {exc}") from exc

    if manifest.provenance.redistribution == "forbidden":
        raise InstallError(
            f"package {manifest.package.id} forbids redistribution"
        )
    return manifest


def _stream_extract(pkg_path: Path, dest: Path) -> None:
    """Stream-extract a tar+zstd package without loading it all into RAM."""
    try:
        import zstandard as zstd
        dctx = zstd.ZstdDecompressor()
        with pkg_path.open("rb") as raw:
            with dctx.stream_reader(raw) as decompressed:
                with tarfile.open(fileobj=decompressed, mode="r|") as tar:
                    _safe_extract(tar, dest)
        return
    except ImportError:
        pass

    # Fallback: try plain tar (no zstd)
    try:
        with tarfile.open(pkg_path, mode="r:*") as tar:
            _safe_extract(tar, dest)
    except tarfile.TarError as exc:
        raise InstallError(f"unsupported package format: {exc}") from exc


def _safe_extract(tar: tarfile.TarFile, dest: Path) -> None:
    dest = dest.resolve()
    for member in tar:
        target = (dest / member.name).resolve()
        if not str(target).startswith(str(dest)):
            raise InstallError(f"unsafe path in package: {member.name}")
        tar.extract(member, path=dest)


def _verify_weights(staging: Path, manifest: PackageManifest) -> None:
    for wf in manifest.weights.files:
        path = staging / wf.path
        if not path.is_file():
            raise InstallError(f"missing weight file: {wf.path}")
        actual = sha256_file(path)
        if actual != wf.sha256:
            raise InstallError(
                f"weight hash mismatch for {wf.path}: "
                f"expected {wf.sha256}, got {actual}"
            )


def _verify_or_raise(staging: Path, public_key_path: Path | None) -> None:
    sig_path = staging / "signature.sig"
    if not sig_path.is_file():
        raise InstallError(
            "package is unsigned; use --allow-unsigned to install anyway"
        )
    if public_key_path is None or not public_key_path.is_file():
        raise InstallError(
            "signature present but no public key provided; "
            "use --public-key <path> or --allow-unsigned"
        )
    from .signer import verify_signature
    manifest_bytes = (staging / "manifest.yaml").read_bytes()
    weights_hashes = (staging / "integrity" / "weights.sha256").read_bytes()
    payload = manifest_bytes + b"\n---\n" + weights_hashes
    if not verify_signature(payload, sig_path.read_bytes(), public_key_path):
        raise InstallError("signature verification failed")


def _register(dest: Path, manifest: PackageManifest) -> dict:
    return {
        "package_id": manifest.package.id,
        "version": manifest.package.version,
        "path": str(dest),
        "capabilities": list(manifest.capabilities.provides),
        "weights_sha256": (dest / "integrity" / "package.sha256").read_text().strip()
        if (dest / "integrity" / "package.sha256").is_file() else None,
        "bundled": manifest.weights.bundled,
        "size_bytes": manifest.weights.size_bytes,
    }


def _ollama_create(dest: Path, manifest: PackageManifest, *, host: str) -> None:
    """Generate a Modelfile and call ollama create."""
    import httpx

    weights_dir = dest / "weights"
    if not weights_dir.is_dir():
        raise InstallError("no weights directory in package")

    # Find the primary GGUF
    ggufs = list(weights_dir.glob("*.gguf"))
    if not ggufs:
        raise InstallError("no .gguf file found in weights/")
    primary = ggufs[0]

    # Build Modelfile
    lines = [
        f"FROM {primary}",
        f"PARAMETER temperature {manifest.runtime.temperature}",
        f"PARAMETER num_ctx {manifest.runtime.context_window}",
    ]
    system_prompt_path = dest / "prompts" / "system.md"
    if system_prompt_path.is_file():
        system_text = system_prompt_path.read_text(encoding="utf-8").strip()
        if system_text:
            lines.append(f'SYSTEM """{system_text}"""')

    modelfile_text = "\n".join(lines)

    modelfiles_dir().mkdir(parents=True, exist_ok=True)
    modelfile_path = modelfiles_dir() / f"{manifest.package.id}@{manifest.package.version}.Modelfile"
    modelfile_path.write_text(modelfile_text, encoding="utf-8")

    tag = f"assistuff/{manifest.package.id}:{manifest.package.version}"
    response = httpx.post(
        f"{host}/api/create",
        json={"name": tag, "modelfile": modelfile_text, "stream": False},
        timeout=600.0,
    )
    response.raise_for_status()
    logger.info("ollama created %s", tag)


def _update_registry(entry: dict) -> None:
    registry_path = registry_json_path()
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    if registry_path.is_file():
        try:
            registry = json.loads(registry_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            registry = {}
    else:
        registry = {}

    pkg_id = entry["package_id"]
    version = entry["version"]
    registry.setdefault(pkg_id, {"versions": {}, "active": version})
    registry[pkg_id]["versions"][version] = entry
    registry[pkg_id]["active"] = version

    registry_path.write_text(
        json.dumps(registry, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def list_installed() -> dict:
    registry_path = registry_json_path()
    if not registry_path.is_file():
        return {}
    try:
        return json.loads(registry_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def uninstall_package(package_id: str, version: str | None = None) -> None:
    registry = list_installed()
    if package_id not in registry:
        raise InstallError(f"package not installed: {package_id}")
    entry = registry[package_id]
    target_version = version or entry.get("active")
    if not target_version or target_version not in entry["versions"]:
        raise InstallError(f"version not installed: {package_id}@{target_version}")

    dest = Path(entry["versions"][target_version]["path"])
    if dest.exists():
        shutil.rmtree(dest)

    del entry["versions"][target_version]
    if not entry["versions"]:
        del registry[package_id]
    else:
        entry["active"] = next(iter(entry["versions"]))

    registry_json_path().write_text(
        json.dumps(registry, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    logger.info("uninstalled %s@%s", package_id, target_version)