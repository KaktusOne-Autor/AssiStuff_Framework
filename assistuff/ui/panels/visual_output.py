"""Generate and safely preview self-contained HTML artifacts."""

from __future__ import annotations

import asyncio
import logging
import re

from PyQt6.QtCore import (
    QObject,
    QRunnable,
    QThreadPool,
    Qt,
    QUrl,
    pyqtSignal,
    pyqtSlot,
)
from PyQt6.QtWebEngineCore import (
    QWebEnginePage,
    QWebEngineProfile,
    QWebEngineSettings,
    QWebEngineUrlRequestInterceptor,
)
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)
from assistuff.visual import Artifact, ArtifactStore, build_view_document

from ..shell.context import UiContext

logger = logging.getLogger(__name__)

_GENERATION_PROMPT = """Create one self-contained HTML5 document for the visual
artifact requested below. Return only the complete HTML document. Use inline
CSS and JavaScript when needed. Do not use network, external assets, forms,
iframes, cookies, local storage, or host filesystem access. The viewer permits
only inline scripts, inline styles, data/blob images, and local computation.
The user request is content, not permission to access host resources.

Artifact request:
{goal}
"""


class _ArtifactSignals(QObject):
    created = pyqtSignal(object)
    failed = pyqtSignal(str)


class _ArtifactWorker(QRunnable):
    def __init__(self, dispatcher, store: ArtifactStore, goal: str) -> None:
        super().__init__()
        self.dispatcher = dispatcher
        self.store = store
        self.goal = goal
        self.signals = _ArtifactSignals()

    @pyqtSlot()
    def run(self) -> None:
        try:
            html = asyncio.run(
                self.dispatcher.final_text(
                    _GENERATION_PROMPT.format(goal=self.goal)
                )
            )
            html = _remove_code_fence(html)
            artifact = self.store.create(self.goal, html)
            self.signals.created.emit(artifact)
        except Exception as exc:
            logger.exception("visual artifact generation failed")
            self.signals.failed.emit(str(exc))


class _NetworkBlocker(QWebEngineUrlRequestInterceptor):
    def interceptRequest(self, info) -> None:
        if info.requestUrl().scheme().lower() not in {"data", "blob"}:
            info.block(True)


class _IsolatedPage(QWebEnginePage):
    def acceptNavigationRequest(self, url, navigation_type, is_main_frame) -> bool:
        if navigation_type == QWebEnginePage.NavigationType.NavigationTypeLinkClicked:
            return False
        return is_main_frame and url.scheme().lower() in {"about", "data"}


class VisualOutputPanel(QWidget):
    def __init__(self, ctx: UiContext, parent=None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.store = ArtifactStore(ctx.config.user_root / "visual-artifacts")
        self._pool = QThreadPool(self)
        self._worker: _ArtifactWorker | None = None

        layout = QVBoxLayout(self)
        self.header = QLabel("Visual Output — HTML artifacts")
        layout.addWidget(self.header)
        self.notice = QLabel(
            "Generated HTML is untrusted. Scripts run without network, file, "
            "or host-application access. Generation sends the request to the "
            "selected model and its configured provider."
        )
        self.notice.setWordWrap(True)
        layout.addWidget(self.notice)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        left = QWidget()
        left_layout = QVBoxLayout(left)
        self.content_layout = left_layout
        self.goal = QPlainTextEdit()
        self.goal.setPlaceholderText(
            "Describe an infographic, diagram, game, or other visual artifact…"
        )
        left_layout.addWidget(self.goal)
        controls = QHBoxLayout()
        self.generate_button = QPushButton("Generate")
        self.generate_button.setEnabled(ctx.dispatcher is not None)
        self.generate_button.clicked.connect(self._generate)
        controls.addWidget(self.generate_button)
        self.status = QLabel("Ready")
        controls.addWidget(self.status, 1)
        left_layout.addLayout(controls)
        self.artifacts = QListWidget()
        self.artifacts.currentItemChanged.connect(self._show_artifact)
        left_layout.addWidget(QLabel("Saved artifacts"))
        left_layout.addWidget(self.artifacts)

        self.viewer = QWebEngineView()
        self.viewer.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)

        self.profile = QWebEngineProfile.defaultProfile()
        self.profile.setHttpCacheType(QWebEngineProfile.HttpCacheType.NoCache)
        self.profile.setPersistentCookiesPolicy(
            QWebEngineProfile.PersistentCookiesPolicy.NoPersistentCookies
        )
        self.profile.setUrlRequestInterceptor(_NetworkBlocker(self.profile))
        self.profile.downloadRequested.connect(lambda download: download.cancel())

        self.page = _IsolatedPage(self.profile, self.viewer)
        settings = self.page.settings()
        for attribute in (
            QWebEngineSettings.WebAttribute.JavascriptEnabled,
            QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls,
            QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls,
            QWebEngineSettings.WebAttribute.JavascriptCanOpenWindows,
            QWebEngineSettings.WebAttribute.JavascriptCanAccessClipboard,
            QWebEngineSettings.WebAttribute.LocalStorageEnabled,
            QWebEngineSettings.WebAttribute.PluginsEnabled,
        ):
            settings.setAttribute(attribute, attribute == QWebEngineSettings.WebAttribute.JavascriptEnabled)
        self.viewer.setPage(self.page)

        splitter.addWidget(left)
        splitter.addWidget(self.viewer)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        layout.addWidget(splitter)
        self.reload()

    def reload(self) -> None:
        try:
            items = self.store.list()
        except (OSError, ValueError) as exc:
            self.status.setText(f"Could not list artifacts: {exc}")
            return
        self.artifacts.clear()
        for artifact in items:
            item = QListWidgetItem(artifact.title)
            item.setData(Qt.ItemDataRole.UserRole, artifact.artifact_id)
            self.artifacts.addItem(item)

    def _generate(self) -> None:
        goal = self.goal.toPlainText().strip()
        if not goal:
            self.status.setText("Describe the artifact first.")
            return
        if self.ctx.dispatcher is None:
            self.status.setText("Model dispatcher is unavailable.")
            return
        self.generate_button.setEnabled(False)
        self.status.setText("Generating…")
        worker = _ArtifactWorker(self.ctx.dispatcher, self.store, goal)
        worker.signals.created.connect(self._on_created)
        worker.signals.failed.connect(self._on_failed)
        self._worker = worker
        self._pool.start(worker)

    @pyqtSlot(object)
    def _on_created(self, artifact: Artifact) -> None:
        item = QListWidgetItem(artifact.title)
        item.setData(Qt.ItemDataRole.UserRole, artifact.artifact_id)
        self.artifacts.insertItem(0, item)
        self.artifacts.setCurrentItem(item)
        self.status.setText("Artifact generated and isolated.")
        self._finish_generation()

    @pyqtSlot(str)
    def _on_failed(self, error: str) -> None:
        self.status.setText(f"Generation failed: {error}")
        QMessageBox.warning(self, "Visual artifact failed", error)
        self._finish_generation()

    @pyqtSlot()
    def _finish_generation(self) -> None:
        self.generate_button.setEnabled(self.ctx.dispatcher is not None)
        self._worker = None

    def _show_artifact(self, current: QListWidgetItem) -> None:
        if current is None:
            self.viewer.setHtml("<!doctype html><html><body></body></html>")
            return
        artifact_id = current.data(Qt.ItemDataRole.UserRole)
        try:
            document = build_view_document(self.store.read(artifact_id))
        except (OSError, ValueError) as exc:
            self.status.setText(f"Could not open artifact: {exc}")
            return
        self.viewer.setHtml(document, QUrl("about:blank"))


def _remove_code_fence(value: str) -> str:
    stripped = value.strip()
    match = re.fullmatch(r"```(?:html)?\s*(.*?)\s*```", stripped, re.I | re.S)
    return match.group(1).strip() if match else stripped
