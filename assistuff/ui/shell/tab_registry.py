"""Tab registry — pluggable tabs for the main window."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from PyQt6.QtWidgets import QWidget


@dataclass
class TabEntry:
    tab_id: str
    title: str
    factory: Callable[[QWidget], QWidget]
    order: int = 100
    icon: str | None = None


class TabRegistry:
    def __init__(self) -> None:
        self._tabs: dict[str, TabEntry] = {}

    def register(
        self,
        tab_id: str,
        title: str,
        factory: Callable[[QWidget], QWidget],
        *,
        order: int = 100,
        icon: str | None = None,
    ) -> None:
        if tab_id in self._tabs:
            raise ValueError(f"tab already registered: {tab_id}")
        if not callable(factory):
            raise TypeError("factory must be callable")
        self._tabs[tab_id] = TabEntry(tab_id, title, factory, order, icon)

    def ordered(self) -> list[TabEntry]:
        return sorted(self._tabs.values(), key=lambda e: (e.order, e.tab_id))

    def get(self, tab_id: str) -> TabEntry | None:
        return self._tabs.get(tab_id)