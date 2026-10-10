"""System tray icon."""

from __future__ import annotations

import logging

from PyQt6.QtGui import QAction, QIcon
from PyQt6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

logger = logging.getLogger(__name__)


class AssiStuffTray(QSystemTrayIcon):
    def __init__(self, window=None, parent=None) -> None:
        super().__init__(parent)
        self.window = window
        self.setToolTip("AssiStuff")
        self.setIcon(QIcon.fromTheme("applications-science"))

        menu = QMenu()

        open_action = QAction("Open window", self)
        open_action.triggered.connect(self._open_window)
        menu.addAction(open_action)

        toggle_telemetry = QAction("Toggle telemetry", self)
        toggle_telemetry.triggered.connect(self._toggle_telemetry)
        menu.addAction(toggle_telemetry)

        menu.addSeparator()

        quit_action = QAction("Quit", self)
        quit_action.triggered.connect(QApplication.instance().quit)
        menu.addAction(quit_action)

        self.setContextMenu(menu)
        self.activated.connect(self._on_activated)

    def _open_window(self) -> None:
        if self.window is None:
            return
        self.window.showNormal()
        self.window.raise_()
        self.window.activateWindow()

    def _toggle_telemetry(self) -> None:
        if self.window is None:
            return
        dock = getattr(self.window, "telemetry_dock", None)
        if dock is not None:
            dock.setVisible(not dock.isVisible())

    def _on_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self._open_window()