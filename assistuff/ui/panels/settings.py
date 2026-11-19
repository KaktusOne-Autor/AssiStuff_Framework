"""Settings panel."""

from __future__ import annotations

from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from assistuff.memory.profiles import ProfileManager

from ..shell.context import (
    AUDIO_ENABLED_SETTING,
    SETTINGS_APPLICATION,
    SETTINGS_ORGANIZATION,
    UiContext,
)


class SettingsPanel(QWidget):
    def __init__(self, ctx: UiContext, parent=None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.settings = ctx.metadata.get("settings")
        if not isinstance(self.settings, QSettings):
            self.settings = QSettings(SETTINGS_ORGANIZATION, SETTINGS_APPLICATION)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Settings"))

        form = QFormLayout()

        self.profile_combo = QComboBox()
        try:
            pm = ProfileManager(ctx.config.framework.profiles.storage_dir)
            for profile in pm.list_profiles():
                self.profile_combo.addItem(profile)
            idx = self.profile_combo.findText(ctx.profile)
            if idx >= 0:
                self.profile_combo.setCurrentIndex(idx)
        except Exception:
            self.profile_combo.addItem(ctx.profile)
        form.addRow("Active profile", self.profile_combo)

        self.theme_label = QLabel(ctx.config.framework.ui.theme)
        form.addRow("Theme", self.theme_label)

        self.stream_checkbox = QCheckBox("Stream events to chat")
        self.stream_checkbox.setChecked(
            ctx.config.framework.output_chain.stream_to_gui
        )
        form.addRow("Streaming", self.stream_checkbox)

        self.audio_checkbox = QCheckBox("Enable audio controls")
        self.audio_checkbox.setChecked(ctx.config.framework.voice.enabled)
        self.audio_checkbox.toggled.connect(self._set_audio_enabled)
        form.addRow("Audio", self.audio_checkbox)
        self.audio_status = QLabel(
            "Audio is off by default. Enabling it reveals microphone, voice "
            "enrollment, wake-word, and configured speech-output controls."
        )
        self.audio_status.setWordWrap(True)
        form.addRow("", self.audio_status)

        self.telemetry_checkbox = QCheckBox("Show telemetry dock at startup")
        self.telemetry_checkbox.setChecked(False)
        form.addRow("Telemetry", self.telemetry_checkbox)

        layout.addLayout(form)
        layout.addStretch()

    def _set_audio_enabled(self, enabled: bool) -> None:
        self.ctx.config.framework.voice.enabled = enabled
        self.settings.setValue(AUDIO_ENABLED_SETTING, enabled)
        self.settings.sync()
        if self.settings.status() == QSettings.Status.NoError:
            self.audio_status.setText(
                "Audio enabled for this app."
                if enabled
                else "Audio disabled; voice controls are hidden."
            )
        else:
            self.audio_status.setText(
                "Audio setting changed for this session, but could not be saved."
            )
        chat_panel = self.ctx.metadata.get("chat_panel")
        update_audio = getattr(chat_panel, "set_audio_enabled", None)
        if callable(update_audio):
            update_audio(enabled)
