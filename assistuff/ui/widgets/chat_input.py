"""Chat input widget."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QTextEdit


class ChatInput(QTextEdit):
    submitted = pyqtSignal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setPlaceholderText("Введите команду... (Ctrl+Enter — отправить)")
        self.setMaximumHeight(120)

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                text = self.toPlainText().strip()
                if text:
                    self.submitted.emit(text)
                return
        super().keyPressEvent(event)