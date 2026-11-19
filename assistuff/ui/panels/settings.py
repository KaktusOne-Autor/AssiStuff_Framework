"""Settings panel."""

from __future__ import annotations

from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from assistuff.config.api_connections import ApiConnectionError, save_api_connection
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

        api_group = QGroupBox("OpenAI-compatible API")
        api_layout = QVBoxLayout(api_group)
        api_form = QFormLayout()
        self.api_profile = QLineEdit()
        self.api_profile.setPlaceholderText("e.g. openai")
        self.api_model_id = QLineEdit()
        self.api_model_id.setPlaceholderText("e.g. gpt-4o")
        self.api_model_name = QLineEdit()
        self.api_model_name.setPlaceholderText("Provider model name")
        self.api_base_url = QLineEdit("https://api.openai.com/v1")
        self.api_key = QLineEdit()
        self.api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key.setPlaceholderText("Stored in the operating system credential store")
        self.api_insecure_http = QCheckBox("Allow HTTP for a trusted local endpoint")
        api_form.addRow("Connection profile", self.api_profile)
        api_form.addRow("Model ID", self.api_model_id)
        api_form.addRow("Provider model", self.api_model_name)
        api_form.addRow("Base URL", self.api_base_url)
        api_form.addRow("API key", self.api_key)
        api_form.addRow("", self.api_insecure_http)
        api_layout.addLayout(api_form)
        self.api_attach_button = QPushButton("Save API model")
        self.api_attach_button.clicked.connect(self._save_api_model)
        api_layout.addWidget(self.api_attach_button)
        self.api_status = QLabel(
            "Add a model ID and provider model name. The model will be available "
            "after restarting AssiStuff."
        )
        self.api_status.setWordWrap(True)
        api_layout.addWidget(self.api_status)
        layout.addWidget(api_group)

        layout.addStretch()

    def _save_api_model(self) -> None:
        self.api_attach_button.setEnabled(False)
        try:
            manifest = save_api_connection(
                self.ctx.config.user_root,
                profile=self.api_profile.text().strip(),
                model_id=self.api_model_id.text().strip(),
                model_name=self.api_model_name.text().strip(),
                base_url=self.api_base_url.text().strip(),
                api_key=self.api_key.text(),
                existing_model_ids=self.ctx.config.models,
                existing_profiles=self.ctx.config.framework.runtime.remote_endpoints,
                allow_insecure_http=self.api_insecure_http.isChecked(),
            )
        except (ApiConnectionError, ValueError) as exc:
            self.api_status.setText(f"Could not save API model: {exc}")
        else:
            self.api_key.clear()
            self.api_status.setText(
                f"Saved {manifest.id!r}. Its key is stored in the OS credential "
                "store; restart AssiStuff to load the model."
            )
        finally:
            self.api_attach_button.setEnabled(True)

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
