"""Pull weights from a local Ollama blob."""

from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)


class OllamaResolveError(RuntimeError):
    pass


def resolve_ollama_blob(
    tag: str,
    dest_dir: Path,
    *,
    host: str = "http://localhost:11434",
) -> list[Path]:
    """Copy Ollama model blobs into dest_dir.

    Uses Ollama's HTTP API to find the model manifest, then locates
    the blobs in the local Ollama data directory.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)

    try:
        response = httpx.get(f"{host}/api/tags", timeout=10.0)
        response.raise_for_status()
        tags = response.json()
    except httpx.HTTPError as exc:
        raise OllamaResolveError(f"cannot reach Ollama at {host}: {exc}") from exc

    models = {m.get("name", ""): m for m in tags.get("models", [])}
    if tag not in models:
        raise OllamaResolveError(f"model {tag!r} not found in Ollama")

    # Ollama stores blobs under ~/.ollama/models/blobs
    ollama_root = Path.home() / ".ollama" / "models"
    if not ollama_root.is_dir():
        raise OllamaResolveError(
            "cannot find ~/.ollama/models; is Ollama installed for this user?"
        )

    # We don't try to parse the manifest format; instead, we ask Ollama
    # to show the Modelfile, which references the blobs.
    try:
        modelfile_resp = httpx.post(
            f"{host}/api/show",
            json={"name": tag},
            timeout=10.0,
        )
        modelfile_resp.raise_for_status()
        show = modelfile_resp.json()
    except httpx.HTTPError as exc:
        raise OllamaResolveError(f"cannot query Ollama for {tag!r}: {exc}") from exc

    # Ollama returns details.modelfile; we copy every blob referenced by
    # the FROM line. Fallback: copy all blobs (may be large).
    copied: list[Path] = []
    blob_dir = ollama_root / "blobs"
    if not blob_dir.is_dir():
        raise OllamaResolveError(f"no blobs directory at {blob_dir}")

    # Copy blobs that appear in the manifest for this tag
    manifest_paths = list((ollama_root / "manifests").rglob(tag.replace(":", "/")))
    if manifest_paths:
        manifest_path = manifest_paths[0]
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise OllamaResolveError(f"cannot parse manifest {manifest_path}: {exc}") from exc
        for layer in data.get("layers", []):
            digest = layer.get("digest", "")
            if not digest.startswith("sha256:"):
                continue
            blob_name = digest.split(":", 1)[1]
            blob_path = blob_dir / f"sha256-{blob_name}"
            if not blob_path.is_file():
                continue
            dest = dest_dir / blob_path.name
            shutil.copy2(blob_path, dest)
            copied.append(dest)
    else:
        # Fallback: copy all blobs (warning: может быть много)
        logger.warning(
            "no manifest found for %s, copying all blobs from %s", tag, blob_dir
        )
        for blob in blob_dir.glob("sha256-*"):
            dest = dest_dir / blob.name
            shutil.copy2(blob, dest)
            copied.append(dest)

    if not copied:
        raise OllamaResolveError(f"no blobs copied for {tag!r}")
    logger.info("copied %d blobs from Ollama for %s", len(copied), tag)
    return copied