"""Chat panel — main conversation view."""

from __future__ import annotations

import asyncio
import logging
import threading

from PyQt6.QtCore import QObject, QRunnable, QThreadPool, QTimer, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from assistuff.bus.emitters.tts import TtsEmitter
from assistuff.bus.events import ChainEvent

from ..shell.context import UiContext
from ..widgets.chat_input import ChatInput
from ..widgets.mic_button import MicButton

logger = logging.getLogger(__name__)


class _Signals(QObject):
    event = pyqtSignal(object)
    done = pyqtSignal(str)
    error = pyqtSignal(str)
    voice_error = pyqtSignal(str)


class _VoiceSignals(QObject):
    transcript = pyqtSignal(str)
    embedding = pyqtSignal(object)
    wake_detected = pyqtSignal(str)
    error = pyqtSignal(str)
    finished = pyqtSignal(str)


class _VoiceWorker(QRunnable):
    def __init__(self, pipeline, action: str, stop_event: threading.Event) -> None:
        super().__init__()
        self.pipeline = pipeline
        self.action = action
        self.stop_event = stop_event
        self.signals = _VoiceSignals()

    @pyqtSlot()
    def run(self) -> None:
        try:
            if self.action == "transcribe":
                clip = self.pipeline.capture(stop_event=self.stop_event)
                transcript = asyncio.run(self.pipeline.transcribe_clip(clip))
                self.signals.transcript.emit(transcript)
            elif self.action == "enroll":
                clip = self.pipeline.capture_enrollment_sample(stop_event=self.stop_event)
                embedding = self.pipeline.extract_enrollment_sample(clip)
                self.signals.embedding.emit(embedding)
            elif self.action == "wake":
                phrase = self.pipeline.listen_for_wake(self.stop_event)
                if phrase:
                    self.signals.wake_detected.emit(phrase)
            else:
                raise ValueError(f"unknown voice task: {self.action}")
        except Exception as exc:
            logger.exception("voice %s task failed", self.action)
            self.signals.error.emit(str(exc))
        finally:
            self.signals.finished.emit(self.action)


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
        self._voice_pipeline = getattr(ctx.dispatcher, "voice", None)
        self._voice_worker: _VoiceWorker | None = None
        self._voice_stop_event: threading.Event | None = None
        self._voice_mode: str | None = None
        self._enrollment_active = False
        self._enrollment_samples: list[list[float]] = []
        self._wake_triggered = False

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
        self.mic_button.setToolTip("Record a local voice turn; click again to stop")
        self.enroll_button = QPushButton("Enroll voice")
        self.enroll_button.clicked.connect(self._on_enroll_clicked)
        self.cancel_enrollment_button = QPushButton("Cancel enrollment")
        self.cancel_enrollment_button.setEnabled(False)
        self.cancel_enrollment_button.clicked.connect(self._cancel_enrollment)
        self.delete_voiceprint_button = QPushButton("Delete voiceprint")
        self.delete_voiceprint_button.clicked.connect(self._delete_voiceprint)
        self.wake_checkbox = QCheckBox("Wake word")
        self.wake_checkbox.setToolTip(
            "Opt in to continuous local microphone listening for a configured phrase."
        )
        self.wake_checkbox.toggled.connect(self._on_wake_toggled)
        self.clear_button = QPushButton("Clear")
        self.clear_button.clicked.connect(self.history.clear)
        buttons.addWidget(self.send_button)
        buttons.addWidget(self.mic_button)
        buttons.addWidget(self.enroll_button)
        buttons.addWidget(self.cancel_enrollment_button)
        buttons.addWidget(self.delete_voiceprint_button)
        buttons.addWidget(self.wake_checkbox)
        buttons.addWidget(self.clear_button)
        buttons.addStretch()
        layout.addLayout(buttons)

        self._signals = _Signals()
        self._signals.voice_error.connect(self._on_tts_error)
        self._tts_emitter = None
        if (
            self._voice_pipeline is not None
            and ctx.config.framework.voice.tts.enabled
            and "tts" in ctx.config.framework.output_chain.emitters
        ):
            self._tts_emitter = TtsEmitter(
                self._voice_pipeline.tts.speak,
                on_error=lambda exc: self._signals.voice_error.emit(str(exc)),
            )
            ctx.dispatcher.chain.subscribe_final(self._speak_final_result)
        self._update_voice_controls()
        self.ctx.metadata["chat_panel"] = self

    # ------------------------------------------------------------------
    # Input handling
    # ------------------------------------------------------------------

    def _on_send_clicked(self) -> None:
        text = self.input.toPlainText().strip()
        if text:
            self._on_submit(text)

    def _on_submit(self, text: str, *, source_label: str = "You") -> None:
        if self._busy:
            return
        if self._voice_worker is not None and source_label != "You (voice)":
            if self._voice_mode == "wake":
                self.wake_checkbox.setChecked(False)
            else:
                self.status.setText("Finish or cancel the current voice task first.")
                return
        if self.ctx.dispatcher is None:
            self.history.appendPlainText("[ui] dispatcher not available")
            return
        self.input.clear()
        self.history.appendPlainText(f"{source_label}: {text}")
        self._busy = True
        self.send_button.setEnabled(False)
        self.mic_button.setEnabled(False)
        self.wake_checkbox.setEnabled(False)
        self.status.setText("Thinking…")
        self.status.setStyleSheet("color: orange;")

        worker = _AskWorker(self.ctx.dispatcher, text)
        worker.signals.event.connect(self._on_event)
        worker.signals.done.connect(self._on_done)
        worker.signals.error.connect(self._on_error)
        self._pool.start(worker)

    def _on_mic_toggled(self, active: bool) -> None:
        if not active:
            if self._voice_mode == "transcribe" and self._voice_stop_event is not None:
                self.status.setText("Stopping recording…")
                self._voice_stop_event.set()
            return
        if self._busy:
            self._set_mic_idle()
            return
        if not self.ctx.config.framework.voice.enabled:
            self._set_mic_idle()
            return
        if self._voice_worker is not None:
            self._set_mic_idle()
            self.status.setText("Another voice task is already active.")
            return
        if self._voice_pipeline is None:
            self._set_mic_idle()
            self._on_voice_error("Voice pipeline is unavailable; restart the GUI.")
            return
        if (
            self.ctx.config.framework.voice.auth.enabled
            and not self._voice_pipeline.auth.has_voiceprint(self.ctx.profile)
        ):
            self._set_mic_idle()
            self._on_voice_error(
                f"No voiceprint is enrolled for profile {self.ctx.profile!r}. "
                "Select Enroll voice before using the microphone."
            )
            return
        self.mic_button.setText("Stop")
        self.status.setText("Listening…")
        self._start_voice_task("transcribe")

    def _start_voice_task(self, action: str) -> None:
        if self._voice_worker is not None:
            return
        stop_event = threading.Event()
        worker = _VoiceWorker(self._voice_pipeline, action, stop_event)
        worker.signals.transcript.connect(self._on_voice_transcript)
        worker.signals.embedding.connect(self._on_enrollment_embedding)
        worker.signals.wake_detected.connect(self._on_wake_detected)
        worker.signals.error.connect(self._on_voice_error)
        worker.signals.finished.connect(self._on_voice_task_finished)
        self._voice_worker = worker
        self._voice_stop_event = stop_event
        self._voice_mode = action
        self._pool.start(worker)

    @pyqtSlot(str)
    def _on_voice_transcript(self, transcript: str) -> None:
        self._set_mic_idle()
        if not self.ctx.config.framework.voice.enabled:
            return
        self._on_submit(transcript, source_label="You (voice)")

    @pyqtSlot(object)
    def _on_enrollment_embedding(self, embedding: list[float]) -> None:
        if not self._enrollment_active:
            return
        self._enrollment_samples.append(embedding)
        required = self.ctx.config.framework.voice.auth.enrollment_samples
        if len(self._enrollment_samples) < required:
            sample_number = len(self._enrollment_samples) + 1
            self.enroll_button.setText(f"Record sample {sample_number}/{required}")
            self.enroll_button.setEnabled(True)
            self.status.setText(f"Sample saved. Record sample {sample_number} of {required}.")
            return
        try:
            self._voice_pipeline.save_enrollment(self._enrollment_samples)
        except Exception as exc:
            self._on_voice_error(f"Could not save voiceprint: {exc}")
        else:
            self.status.setText(
                f"Voiceprint enrolled for profile {self.ctx.profile}. "
                "Only the speaker vector is stored; raw audio is discarded."
            )
        self._enrollment_active = False
        self._enrollment_samples.clear()
        self._update_voice_controls()

    def _on_enroll_clicked(self) -> None:
        if not self.ctx.config.framework.voice.enabled:
            return
        if self._voice_pipeline is None:
            self._on_voice_error("Voice pipeline is unavailable.")
            return
        if self._voice_worker is not None:
            return
        if not self._enrollment_active:
            answer = QMessageBox.question(
                self,
                "Enroll voice",
                "Record several short speech samples to create a local voiceprint? "
                "Raw audio is discarded; only a speaker vector is stored for this "
                f"profile ({self.ctx.profile}).",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
            self._enrollment_active = True
            self._enrollment_samples.clear()
            self.cancel_enrollment_button.setEnabled(True)
            self.enroll_button.setText(
                f"Record sample 1/{self.ctx.config.framework.voice.auth.enrollment_samples}"
            )
        self.enroll_button.setEnabled(False)
        self.status.setText("Speak a short sample. Recording ends after the configured silence.")
        self._start_voice_task("enroll")

    def _cancel_enrollment(self) -> None:
        if self._voice_mode == "enroll" and self._voice_stop_event is not None:
            self._voice_stop_event.set()
        self._enrollment_active = False
        self._enrollment_samples.clear()
        self._update_voice_controls()
        self.status.setText("Voice enrollment canceled.")

    def _delete_voiceprint(self) -> None:
        if self._voice_pipeline is None:
            return
        answer = QMessageBox.question(
            self,
            "Delete voiceprint",
            f"Delete the local voiceprint for profile {self.ctx.profile}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._voice_pipeline.auth.store.delete(self.ctx.profile)
        self._update_voice_controls()
        self.status.setText("Voiceprint deleted.")

    def _update_voice_controls(self) -> None:
        enabled = self.ctx.config.framework.voice.enabled
        available = enabled and self._voice_pipeline is not None
        self.mic_button.setVisible(enabled)
        self.enroll_button.setVisible(enabled)
        self.cancel_enrollment_button.setVisible(enabled and self._enrollment_active)
        self.delete_voiceprint_button.setVisible(enabled)
        self.wake_checkbox.setVisible(enabled)
        self.mic_button.setEnabled(available and not self._busy)
        self.enroll_button.setEnabled(available and self._voice_worker is None)
        self.cancel_enrollment_button.setEnabled(self._enrollment_active)
        has_voiceprint = False
        if available:
            try:
                has_voiceprint = self._voice_pipeline.auth.has_voiceprint(self.ctx.profile)
            except Exception as exc:
                self.status.setText(f"Voiceprint status unavailable: {exc}")
        self.delete_voiceprint_button.setEnabled(has_voiceprint)
        self.wake_checkbox.setEnabled(available and not self._busy)

    def set_audio_enabled(self, enabled: bool) -> None:
        self.ctx.config.framework.voice.enabled = enabled
        if not enabled:
            if self.wake_checkbox.isChecked():
                self.wake_checkbox.setChecked(False)
            if self._voice_stop_event is not None:
                self._voice_stop_event.set()
            self._enrollment_active = False
            self._enrollment_samples.clear()
            if self.mic_button.isChecked():
                self._set_mic_idle()
        self._update_voice_controls()

    def _on_wake_toggled(self, active: bool) -> None:
        if not active:
            if self._voice_mode == "wake" and self._voice_stop_event is not None:
                self._voice_stop_event.set()
            if self.status.text().startswith("Wake-word"):
                self.status.setText("Wake-word listening stopped.")
            return
        if (
            not self.ctx.config.framework.voice.enabled
            or self._voice_pipeline is None
            or self._busy
            or self._voice_worker is not None
        ):
            self.wake_checkbox.setChecked(False)
            self._on_voice_error("Wake-word listening is unavailable right now.")
            return
        if (
            self.ctx.config.framework.voice.auth.enabled
            and not self._voice_pipeline.auth.has_voiceprint(self.ctx.profile)
        ):
            self.wake_checkbox.setChecked(False)
            self._on_voice_error("Enroll a voiceprint before enabling wake-word listening.")
            return
        self.status.setText("Wake-word listener active; microphone audio stays local.")
        self._start_voice_task("wake")

    @pyqtSlot(str)
    def _on_wake_detected(self, phrase: str) -> None:
        self._wake_triggered = True
        self.status.setText(f"Wake phrase detected ({phrase}); listening for a request…")

    @pyqtSlot(str)
    def _on_voice_error(self, error: str) -> None:
        self.history.appendPlainText(f"[voice error] {error}")
        self.status.setText("Voice error")
        self.status.setStyleSheet("color: red;")
        self._set_mic_idle()
        if self.wake_checkbox.isChecked():
            self.wake_checkbox.setChecked(False)

    @pyqtSlot(str)
    def _on_tts_error(self, error: str) -> None:
        self.history.appendPlainText(f"[speech output error] {error}")

    @pyqtSlot(str)
    def _on_voice_task_finished(self, action: str) -> None:
        self._voice_worker = None
        self._voice_stop_event = None
        self._voice_mode = None
        if action == "enroll":
            self._update_voice_controls()
        elif action == "transcribe":
            self._set_mic_idle()
            if self.wake_checkbox.isChecked() and not self._busy:
                QTimer.singleShot(300, self._start_wake_listener)
        elif action == "wake":
            if not self.ctx.config.framework.voice.enabled:
                self._wake_triggered = False
                self._set_mic_idle()
                return
            if self._wake_triggered:
                self._wake_triggered = False
                self._set_mic_recording()
                self._start_voice_task("transcribe")
            elif self.wake_checkbox.isChecked():
                self.wake_checkbox.setChecked(False)

    def _start_wake_listener(self) -> None:
        if self.wake_checkbox.isChecked() and not self._busy and self._voice_worker is None:
            self.status.setText("Wake-word listener active; microphone audio stays local.")
            self._start_voice_task("wake")

    def _set_mic_idle(self) -> None:
        self.mic_button.blockSignals(True)
        self.mic_button.setChecked(False)
        self.mic_button.setText("🎤")
        self.mic_button.blockSignals(False)
        self.mic_button.setEnabled(
            self.ctx.config.framework.voice.enabled
            and self._voice_pipeline is not None
            and not self._busy
        )

    def _set_mic_recording(self) -> None:
        self.mic_button.blockSignals(True)
        self.mic_button.setChecked(True)
        self.mic_button.setText("Stop")
        self.mic_button.blockSignals(False)
        self.mic_button.setEnabled(True)

    def _speak_final_result(self, event: ChainEvent) -> None:
        if (
            not self.ctx.config.framework.voice.enabled
            or self._tts_emitter is None
            or self._voice_pipeline is None
        ):
            return
        ready, detail = self._voice_pipeline.diagnostics()["Piper TTS"]
        if not ready:
            self._signals.voice_error.emit(f"Piper TTS unavailable: {detail}")
            return
        self._tts_emitter(event)

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
        self._update_voice_controls()
        self.status.setText("Ready")
        self.status.setStyleSheet("color: green;")
        if self.wake_checkbox.isChecked():
            QTimer.singleShot(500, self._start_wake_listener)

    @pyqtSlot(str)
    def _on_error(self, error: str) -> None:
        self.history.appendPlainText(f"[error] {error}")
        self._busy = False
        self.send_button.setEnabled(True)
        self._update_voice_controls()
        self.status.setText("Error")
        self.status.setStyleSheet("color: red;")
        if self.wake_checkbox.isChecked():
            QTimer.singleShot(500, self._start_wake_listener)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def append_system(self, text: str) -> None:
        self.history.appendPlainText(f"[system] {text}")
