"""Trace panel — call graph and events."""

from __future__ import annotations

from collections import OrderedDict

from PyQt6.QtCore import QObject, Qt, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QBrush, QColor, QFont, QPainter, QPen
from PyQt6.QtWidgets import (
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
    QGraphicsView,
    QLabel,
    QPlainTextEdit,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from ..shell.context import UiContext


class _TraceSignals(QObject):
    event = pyqtSignal(object)


class TracePanel(QWidget):
    def __init__(self, ctx: UiContext, parent=None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self._signals = _TraceSignals(self)
        self._signals.event.connect(self._on_event)
        self._paths: OrderedDict[str, list[tuple[str, ...]]] = OrderedDict()

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Trace — call graph and recent chain events"))

        splitter = QSplitter(Qt.Orientation.Vertical)
        self.scene = QGraphicsScene(self)
        self.graph = QGraphicsView(self.scene)
        self.graph.setRenderHints(
            QPainter.RenderHint.Antialiasing
            | QPainter.RenderHint.TextAntialiasing
        )
        self.graph.setBackgroundBrush(QBrush(QColor("#08130e")))
        splitter.addWidget(self.graph)
        self.view = QPlainTextEdit()
        self.view.setReadOnly(True)
        self.view.setMaximumBlockCount(2000)
        splitter.addWidget(self.view)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 1)
        layout.addWidget(splitter)

        if ctx.dispatcher is not None:
            ctx.dispatcher.chain.subscribe(self._signals.event.emit)

    @pyqtSlot(object)
    def _on_event(self, event) -> None:
        path = event.call_stack or (event.source,)
        if event.trace_id not in self._paths:
            self._paths[event.trace_id] = []
        self._paths.move_to_end(event.trace_id)
        while len(self._paths) > 20:
            self._paths.popitem(last=False)
        trace_paths = self._paths[event.trace_id]
        if not trace_paths or trace_paths[-1] != path:
            trace_paths.append(path)
            del trace_paths[:-200]
        self._render_graph(event.trace_id)
        preview = event.payload.get("text")
        if isinstance(preview, str) and len(preview) > 200:
            preview = preview[:200] + "…"
        if preview is None:
            preview = str(event.payload)
        line = f"[{event.trace_id[:8]}] {event.source} ({event.kind}): {preview}"
        self.view.appendPlainText(line)

    def _render_graph(self, trace_id: str) -> None:
        paths = self._paths[trace_id]
        nodes: list[str] = []
        edges: set[tuple[str, str]] = set()
        for path in paths:
            for node in path:
                if node not in nodes:
                    nodes.append(node)
            edges.update(zip(path, path[1:]))

        self.scene.clear()
        positions = {
            node: (40.0 + index * 190.0, 70.0)
            for index, node in enumerate(nodes)
        }
        pen = QPen(QColor("#56d879"), 2)
        for source, target in edges:
            x1, y1 = positions[source]
            x2, y2 = positions[target]
            self.scene.addLine(x1 + 140, y1 + 24, x2, y2 + 24, pen)
        for index, node_id in enumerate(nodes):
            x, y = positions[node_id]
            item = QGraphicsRectItem(0, 0, 140, 48)
            item.setPos(x, y)
            item.setBrush(QBrush(QColor("#142b22")))
            item.setPen(pen)
            label = QGraphicsSimpleTextItem(node_id, item)
            label.setBrush(QBrush(QColor("#e6fff0")))
            font = QFont()
            font.setBold(True)
            label.setFont(font)
            label.setPos(10, 14)
            self.scene.addItem(item)
        self.scene.setSceneRect(0, 0, max(240, len(nodes) * 190), 150)