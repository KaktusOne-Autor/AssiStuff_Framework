"""Models panel — installed packages and manifests."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import yaml
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPainter, QPixmap
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtWidgets import (
    QFileDialog,
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

from assistuff.pack.installer import list_installed

from ..shell.context import UiContext


class ModelsPanel(QWidget):
    def __init__(self, ctx: UiContext, parent=None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self._current_manifest = None

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Models & packages"))
        self.remote_notice = QLabel(
            "Remote models send prompts and manifest-authorized memory context "
            "to their configured provider. Review endpoint and privacy terms "
            "before routing requests to them."
        )
        self.remote_notice.setWordWrap(True)
        layout.addWidget(self.remote_notice)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        self.installed = QListWidget()
        left_layout.addWidget(QLabel("Installed packages"))
        left_layout.addWidget(self.installed)

        self.manifests = QListWidget()
        left_layout.addWidget(QLabel("Configured manifests"))
        left_layout.addWidget(self.manifests)

        buttons = QHBoxLayout()
        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.clicked.connect(self.reload)
        buttons.addWidget(self.refresh_button)
        buttons.addStretch()
        left_layout.addLayout(buttons)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.addWidget(QLabel("Details"))
        avatar_row = QHBoxLayout()
        self.avatar_preview = QLabel("No avatar")
        self.avatar_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.avatar_preview.setFixedSize(112, 112)
        self.avatar_preview.setStyleSheet(
            "border: 1px solid palette(mid); border-radius: 8px;"
        )
        avatar_row.addWidget(self.avatar_preview)
        avatar_buttons = QVBoxLayout()
        self.choose_avatar_button = QPushButton("Choose SVG avatar…")
        self.choose_avatar_button.clicked.connect(self._choose_avatar)
        self.clear_avatar_button = QPushButton("Clear avatar")
        self.clear_avatar_button.clicked.connect(self._clear_avatar)
        avatar_buttons.addWidget(self.choose_avatar_button)
        avatar_buttons.addWidget(self.clear_avatar_button)
        avatar_buttons.addStretch()
        avatar_row.addLayout(avatar_buttons)
        avatar_row.addStretch()
        right_layout.addLayout(avatar_row)

        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        right_layout.addWidget(self.details)

        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        layout.addWidget(splitter)

        self.installed.currentItemChanged.connect(self._show_package)
        self.manifests.currentItemChanged.connect(self._show_manifest)

        self.reload()

    def reload(self) -> None:
        self.installed.clear()
        for pkg_id, info in sorted(list_installed().items()):
            for version in sorted(info.get("versions", {})):
                entry = info["versions"][version]
                size_gb = entry.get("size_bytes", 0) / 1e9
                item = QListWidgetItem(f"{pkg_id}@{version}  ({size_gb:.2f} GB)")
                item.setData(Qt.ItemDataRole.UserRole, entry)
                self.installed.addItem(item)

        self.manifests.clear()
        has_remote_models = any(
            manifest.runtime.backend == "remote_api"
            for manifest in self.ctx.config.models.values()
        )
        self.remote_notice.setVisible(has_remote_models)
        for model_id, manifest in sorted(self.ctx.config.models.items()):
            item = QListWidgetItem(
                f"{model_id}@{manifest.version}  [{manifest.runtime.backend}]"
            )
            item.setData(Qt.ItemDataRole.UserRole, manifest)
            self.manifests.addItem(item)

    def _show_package(self, current: QListWidgetItem, _prev) -> None:
        if current is None:
            return
        entry = current.data(Qt.ItemDataRole.UserRole)
        if not entry:
            return
        self.details.setPlainText(json.dumps(entry, indent=2, ensure_ascii=False))

    def _show_manifest(self, current: QListWidgetItem, _prev) -> None:
        self._current_manifest = None
        if current is None:
            self._show_avatar(None)
            return
        manifest = current.data(Qt.ItemDataRole.UserRole)
        if manifest is None:
            self._show_avatar(None)
            return
        self._current_manifest = manifest
        try:
            data = manifest.model_dump()
        except AttributeError:
            data = {"repr": repr(manifest)}
        self.details.setPlainText(json.dumps(data, indent=2, ensure_ascii=False))
        avatar = manifest.avatar
        avatar_path = self.ctx.config.project_root / avatar if avatar else None
        self._show_avatar(avatar_path)

    def _show_avatar(self, path: Path | None) -> None:
        if path is None or not path.is_file():
            self.avatar_preview.setPixmap(QPixmap())
            self.avatar_preview.setText("No avatar")
            return
        renderer = QSvgRenderer(str(path))
        if not renderer.isValid():
            self.avatar_preview.setPixmap(QPixmap())
            self.avatar_preview.setText("Invalid SVG")
            return
        pixmap = QPixmap(96, 96)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        renderer.render(painter)
        painter.end()
        self.avatar_preview.setText("")
        self.avatar_preview.setPixmap(pixmap)

    def _choose_avatar(self) -> None:
        manifest = self._current_manifest
        if manifest is None:
            QMessageBox.information(self, "Choose model", "Select a configured model first.")
            return
        source, _ = QFileDialog.getOpenFileName(
            self,
            "Choose model avatar",
            str(Path.home()),
            "SVG images (*.svg)",
        )
        if not source:
            return
        renderer = QSvgRenderer(source)
        if not renderer.isValid():
            QMessageBox.warning(self, "Invalid avatar", "Choose a valid SVG image.")
            return

        avatar_dir = self.ctx.config.project_root / "assets" / "avatars"
        destination = avatar_dir / f"{manifest.id}.svg"
        try:
            avatar_dir.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
            manifest.avatar = destination.relative_to(
                self.ctx.config.project_root
            ).as_posix()
            self._save_manifest(manifest)
        except OSError as exc:
            QMessageBox.critical(self, "Avatar not saved", str(exc))
            return
        self._show_avatar(destination)
        self._show_manifest_details(manifest)

    def _clear_avatar(self) -> None:
        manifest = self._current_manifest
        if manifest is None:
            QMessageBox.information(self, "Choose model", "Select a configured model first.")
            return
        manifest.avatar = None
        try:
            self._save_manifest(manifest)
        except OSError as exc:
            QMessageBox.critical(self, "Avatar not cleared", str(exc))
            return
        self._show_avatar(None)
        self._show_manifest_details(manifest)

    def _save_manifest(self, manifest) -> None:
        path = self.ctx.config.project_root / "config" / "models" / f"{manifest.id}.yaml"
        payload = manifest.model_dump(exclude_none=True)
        path.write_text(
            yaml.safe_dump(payload, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )

    def _show_manifest_details(self, manifest) -> None:
        self.details.setPlainText(
            json.dumps(manifest.model_dump(), indent=2, ensure_ascii=False)
        )