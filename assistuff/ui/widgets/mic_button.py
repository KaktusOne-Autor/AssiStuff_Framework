"""Microphone toggle button."""

from __future__ import annotations

from PyQt6.QtWidgets import QPushButton


class MicButton(QPushButton):
    def __init__(self, parent=None) -> None:
        super().__init__("🎤", parent)
        self.setCheckable(True)
        self.setToolTip("Toggle microphone")
        self.setFixedWidth(48)