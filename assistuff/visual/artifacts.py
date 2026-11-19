"""Store generated HTML artifacts and apply a restrictive viewer policy."""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

_ARTIFACT_ID = re.compile(r"^[0-9a-f]{32}$")
_MAX_ARTIFACT_BYTES = 1_000_000
_CSP_META = (
    '<meta http-equiv="Content-Security-Policy" content="'
    "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; "
    "img-src data: blob:; media-src data: blob:; font-src data:; "
    "connect-src 'none'; object-src 'none'; frame-src 'none'; "
    "worker-src 'none'; form-action 'none'; base-uri 'none'\">"
)


@dataclass(frozen=True)
class Artifact:
    artifact_id: str
    title: str
    created_at: str


class ArtifactStore:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).expanduser()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)

    def create(self, title: str, document: str) -> Artifact:
        _validate_document(document)
        artifact_id = uuid.uuid4().hex
        clean_title = " ".join(title.split())[:120] or "Visual artifact"
        created_at = datetime.now(UTC).isoformat()
        html_path = self.root / f"{artifact_id}.html"
        meta_path = self.root / f"{artifact_id}.json"
        _write_private(html_path, document.encode("utf-8"))
        metadata = json.dumps(
            {
                "artifact_id": artifact_id,
                "title": clean_title,
                "created_at": created_at,
            },
            ensure_ascii=False,
        ).encode("utf-8")
        try:
            _write_private(meta_path, metadata)
        except OSError:
            html_path.unlink(missing_ok=True)
            raise
        return Artifact(artifact_id, clean_title, created_at)

    def list(self) -> list[Artifact]:
        artifacts: list[Artifact] = []
        for path in self.root.glob("*.json"):
            artifact_id = path.stem
            _validate_id(artifact_id)
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                artifact = Artifact(
                    artifact_id=artifact_id,
                    title=str(data["title"]),
                    created_at=str(data["created_at"]),
                )
            except (OSError, ValueError, KeyError, TypeError) as exc:
                raise ValueError(f"invalid artifact metadata at {path}") from exc
            if not (self.root / f"{artifact_id}.html").is_file():
                raise FileNotFoundError(f"artifact document is missing: {artifact_id}")
            artifacts.append(artifact)
        return sorted(artifacts, key=lambda item: item.created_at, reverse=True)

    def read(self, artifact_id: str) -> str:
        _validate_id(artifact_id)
        path = self.root / f"{artifact_id}.html"
        if path.resolve().parent != self.root.resolve() or not path.is_file():
            raise FileNotFoundError(f"unknown visual artifact: {artifact_id}")
        document = path.read_text(encoding="utf-8")
        _validate_document(document)
        return document


def build_view_document(document: str) -> str:
    """Insert host-enforced CSP before displaying an untrusted artifact."""
    _validate_document(document)
    head_match = re.search(r"<head\b[^>]*>", document, re.I)
    if head_match:
        return document[:head_match.end()] + _CSP_META + document[head_match.end():]
    html_match = re.search(r"<html\b[^>]*>", document, re.I)
    if not html_match:
        raise ValueError("visual artifact must contain an html root element")
    head = f"<head><meta charset=\"utf-8\">{_CSP_META}</head>"
    return document[:html_match.end()] + head + document[html_match.end():]


def _validate_document(document: str) -> None:
    if not isinstance(document, str):
        raise TypeError("visual artifact must be HTML text")
    encoded = document.encode("utf-8")
    if len(encoded) > _MAX_ARTIFACT_BYTES:
        raise ValueError(f"visual artifact exceeds {_MAX_ARTIFACT_BYTES} bytes")
    if not re.search(r"<html\b", document, re.I) or not re.search(
        r"</html\s*>", document, re.I
    ):
        raise ValueError("visual artifact must contain a complete html document")


def _validate_id(artifact_id: str) -> None:
    if not _ARTIFACT_ID.fullmatch(artifact_id):
        raise ValueError("invalid visual artifact ID")


def _write_private(path: Path, data: bytes) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("xb") as handle:
        handle.write(data)
    temporary.chmod(0o600)
    temporary.replace(path)
