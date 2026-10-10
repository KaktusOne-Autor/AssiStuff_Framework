"""Trace panel — call graph and events."""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QLabel,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..shell.context import UiContext


class TracePanel(QWidget):
    def __init__(self, ctx: UiContext, parent=None) -> None:
        super().__init__(parent)
        self.ctx = ctx

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Trace — recent chain events"))

        self.view = QPlainTextEdit()
        self.view.setReadOnly(True)
        self.view.setMaximumBlockCount(2000)
        layout.addWidget(self.view)

        if ctx.dispatcher is not None:
            ctx.dispatcher.chain.subscribe(self._on_event)

    def _on_event(self, event) -> None:
        preview = event.payload.get("text")
        if isinstance(preview, str) and len(preview) > 200:
            preview = preview[:200] + "…"
        if preview is None:
            preview = str(event.payload)
        line = f"[{event.trace_id[:8]}] {event.source} ({event.kind}): {preview}"
        self.view.appendPlainText(line)