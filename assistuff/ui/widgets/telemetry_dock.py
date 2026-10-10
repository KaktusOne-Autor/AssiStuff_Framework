"""Telemetry as a dock widget, hidden by default."""

from __future__ import annotations

import logging
import math

import pyqtgraph as pg
import psutil
from PyQt6.QtCore import QObject, QRunnable, QThreadPool, QTimer, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import (
    QDockWidget,
    QLabel,
    QPlainTextEdit,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

logger = logging.getLogger(__name__)


class _Signals(QObject):
    updated = pyqtSignal(dict)
    failed = pyqtSignal(str)


class _Worker(QRunnable):
    def __init__(self) -> None:
        super().__init__()
        self.signals = _Signals()

    @pyqtSlot()
    def run(self) -> None:
        try:
            cpu = psutil.cpu_percent(interval=None)
            mem = psutil.virtual_memory()
            data = {
                "cpu": float(cpu),
                "ram": float(mem.percent),
                "ram_used_gb": mem.used / 1e9,
                "ram_total_gb": mem.total / 1e9,
                "gpu": None,
            }
        except Exception as exc:
            self.signals.failed.emit(str(exc))
        else:
            self.signals.updated.emit(data)


class TelemetryDock(QDockWidget):
    def __init__(self, parent=None, *, interval_ms: int = 1000) -> None:
        super().__init__("Telemetry", parent)
        self.setObjectName("TelemetryDock")
        self.setAllowedAreas(
            self.allowedAreas()
            | __import__("PyQt6.QtCore", fromlist=["Qt"]).Qt.DockWidgetArea.BottomDockWidgetArea
        )

        container = QWidget(self)
        layout = QVBoxLayout(container)

        self.tabs = QTabWidget(container)
        self.cpu_plot = self._make_plot("CPU %")
        self.ram_plot = self._make_plot("RAM %")
        self.tabs.addTab(self.cpu_plot, "CPU")
        self.tabs.addTab(self.ram_plot, "RAM")

        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(1000)
        self.tabs.addTab(self.log_view, "Logs")

        layout.addWidget(self.tabs)

        self.label = QLabel("CPU: -- | RAM: --")
        layout.addWidget(self.label)

        self.setWidget(container)

        self._curves = {
            "cpu": self.cpu_plot.plot([], [], pen="y"),
            "ram": self.ram_plot.plot([], [], pen="c"),
        }
        self._samples = {"cpu": [], "ram": []}
        self._index = 0
        self._history = 60

        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(1)
        self._worker: _Worker | None = None

        self._timer = QTimer(self)
        self._timer.setInterval(max(250, interval_ms))
        self._timer.timeout.connect(self._collect)
        self._timer.start()

    @staticmethod
    def _make_plot(title: str) -> pg.PlotWidget:
        plot = pg.PlotWidget(title=title)
        plot.setYRange(0, 100, padding=0)
        plot.showGrid(x=True, y=True, alpha=0.25)
        return plot

    def _collect(self) -> None:
        if self._worker is not None:
            return
        worker = _Worker()
        self._worker = worker
        worker.signals.updated.connect(self._on_updated)
        worker.signals.failed.connect(self._on_failed)
        self._pool.start(worker)

    @pyqtSlot(dict)
    def _on_updated(self, data: dict) -> None:
        self._worker = None
        for key in ("cpu", "ram"):
            value = float(data.get(key, 0.0))
            if math.isnan(value):
                value = 0.0
            self._samples[key].append(value)
            if len(self._samples[key]) > self._history:
                self._samples[key].pop(0)
            xs = list(range(self._index - len(self._samples[key]) + 1, self._index + 1))
            self._curves[key].setData(xs, self._samples[key])
        self._index += 1
        self.label.setText(
            f"CPU: {data.get('cpu', 0):.0f}% | "
            f"RAM: {data.get('ram', 0):.0f}% "
            f"({data.get('ram_used_gb', 0):.1f}/{data.get('ram_total_gb', 0):.1f} GB)"
        )

    @pyqtSlot(str)
    def _on_failed(self, error: str) -> None:
        self._worker = None
        logger.warning("telemetry failed: %s", error)

    def append_log(self, message: str) -> None:
        self.log_view.appendPlainText(message)

    def stop(self) -> None:
        self._timer.stop()