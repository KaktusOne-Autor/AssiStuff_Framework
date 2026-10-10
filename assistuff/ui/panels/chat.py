"""Chat panel — main conversation view."""

from __future__ import annotations

import asyncio
import logging

from PyQt6.QtCore import QObject, QRunnable, QThreadPool, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from assistuff.bus.events import ChainEvent

from ..shell.context import UiContext
from ..widgets.chat_input import ChatInput
from ..widgets.mic_button import MicButton

logger = logging.getLogger(__name__)


class _Signals(QObject):
    event = pyqtSignal(object)
    done = pyqtSignal(str)
    error = pyqtSignal(str)


class _AskWorker(QRunnable):
    def __init__(self, dispatcher, query: str) -> None:
        super().__init__()
        self.dispatcher = dispatcher
        self.query = query
        self.signals = _Signals()

    @pyqtSlot()
    def run(self) -> None:
        try:
            asyncio.run(self._run())
        except Exception as exc:
            logger.exception("ask failed")
            self.signals.error.emit(str(exc))

    async def _run(self) -> None:
        final = ""
        async for event in self.dispatcher.handle(self.query):
            self.signals.event.emit(event)
            if event.kind == "result":
                text = event.payload.get("text")
                if isinstance(text, str):
                    final = text
        self.signals.done.emit(final)


class ChatPanel(QWidget):
    def __init__(self, ctx: UiContext, parent=None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self._pool = QThreadPool(self)
        self._busy = False

        layout = QVBoxLayout(self)

        header = QHBoxLayout()
        self.status = QLabel("Ready")
        self.status.setStyleSheet("color: green;")
        self.profile_label = QLabel(f"Profile: {ctx.profile}")
        header.addWidget(self.status)
        header.addStretch()
        header.addWidget(self.profile_label)
        layout.addLayout(header)

        self.history = QPlainTextEdit()
        self.history.setReadOnly(True)
        self.history.setPlaceholderText("Сообщения появятся здесь.")
        layout.addWidget(self.history)

        self.input = ChatInput()
        self.input.submitted.connect(self._on_submit)
        layout.addWidget(self.input)

        buttons = QHBoxLayout()
        self.send_button = QPushButton("Send")
        self.send_button.clicked.connect(self._on_send_clicked)
        self.mic_button = MicButton()
        self.mic_button.toggled.connect(self._on_mic_toggled)
        self.clear_button = QPushButton("Clear")
        self.clear_button.clicked.connect(self.history.clear)
        buttons.addWidget(self.send_button)
        buttons.addWidget(self.mic_button)
        buttons.addWidget(self.clear_button)
        buttons.addStretch()
        layout.addLayout(buttons)

        self.ctx.metadata["chat_panel"] = self

    # ------------------------------------------------------------------
    # Input handling
    # ------------------------------------------------------------------

    def _on_send_clicked(self) -> None:
        text = self.input.toPlainText().strip()
        if text:
            self._on_submit(text)

    def _on_submit(self, text: str) -> None:
        if self._busy:
            return
        if self.ctx.dispatcher is None:
            self.history.appendPlainText("[ui] dispatcher not available")
            return
        self.input.clear()
        self.history.appendPlainText(f"You: {text}")
        self._busy = True
        self.send_button.setEnabled(False)
        self.status.setText("Thinking…")
        self.status.setStyleSheet("color: orange;")

        worker = _AskWorker(self.ctx.dispatcher, text)
        worker.signals.event.connect(self._on_event)
        worker.signals.done.connect(self._on_done)
        worker.signals.error.connect(self._on_error)
        self._pool.start(worker)

    def _on_mic_toggled(self, active: bool) -> None:
        self.history.appendPlainText(
            f"[ui] microphone {'enabled' if active else 'disabled'} (voice pipeline not wired yet)"
        )

    # ------------------------------------------------------------------
    # Stream handling
    # ------------------------------------------------------------------

    @pyqtSlot(object)
    def _on_event(self, event: ChainEvent) -> None:
        if self.ctx.config.framework.output_chain.stream_to_gui:
            text = event.payload.get("text")
            if isinstance(text, str):
                preview = text if len(text) <= 300 else text[:300] + "…"
                self.history.appendPlainText(f"[{event.source}] {preview}")

    @pyqtSlot(str)
    def _on_done(self, final: str) -> None:
        self.history.appendPlainText(f"AssiStuff: {final}")
        self._busy = False
        self.send_button.setEnabled(True)
        self.status.setText("Ready")
        self.status.setStyleSheet("color: green;")

    @pyqtSlot(str)
    def _on_error(self, error: str) -> None:
        self.history.appendPlainText(f"[error] {error}")
        self._busy = False
        self.send_button.setEnabled(True)
        self.status.setText("Error")
        self.status.setStyleSheet("color: red;")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def append_system(self, text: str) -> None:
        self.history.appendPlainText(f"[system] {text}")