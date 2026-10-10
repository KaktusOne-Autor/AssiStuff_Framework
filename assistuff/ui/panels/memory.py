"""Memory panel — short-term, long-term, dossier."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
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
)

from ..shell.context import UiContext


class MemoryPanel(QWidget):
    def __init__(self, ctx: UiContext, parent=None) -> None:
        super().__init__(parent)
        self.ctx = ctx

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
        if self.ctx.dispatcher is None:
            return
        query = self.search_input.text().strip()
        if not query:
            return
        try:
            hits = self.ctx.dispatcher.memory.retriever.search(query)
        except Exception as exc:
            self.long_results.setPlainText(f"[error] {exc}")
            return
        if not hits:
            self.long_results.setPlainText("(no results)")
            return
        self.long_results.setPlainText(
            "\n".join(
                f"{h.timestamp} {' '.join(h.tags)}: {h.text}"
                for h in hits
            )
        )

    def _on_tag_clicked(self, item: QListWidgetItem) -> None:
        self.search_input.setText(item.text())
        self._on_search()