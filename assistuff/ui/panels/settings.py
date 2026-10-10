"""Settings panel."""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from assistuff.memory.profiles import ProfileManager

from ..shell.context import UiContext


class SettingsPanel(QWidget):
    def __init__(self, ctx: UiContext, parent=None) -> None:
        super().__init__(parent)
        self.ctx = ctx

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

        self.telemetry_checkbox = QCheckBox("Show telemetry dock at startup")
        self.telemetry_checkbox.setChecked(False)
        form.addRow("Telemetry", self.telemetry_checkbox)

        layout.addLayout(form)
        layout.addStretch()