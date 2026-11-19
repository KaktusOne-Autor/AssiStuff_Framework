"""Main window — tabbed shell."""

from __future__ import annotations

import logging

from PyQt6.QtCore import QPropertyAnimation, QSettings
from PyQt6.QtGui import QAction, QCloseEvent
from PyQt6.QtWidgets import (
    QApplication,
    QGraphicsOpacityEffect,
    QMainWindow,
    QTabWidget,
    QWidget,
)

from assistuff.access.user import User
from assistuff.config.schemas import RuntimeConfigBundle

from ..panels import (
    ChatPanel,
    GraphPanel,
    MemoryPanel,
    ModelsPanel,
    PluginsPanel,
    SettingsPanel,
    SkillsPanel,
    TasksPanel,
    TracePanel,
    VisualOutputPanel,
    VttPanel,
)
from ..widgets.telemetry_dock import TelemetryDock
from .context import (
    AUDIO_ENABLED_SETTING,
    SETTINGS_APPLICATION,
    SETTINGS_ORGANIZATION,
    UiContext,
)
from .tab_registry import TabRegistry

logger = logging.getLogger(__name__)


def build_default_registry() -> TabRegistry:
    reg = TabRegistry()
    reg.register("chat", "Chat", lambda ctx: ChatPanel(ctx), order=10)
    reg.register("models", "Models", lambda ctx: ModelsPanel(ctx), order=20)
    reg.register("tasks", "Tasks", lambda ctx: TasksPanel(ctx), order=30)
    reg.register("memory", "Memory", lambda ctx: MemoryPanel(ctx), order=40)
    reg.register("visual", "Visual Output", lambda ctx: VisualOutputPanel(ctx), order=45)
    reg.register("vtt", "VTT", lambda ctx: VttPanel(ctx), order=48)
    reg.register("skills", "Skills", lambda ctx: SkillsPanel(ctx), order=50)
    reg.register("trace", "Trace", lambda ctx: TracePanel(ctx), order=60)
    reg.register("settings", "Settings", lambda ctx: SettingsPanel(ctx), order=70)
    reg.register("plugins", "Plugins", lambda ctx: PluginsPanel(ctx), order=80)
    reg.register("graph", "Graph", lambda ctx: GraphPanel(ctx), order=55)
    return reg


class MainWindow(QMainWindow):
    def __init__(
        self,
        config: RuntimeConfigBundle,
        *,
        dispatcher=None,
        profile: str | None = None,
        user: User | None = None,
        registry: TabRegistry | None = None,
    ) -> None:
        super().__init__()

        self.config = config
        self.dispatcher = dispatcher
        self.settings = QSettings(SETTINGS_ORGANIZATION, SETTINGS_APPLICATION)
        audio_enabled = self.settings.value(
            AUDIO_ENABLED_SETTING,
            config.framework.voice.enabled,
            type=bool,
        )
        config.framework.voice.enabled = audio_enabled
        self.ctx = UiContext(
            config=config,
            dispatcher=dispatcher,
            profile=profile or config.framework.profiles.default,
            user_level=user.level if user and user.authenticated else 0,
            user_name=user.name if user and user.authenticated else "guest",
            account_id=user.account_id if user and user.authenticated else None,
            authenticated=bool(user and user.authenticated),
        )
        self.ctx.metadata["settings"] = self.settings

        self.setWindowTitle(
            f"AssiStuff {config.framework.framework.version} — "
            f"{self.ctx.user_name} / {self.ctx.profile}"
        )
        self.resize(1100, 780)
        self.setStyleSheet(
            """
            QMainWindow, QWidget { background: #0a120e; color: #e4f5e9; }
            QTabWidget::pane { border: 1px solid #244c34; }
            QTabBar::tab {
                background: #102019; color: #a7c7b1;
                border: 1px solid #244c34; padding: 8px 14px;
                margin-right: 2px; border-top-left-radius: 5px;
                border-top-right-radius: 5px;
            }
            QTabBar::tab:selected { background: #163d27; color: #74f29b; }
            QPushButton {
                background: #173b27; color: #dfffea;
                border: 1px solid #39a85f; border-radius: 5px;
                padding: 6px 12px;
            }
            QPushButton:hover { background: #205536; }
            QPushButton:pressed { background: #0f2c1c; }
            QLineEdit, QPlainTextEdit, QListWidget, QComboBox {
                background: #0d1b13; color: #e4f5e9;
                border: 1px solid #28533a; border-radius: 4px;
                selection-background-color: #24653b;
            }
            QMenuBar, QMenu { background: #0c1710; color: #e4f5e9; }
            QMenu::item:selected { background: #205536; }
            """
        )

        self.tabs = QTabWidget()
        self._tab_animations: dict[QWidget, tuple[QGraphicsOpacityEffect, QPropertyAnimation]] = {}
        self.tabs.currentChanged.connect(self._animate_tab)
        self.setCentralWidget(self.tabs)

        self.registry = registry or build_default_registry()
        self._build_tabs()

        # Telemetry dock (hidden by default)
        self.telemetry_dock = TelemetryDock(
            self,
            interval_ms=config.framework.ui.telemetry_interval_ms,
        )
        self.addDockWidget(
            __import__("PyQt6.QtCore", fromlist=["Qt"]).Qt.DockWidgetArea.BottomDockWidgetArea,
            self.telemetry_dock,
        )
        self.telemetry_dock.hide()

        self._install_log_handler()
        self._build_menu()

    def _build_tabs(self) -> None:
        for entry in self.registry.ordered():
            try:
                widget = entry.factory(self.ctx)
            except Exception:
                logger.exception("failed to build tab %s", entry.tab_id)
                widget = QWidget()
            self.tabs.addTab(widget, entry.title)

    def _build_menu(self) -> None:
        menu = self.menuBar()

        view_menu = menu.addMenu("View")

        toggle = QAction("Toggle telemetry dock", self)
        toggle.setShortcut("Ctrl+T")
        toggle.triggered.connect(self._toggle_telemetry)
        view_menu.addAction(toggle)

        reload_action = QAction("Reload panels", self)
        reload_action.setShortcut("Ctrl+R")
        reload_action.triggered.connect(self._reload_panels)
        view_menu.addAction(reload_action)

        quit_action = QAction("Quit", self)
        quit_action.setShortcut("Ctrl+Q")
        quit_action.triggered.connect(QApplication.instance().quit)
        view_menu.addAction(quit_action)

    def _toggle_telemetry(self) -> None:
        self.telemetry_dock.setVisible(not self.telemetry_dock.isVisible())

    def _animate_tab(self, index: int) -> None:
        widget = self.tabs.widget(index)
        if widget is None:
            return
        previous = self._tab_animations.pop(widget, None)
        if previous is not None:
            previous[1].stop()
            widget.setGraphicsEffect(None)

        effect = QGraphicsOpacityEffect(widget)
        effect.setOpacity(0.35)
        widget.setGraphicsEffect(effect)
        animation = QPropertyAnimation(effect, b"opacity", self)
        animation.setDuration(180)
        animation.setStartValue(0.35)
        animation.setEndValue(1.0)

        def finish() -> None:
            current = self._tab_animations.get(widget)
            if current is not None and current[1] is animation:
                self._tab_animations.pop(widget, None)
            if widget.graphicsEffect() is effect:
                widget.setGraphicsEffect(None)
            animation.deleteLater()

        animation.finished.connect(finish)
        self._tab_animations[widget] = (effect, animation)
        animation.start()

    def _reload_panels(self) -> None:
        for i in range(self.tabs.count()):
            widget = self.tabs.widget(i)
            reload_fn = getattr(widget, "reload", None)
            if callable(reload_fn):
                try:
                    reload_fn()
                except Exception:
                    logger.exception("reload failed for tab %d", i)

    def _install_log_handler(self) -> None:
        import logging as _logging

        class _QtHandler(_logging.Handler):
            def __init__(self, dock: TelemetryDock) -> None:
                super().__init__(_logging.INFO)
                self.dock = dock
                self.setFormatter(_logging.Formatter(
                    "%(asctime)s %(levelname)s %(name)s: %(message)s",
                    datefmt="%H:%M:%S",
                ))

            def emit(self, record: _logging.LogRecord) -> None:
                try:
                    self.dock.append_log(self.format(record))
                except Exception:
                    pass

        self._log_handler = _QtHandler(self.telemetry_dock)
        _logging.getLogger().addHandler(self._log_handler)

    def closeEvent(self, event: QCloseEvent) -> None:
        try:
            self.telemetry_dock.stop()
        except Exception:
            pass
        try:
            import logging as _logging
            _logging.getLogger().removeHandler(self._log_handler)
        except Exception:
            pass
        super().closeEvent(event)
