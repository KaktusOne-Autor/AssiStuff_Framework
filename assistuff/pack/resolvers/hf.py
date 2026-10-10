"""Pull weights from Hugging Face."""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class HfResolveError(RuntimeError):
    pass


def resolve_hf_snapshot(
    repo_id: str,
    dest_dir: Path,
    *,
    allow_patterns: list[str] | None = None,
    revision: str | None = None,
) -> list[Path]:
    try:
        from huggingface_hub import snapshot_download
    except ImportError as exc:
        raise HfResolveError(
            "huggingface_hub is required for HF resolver; "
            "install with: pip install 'assistuff[pack]'"
        ) from exc

    dest_dir.mkdir(parents=True, exist_ok=True)
    try:
        local = snapshot_download(
            repo_id=repo_id,
            revision=revision,
            allow_patterns=allow_patterns,
            local_dir=str(dest_dir),
            local_dir_use_symlinks=False,
        )
    except Exception as exc:
        raise HfResolveError(f"failed to fetch {repo_id}: {exc}") from exc

    files = sorted(Path(local).rglob("*"))
    paths = [f for f in files if f.is_file()]
    logger.info("fetched %d files from HF repo %s", len(paths), repo_id)
    return paths