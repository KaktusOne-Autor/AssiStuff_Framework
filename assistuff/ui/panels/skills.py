"""Skills panel."""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QLabel,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..shell.context import UiContext


class SkillsPanel(QWidget):
    def __init__(self, ctx: UiContext, parent=None) -> None:
        super().__init__(parent)
        self.ctx = ctx

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Registered skills"))

        self.list = QListWidget()
        layout.addWidget(self.list)

        self.reload()

    def reload(self) -> None:
        self.list.clear()
        if self.ctx.dispatcher is None:
            return
        for unit in sorted(self.ctx.dispatcher.bus.units(), key=lambda u: u.id):
            caps = ", ".join(unit.capabilities)
            item = QListWidgetItem(
                f"{unit.id}  (min_level={unit.min_level})  caps: {caps}"
            )
            self.list.addItem(item)