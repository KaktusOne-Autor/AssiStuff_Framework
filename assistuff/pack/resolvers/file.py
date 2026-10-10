"""Copy weights from a local file or directory."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)


class FileResolveError(RuntimeError):
    pass


def resolve_local_path(source: str, dest_dir: Path) -> list[Path]:
    src = Path(source).expanduser().resolve()
    if not src.exists():
        raise FileResolveError(f"source path does not exist: {src}")

    dest_dir.mkdir(parents=True, exist_ok=True)
    copied: list[Path] = []

    if src.is_file():
        dest = dest_dir / src.name
        shutil.copy2(src, dest)
        copied.append(dest)
    elif src.is_dir():
        for item in sorted(src.rglob("*")):
            if not item.is_file():
                continue
            rel = item.relative_to(src)
            dest = dest_dir / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, dest)
            copied.append(dest)
    else:
        raise FileResolveError(f"source is neither file nor directory: {src}")

    if not copied:
        raise FileResolveError(f"nothing copied from {src}")
    logger.info("copied %d files from %s", len(copied), src)
    return copied