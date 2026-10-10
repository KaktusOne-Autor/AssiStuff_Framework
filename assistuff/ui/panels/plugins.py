"""Plugins panel."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtWidgets import (
    QLabel,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..shell.context import UiContext


class PluginsPanel(QWidget):
    def __init__(self, ctx: UiContext, parent=None) -> None:
        super().__init__(parent)
        self.ctx = ctx

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Enabled plugins"))

        self.enabled_list = QListWidget()
        layout.addWidget(self.enabled_list)

        layout.addWidget(QLabel("Available plugins in plugins/"))

        self.available_list = QListWidget()
        layout.addWidget(self.available_list)

        self.reload()

    def reload(self) -> None:
        self.enabled_list.clear()
        self.available_list.clear()

        enabled = self.ctx.config.framework.tasks.enabled_plugins
        for pid in enabled:
            self.enabled_list.addItem(QListWidgetItem(pid))

        plugin_dir = Path(self.ctx.config.framework.tasks.plugin_dir)
        if not plugin_dir.is_absolute():
            plugin_dir = self.ctx.config.project_root / plugin_dir
        if plugin_dir.is_dir():
            for manifest in sorted(plugin_dir.glob("*.json")):
                self.available_list.addItem(QListWidgetItem(manifest.stem))