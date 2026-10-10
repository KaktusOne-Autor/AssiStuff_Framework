"""Main window — tabbed shell."""

from __future__ import annotations

import logging

from PyQt6.QtGui import QAction, QCloseEvent, QIcon
from PyQt6.QtWidgets import (
    QApplication,
    QMainWindow,
    QTabWidget,
    QWidget,
)

from assistuff.config.schemas import RuntimeConfigBundle

from ..panels import (
    ChatPanel,
    MemoryPanel,
    ModelsPanel,
    PluginsPanel,
    SettingsPanel,
    SkillsPanel,
    TasksPanel,
    TracePanel,
)
from ..widgets.telemetry_dock import TelemetryDock
from .context import UiContext
from .tab_registry import TabRegistry

logger = logging.getLogger(__name__)


def build_default_registry() -> TabRegistry:
    reg = TabRegistry()
    reg.register("chat", "Chat", lambda ctx: ChatPanel(ctx), order=10)
    reg.register("models", "Models", lambda ctx: ModelsPanel(ctx), order=20)
    reg.register("tasks", "Tasks", lambda ctx: TasksPanel(ctx), order=30)
    reg.register("memory", "Memory", lambda ctx: MemoryPanel(ctx), order=40)
    reg.register("skills", "Skills", lambda ctx: SkillsPanel(ctx), order=50)
    reg.register("trace", "Trace", lambda ctx: TracePanel(ctx), order=60)
    reg.register("settings", "Settings", lambda ctx: SettingsPanel(ctx), order=70)
    reg.register("plugins", "Plugins", lambda ctx: PluginsPanel(ctx), order=80)
    return reg


class MainWindow(QMainWindow):
    def __init__(
        self,
        config: RuntimeConfigBundle,
        *,
        dispatcher=None,
        profile: str | None = None,
        registry: TabRegistry | None = None,
    ) -> None:
        super().__init__()

        self.config = config
        self.dispatcher = dispatcher
        self.ctx = UiContext(
            config=config,
            dispatcher=dispatcher,
            profile=profile or config.framework.profiles.default,
            user_level=(
                config.framework.access.profile_levels.get(
                    profile or config.framework.profiles.default,
                    config.framework.access.default_level,
                )
            ),
        )

        self.setWindowTitle(
            f"AssiStuff {config.framework.framework.version} — {self.ctx.profile}"
        )
        self.resize(1100, 780)

        self.tabs = QTabWidget()
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