"""Weight resolvers."""

from __future__ import annotations

import logging
from pathlib import Path

from .file import FileResolveError, resolve_local_path
from .hf import HfResolveError, resolve_hf_snapshot
from .ollama import OllamaResolveError, resolve_ollama_blob

logger = logging.getLogger(__name__)


class ResolveError(RuntimeError):
    pass


def resolve_weights(spec: str, dest_dir: Path) -> list[Path]:
    """Resolve a weight source spec into local files.

    Spec formats:
      - ``ollama:<tag>``            — pull from local Ollama
      - ``hf:<repo_id>``            — pull from Hugging Face
      - ``file:<path>``             — copy from local path
      - ``<path>``                  — treated as file:
    """
    if ":" in spec:
        scheme, _, value = spec.partition(":")
        scheme = scheme.lower()
    else:
        scheme, value = "file", spec

    if scheme == "ollama":
        return resolve_ollama_blob(value, dest_dir)
    if scheme == "hf":
        return resolve_hf_snapshot(value, dest_dir)
    if scheme == "file":
        return resolve_local_path(value, dest_dir)
    raise ResolveError(f"unsupported weight source scheme: {scheme!r}")