"""Skill: DuckDuckGo HTML search."""

from __future__ import annotations

import logging
import re
from html.parser import HTMLParser
from urllib.parse import parse_qs, urlparse

import httpx

from assistuff.skills.registry import SkillContext

logger = logging.getLogger(__name__)

_STRIP_PREFIX_RE = re.compile(
    r"^\s*(?:search(?:\s+(?:the\s+)?(?:web|internet|online))?\s+for|"
    r"browse(?:\s+(?:the\s+)?(?:web|internet|online))?\s+for|"
    r"find\s+online|найди\s+в\s+интернете|найти\s+в\s+интернете|"
    r"поищи\s+в\s+интернете|поищи\s+в\s+сети|найди\s+в\s+сети|"
    r"поиск\s+в\s+интернете|поищи\s+онлайн|найди\s+онлайн|загугли)\s*[:,-]?\s*",
    re.IGNORECASE,
)


class _ResultsParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.results: list[dict[str, str]] = []
        self._active_field: str | None = None
        self._active_result: dict[str, str] | None = None

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        classes = set((attributes.get("class") or "").split())
        if tag == "a" and "result__a" in classes:
            self._active_result = {
                "title": "",
                "url": attributes.get("href") or "",
                "snippet": "",
            }
            self._active_field = "title"
        elif "result__snippet" in classes and self.results:
            self._active_result = self.results[-1]
            self._active_field = "snippet"

    def handle_endtag(self, tag):
        if tag in {"a", "div", "td"}:
            if self._active_result is not None and self._active_result not in self.results:
                if self._active_result["title"].strip():
                    self.results.append(self._active_result)
            self._active_result = None
            self._active_field = None

    def handle_data(self, data):
        if self._active_result is not None and self._active_field:
            self._active_result[self._active_field] += data


def _normalize_url(value: str) -> str:
    candidate = value.strip()
    parsed = urlparse(candidate)
    hostname = parsed.hostname or ""
    if hostname == "duckduckgo.com" or hostname.endswith(".duckduckgo.com"):
        target = parse_qs(parsed.query).get("uddg", [])
        if target:
            candidate = target[0]
            parsed = urlparse(candidate)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return ""
    return candidate


def run(value: str, _ctx: SkillContext) -> str:
    query = _STRIP_PREFIX_RE.sub("", value).strip()
    if not query:
        raise ValueError("provide a query for web search")
    if len(query) > 500:
        raise ValueError("web search query must not exceed 500 characters")

    try:
        response = httpx.get(
            "https://html.duckduckgo.com/html/",
            params={"q": query},
            headers={"User-Agent": "AssiStuff/4.1 (local search)"},
            timeout=(5.0, 15.0),
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        logger.exception("web search failed")
        raise RuntimeError(f"web search failed: {exc}") from exc

    parser = _ResultsParser()
    parser.feed(response.text)

    formatted: list[str] = []
    for item in parser.results:
        title = " ".join(item["title"].split())
        snippet = " ".join(item["snippet"].split())
        url = _normalize_url(item["url"])
        if not title or not url:
            continue
        formatted.append(
            f"{len(formatted) + 1}. {title}\n"
            f"   {snippet[:600]}\n"
            f"   Source: {url}"
        )
        if len(formatted) == 5:
            break

    if not formatted:
        return f"No web results found for: {query}"
    return f'Web search results for "{query}":\n' + "\n".join(formatted)