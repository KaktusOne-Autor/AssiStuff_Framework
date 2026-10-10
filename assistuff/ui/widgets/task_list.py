"""Task list widget."""

from __future__ import annotations

from PyQt6.QtWidgets import QListWidget


class TaskList(QListWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setAlternatingRowColors(True)
        self.setMaximumHeight(220)