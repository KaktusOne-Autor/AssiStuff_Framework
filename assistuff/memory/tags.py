"""Tag registry — controlled vocabulary stored in memory.md header."""

from __future__ import annotations

import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

_TAG_BLOCK_RE = re.compile(
    r"<!--\s*tags\s*\n(.*?)\n\s*-->",
    re.DOTALL | re.IGNORECASE,
)
_TAG_LINE_RE = re.compile(
    r"^\s*([^:]+?)\s*:\s*(.+?)\s*$",
)
_TAG_TOKEN_RE = re.compile(r"[#]?[A-Za-zА-Яа-яЁё0-9_/-]+")


class TagRegistry:
    """Loads the tag list from memory.md header and normalizes lookups."""

    def __init__(self, memory_md_path: Path) -> None:
        self.memory_md_path = Path(memory_md_path)
        self._canonical: dict[str, str] = {}
        self._order: list[str] = []

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def load(self) -> None:
        self._canonical.clear()
        self._order.clear()
        if not self.memory_md_path.is_file():
            return
        text = self.memory_md_path.read_text(encoding="utf-8")
        match = _TAG_BLOCK_RE.search(text)
        if not match:
            return
        for raw_line in match.group(1).splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            m = _TAG_LINE_RE.match(line)
            if not m:
                continue
            left, _desc = m.group(1), m.group(2)
            for token in left.split("/"):
                tag = self._normalize(token)
                if not tag:
                    continue
                if tag not in self._canonical:
                    self._order.append(tag)
                self._canonical[tag] = tag

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def all(self) -> list[str]:
        return list(self._order)

    def is_known(self, tag: str) -> bool:
        return self.canonical(tag) in self._canonical.values()

    def canonical(self, tag: str) -> str:
        normalized = self._normalize(tag)
        return self._canonical.get(normalized, normalized)

    def canonicalize_many(self, tags: list[str]) -> list[str]:
        seen: list[str] = []
        for tag in tags:
            c = self.canonical(tag)
            if c and c not in seen:
                seen.append(c)
        return seen

    # ------------------------------------------------------------------
    # Mutation
    # ------------------------------------------------------------------

    def add(self, tag: str, *, position: str = "top") -> str:
        normalized = self._normalize(tag)
        if not normalized:
            raise ValueError(f"cannot add empty tag: {tag!r}")
        if normalized in self._canonical:
            return self._canonical[normalized]

        self._canonical[normalized] = normalized
        if position == "top":
            self._order.insert(0, normalized)
        else:
            self._order.append(normalized)

        self._rewrite_header()
        return normalized

    def _rewrite_header(self) -> None:
        if not self.memory_md_path.is_file():
            logger.warning("memory.md not found, cannot rewrite header")
            return
        text = self.memory_md_path.read_text(encoding="utf-8")
        match = _TAG_BLOCK_RE.search(text)
        if not match:
            logger.warning("tags block not found in memory.md")
            return

        descriptions: dict[str, str] = {}
        for raw_line in match.group(1).splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            m = _TAG_LINE_RE.match(line)
            if not m:
                continue
            desc = m.group(2)
            for token in m.group(1).split("/"):
                tag = self._normalize(token)
                if tag:
                    descriptions.setdefault(tag, desc)

        lines: list[str] = []
        for tag in self._order:
            desc = descriptions.get(tag, "")
            lines.append(f"{tag}: {desc}" if desc else tag)
        new_block = "<!-- tags\n" + "\n".join(lines) + "\n-->"
        new_text = text[: match.start()] + new_block + text[match.end() :]
        self.memory_md_path.write_text(new_text, encoding="utf-8")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize(tag: str) -> str:
        raw = tag.strip()
        if not raw:
            return ""
        tokens = _TAG_TOKEN_RE.findall(raw)
        if not tokens:
            return ""
        token = tokens[0].lstrip("#").strip().lower()
        if not token:
            return ""
        return f"#{token}"