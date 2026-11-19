"""Memory panel — short-term, long-term, dossier."""

from __future__ import annotations

import asyncio

from PyQt6.QtCore import QObject, QRunnable, QThreadPool, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import (
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
    QMessageBox,
)

from ..shell.context import UiContext


class _MemorySearchSignals(QObject):
    results = pyqtSignal(object)
    error = pyqtSignal(str)
    finished = pyqtSignal()


class _MemorySearchWorker(QRunnable):
    def __init__(self, retriever, query: str, max_retries: int) -> None:
        super().__init__()
        self.retriever = retriever
        self.query = query
        self.max_retries = max_retries
        self.signals = _MemorySearchSignals()

    @pyqtSlot()
    def run(self) -> None:
        try:
            results = asyncio.run(
                self.retriever.search_with_retry_async(
                    self.query,
                    max_retries=self.max_retries,
                )
            )
            self.signals.results.emit(results)
        except Exception as exc:
            self.signals.error.emit(str(exc))
        finally:
            self.signals.finished.emit()


class MemoryPanel(QWidget):
    def __init__(self, ctx: UiContext, parent=None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self._pool = QThreadPool(self)
        self._searching = False

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"Memory for profile: {ctx.profile}"))

        self.tabs = QTabWidget()

        self.short_tab = self._build_short_tab()
        self.long_tab = self._build_long_tab()
        self.dossier_tab = self._build_dossier_tab()

        self.tabs.addTab(self.short_tab, "Short-term")
        self.tabs.addTab(self.long_tab, "Long-term")
        self.tabs.addTab(self.dossier_tab, "Dossier")

        layout.addWidget(self.tabs)

        self.reload()

    # ------------------------------------------------------------------

    def _build_short_tab(self) -> QWidget:
        w = QWidget()
        l = QVBoxLayout(w)
        self.short_view = QPlainTextEdit()
        self.short_view.setReadOnly(True)
        l.addWidget(self.short_view)
        return w

    def _build_long_tab(self) -> QWidget:
        w = QWidget()
        l = QVBoxLayout(w)

        row = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search memory (keywords, #tags, time)...")
        self.search_button = QPushButton("Search")
        self.search_button.clicked.connect(self._on_search)
        row.addWidget(self.search_input, 1)
        row.addWidget(self.search_button)
        l.addLayout(row)

        tag_row = QHBoxLayout()
        tag_row.addWidget(QLabel("Tags:"))
        self.tags_list = QListWidget()
        self.tags_list.setMaximumHeight(80)
        self.tags_list.setFlow(QListWidget.Flow.LeftToRight)
        self.tags_list.setWrapping(True)
        self.tags_list.itemClicked.connect(self._on_tag_clicked)
        tag_row.addWidget(self.tags_list, 1)
        self.edit_tags_button = QPushButton("Edit tags…")
        self.edit_tags_button.clicked.connect(self._edit_tags)
        tag_row.addWidget(self.edit_tags_button)
        l.addLayout(tag_row)

        self.long_results = QPlainTextEdit()
        self.long_results.setReadOnly(True)
        l.addWidget(self.long_results)
        return w

    def _build_dossier_tab(self) -> QWidget:
        w = QWidget()
        l = QVBoxLayout(w)
        self.dossier_view = QPlainTextEdit()
        self.dossier_view.setReadOnly(True)
        l.addWidget(self.dossier_view)
        return w

    # ------------------------------------------------------------------

    def reload(self) -> None:
        self._reload_short()
        self._reload_tags()
        self._reload_dossier()

    def _reload_short(self) -> None:
        if self.ctx.dispatcher is None:
            return
        try:
            messages = self.ctx.dispatcher.memory.short_term.recent_messages(limit=30)
        except Exception:
            messages = []
        self.short_view.setPlainText(
            "\n".join(f"{role}: {content}" for role, content in messages)
        )

    def _reload_tags(self) -> None:
        self.tags_list.clear()
        if self.ctx.dispatcher is None:
            return
        try:
            tags = self.ctx.dispatcher.memory.long_term.tags.all()
        except Exception:
            tags = []
        for tag in tags:
            self.tags_list.addItem(QListWidgetItem(tag))

    def _reload_dossier(self) -> None:
        if self.ctx.dispatcher is None:
            return
        try:
            dossier = self.ctx.dispatcher.memory.load_dossier()
            self.dossier_view.setPlainText(dossier.to_markdown())
        except Exception as exc:
            self.dossier_view.setPlainText(f"[error] {exc}")

    # ------------------------------------------------------------------

    def _on_search(self) -> None:
        if self.ctx.dispatcher is None or self._searching:
            return
        query = self.search_input.text().strip()
        if not query:
            return
        tag_config = self.ctx.config.framework.memory.long_term.tags
        max_retries = (
            tag_config.max_retries
            if tag_config.search_on_unknown_tag == "retry"
            else 0
        )
        self._searching = True
        self.search_button.setEnabled(False)
        self.long_results.setPlainText("Searching…")
        worker = _MemorySearchWorker(
            self.ctx.dispatcher.memory.retriever,
            query,
            max_retries,
        )
        worker.signals.results.connect(self._on_search_results)
        worker.signals.error.connect(self._on_search_error)
        worker.signals.finished.connect(self._on_search_finished)
        self._pool.start(worker)

    @pyqtSlot(object)
    def _on_search_results(self, hits) -> None:
        if not hits:
            self.long_results.setPlainText("(no results)")
            return
        self.long_results.setPlainText(
            "\n".join(
                f"{h.timestamp} {' '.join(h.tags)}: {h.text}"
                for h in hits
            )
        )

    @pyqtSlot(str)
    def _on_search_error(self, error: str) -> None:
        self.long_results.setPlainText(f"[error] {error}")

    @pyqtSlot()
    def _on_search_finished(self) -> None:
        self._searching = False
        self.search_button.setEnabled(True)

    def _on_tag_clicked(self, item: QListWidgetItem) -> None:
        self.search_input.setText(item.text())
        self._on_search()

    def _edit_tags(self) -> None:
        if self.ctx.dispatcher is None:
            QMessageBox.information(
                self,
                "Memory unavailable",
                "The memory store is not available in this session.",
            )
            return

        dialog = QDialog(self)
        dialog.setWindowTitle("Edit memory tags")
        layout = QFormLayout(dialog)
        tag_input = QLineEdit()
        tag_input.setPlaceholderText("e.g. #research")
        tags = QListWidget()
        for tag in self.ctx.dispatcher.memory.long_term.tags.all():
            tags.addItem(tag)
        layout.addRow("Current tags", tags)
        layout.addRow("Add tag", tag_input)
        add_button = QPushButton("Add")
        layout.addRow(add_button)
        add_button.clicked.connect(
            lambda: self._add_tag_to_dialog(tag_input, tags)
        )
        dialog.exec()

    def _add_tag_to_dialog(self, tag_input: QLineEdit, tags: QListWidget) -> None:
        tag = tag_input.text().strip()
        if not tag:
            return
        dispatcher = self.ctx.dispatcher
        if dispatcher is None:
            QMessageBox.information(
                self,
                "Memory unavailable",
                "The memory store is not available in this session.",
            )
            return
        try:
            registry = dispatcher.memory.long_term.tags
            added = registry.add(
                tag,
                position=self.ctx.config.framework.memory.long_term.tags.new_tag_position,
            )
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self, "Tag not saved", str(exc))
            return
        tags.clear()
        tags.addItems(registry.all())
        self._reload_tags()
        tag_input.clear()
        self.long_results.setPlainText(f"Added tag {added}.")