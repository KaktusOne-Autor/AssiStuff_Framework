"""Visual model/skill capability graph and residency settings."""

from __future__ import annotations

import os
import tempfile
import json

import yaml
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QBrush, QColor, QFont, QPainter, QPen
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from assistuff.access import AccountError, AccountRegistry, User
from assistuff.config.schemas import (
    FrameworkConfig,
    ModelManifest,
    SkillManifest,
)

from ..shell.context import UiContext

_MODE_LABELS = {
    "Hot-plug (load on demand)": "hot_plug",
    "Selected for background (workstation)": "selected_for_background",
}


class _GraphNode(QGraphicsRectItem):
    def __init__(
        self,
        node_id: str,
        title: str,
        capabilities: list[str],
        *,
        is_skill: bool,
    ) -> None:
        super().__init__(0, 0, 270, 94)
        fill = QColor("#10241d" if is_skill else "#142b22")
        border = QColor("#43d17d" if is_skill else "#57f287")
        self.setBrush(QBrush(fill))
        self.setPen(QPen(border, 2))
        self.setData(0, node_id)
        self.setData(1, is_skill)
        self.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setToolTip(f"{node_id}\n" + "\n".join(capabilities))

        title_item = QGraphicsSimpleTextItem(title, self)
        title_item.setBrush(QBrush(QColor("#e6fff0")))
        title_font = QFont()
        title_font.setBold(True)
        title_font.setPointSize(10)
        title_item.setFont(title_font)
        title_item.setPos(12, 10)

        body = QGraphicsSimpleTextItem(
            ("Skill" if is_skill else "Model")
            + " · "
            + (", ".join(capabilities) or "no capabilities"),
            self,
        )
        body.setBrush(QBrush(QColor("#9ac8aa")))
        body.setPos(12, 42)


class _GraphView(QGraphicsView):
    def __init__(self, scene: QGraphicsScene, parent=None) -> None:
        super().__init__(scene, parent)
        self.setRenderHints(
            QPainter.RenderHint.Antialiasing
            | QPainter.RenderHint.TextAntialiasing
        )
        self.setBackgroundBrush(QBrush(QColor("#08130e")))
        self.setStyleSheet("border: 1px solid #244c34; border-radius: 8px;")


class GraphPanel(QWidget):
    def __init__(self, ctx: UiContext, parent=None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self._can_edit = ctx.authenticated and ctx.user_level >= 5
        self._nodes: dict[str, _GraphNode] = {}
        self._manifests: dict[str, ModelManifest | SkillManifest] = {}

        root = QVBoxLayout(self)
        root.addWidget(QLabel("Models & skills capability graph"))

        residency = QHBoxLayout()
        residency.addWidget(QLabel("Ollama residency"))
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(_MODE_LABELS)
        self.mode_combo.setEnabled(self._can_edit)
        current_mode = ctx.config.framework.runtime.residency.mode
        for label, mode in _MODE_LABELS.items():
            if mode == current_mode:
                self.mode_combo.setCurrentText(label)
                break
        residency.addWidget(self.mode_combo)
        residency.addWidget(QLabel("Background models"))
        self.background_models = QListWidget()
        self.background_models.setMaximumHeight(100)
        self._populate_background_models()
        self.background_models.setEnabled(
            self._can_edit and current_mode == "selected_for_background"
        )
        self.mode_combo.currentTextChanged.connect(
            lambda label: self.background_models.setEnabled(
                self._can_edit
                and _MODE_LABELS[label] == "selected_for_background"
            )
        )
        residency.addWidget(self.background_models, 1)
        self.save_runtime_button = QPushButton("Save runtime")
        self.save_runtime_button.setEnabled(self._can_edit)
        self.save_runtime_button.clicked.connect(self._save_runtime)
        residency.addWidget(self.save_runtime_button)
        root.addLayout(residency)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.scene = QGraphicsScene(self)
        self.graph = _GraphView(self.scene)
        splitter.addWidget(self.graph)

        details_panel = QWidget()
        details_layout = QVBoxLayout(details_panel)
        details_layout.addWidget(QLabel("Selected unit"))
        self.details = QLabel("Select a model or skill node.")
        self.details.setWordWrap(True)
        self.details.setAlignment(Qt.AlignmentFlag.AlignTop)
        details_layout.addWidget(self.details)
        self.edit_button = QPushButton("Edit selected node…")
        self.edit_button.setEnabled(self._can_edit)
        self.edit_button.clicked.connect(self._edit_selected)
        details_layout.addWidget(self.edit_button)
        details_layout.addStretch()
        splitter.addWidget(details_panel)
        splitter.setStretchFactor(0, 4)
        splitter.setStretchFactor(1, 1)
        root.addWidget(splitter, 1)

        self.status = QLabel("")
        if not self._can_edit:
            self.status.setText("Sign in as a level-5 administrator to edit configuration.")
        root.addWidget(self.status)
        self.scene.selectionChanged.connect(self._selection_changed)
        self._rebuild_graph()

    def _populate_background_models(self) -> None:
        settings = self.ctx.config.framework.runtime.residency
        selected = set(settings.background_models)
        self.background_models.clear()
        for model_id, manifest in sorted(self.ctx.config.models.items()):
            item = QListWidgetItem(f"{model_id} — {manifest.runtime.tag}")
            item.setData(Qt.ItemDataRole.UserRole, model_id)
            item.setFlags(
                item.flags()
                | Qt.ItemFlag.ItemIsUserCheckable
                | Qt.ItemFlag.ItemIsEnabled
            )
            checked = model_id in selected or manifest.runtime.tag in selected
            item.setCheckState(
                Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
            )
            self.background_models.addItem(item)

    def _rebuild_graph(self) -> None:
        self.scene.clear()
        self._nodes.clear()
        self._manifests = {
            **self.ctx.config.models,
            **self.ctx.config.skills,
        }

        model_ids = sorted(self.ctx.config.models)
        skill_ids = sorted(self.ctx.config.skills)
        positions: dict[str, tuple[float, float]] = {}
        for index, node_id in enumerate(model_ids):
            positions[node_id] = (30, float(30 + index * 130))
        for index, node_id in enumerate(skill_ids):
            positions[node_id] = (390, float(30 + index * 130))

        providers: dict[str, list[str]] = {}
        for node_id, manifest in self._manifests.items():
            for capability in manifest.capabilities.provides:
                providers.setdefault(capability, []).append(node_id)

        edge_pen = QPen(QColor("#45945d"), 2, Qt.PenStyle.DashLine)
        for source_id, manifest in self._manifests.items():
            source_pos = positions[source_id]
            for capability in manifest.interop.can_call:
                targets = (
                    [target for target in self._manifests if target != source_id]
                    if capability == "*"
                    else providers.get(capability, [])
                )
                for target_id in targets:
                    if target_id == source_id:
                        continue
                    target_pos = positions[target_id]
                    self.scene.addLine(
                        source_pos[0] + 270,
                        source_pos[1] + 47,
                        target_pos[0],
                        target_pos[1] + 47,
                        edge_pen,
                    )

        for node_id, manifest in self._manifests.items():
            x, y = positions[node_id]
            node = _GraphNode(
                node_id,
                f"{node_id} · {manifest.version}",
                manifest.capabilities.provides,
                is_skill=node_id in self.ctx.config.skills,
            )
            node.setPos(x, y)
            self.scene.addItem(node)
            self._nodes[node_id] = node

        max_rows = max(len(model_ids), len(skill_ids), 1)
        self.scene.setSceneRect(0, 0, 700, 60 + max_rows * 130)

    def _selection_changed(self) -> None:
        selected = self.scene.selectedItems()
        if not selected:
            self.details.setText("Select a model or skill node.")
            return
        node_id = selected[0].data(0)
        manifest = self._manifests.get(node_id)
        if manifest is None:
            return
        data = {
            "id": manifest.id,
            "kind": "skill" if node_id in self.ctx.config.skills else "model",
            "capabilities": manifest.capabilities.provides,
            "can_call": manifest.interop.can_call,
            "accepts_calls_from": manifest.interop.accepts_calls_from,
        }
        self.details.setText(json.dumps(data, indent=2, ensure_ascii=False))

    def _edit_selected(self) -> None:
        if not self._is_current_admin():
            QMessageBox.warning(
                self,
                "Administrator required",
                "Only a level-5 administrator can edit capability permissions.",
            )
            return
        selected = self.scene.selectedItems()
        if not selected:
            QMessageBox.information(self, "Select a node", "Choose a model or skill first.")
            return
        node_id = selected[0].data(0)
        manifest = self._manifests.get(node_id)
        if manifest is None:
            return

        dialog = QDialog(self)
        dialog.setWindowTitle(f"Edit {node_id}")
        form = QFormLayout(dialog)
        provides = QLineEdit(", ".join(manifest.capabilities.provides))
        can_call = QLineEdit(", ".join(manifest.interop.can_call))
        accepts = QLineEdit(", ".join(manifest.interop.accepts_calls_from))
        min_level = QLineEdit(
            str(manifest.access.min_level if manifest.access else 0)
        )
        form.addRow("Provides capabilities", provides)
        form.addRow("May call", can_call)
        form.addRow("Accepts calls from", accepts)
        form.addRow("Minimum access level (0–5)", min_level)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        try:
            level = int(min_level.text())
            data = manifest.model_dump(mode="python")
            data["capabilities"]["provides"] = self._split_values(provides.text())
            data["interop"]["can_call"] = self._split_values(can_call.text())
            data["interop"]["accepts_calls_from"] = self._split_values(accepts.text())
            access = data.get("access") or {}
            access["min_level"] = level
            data["access"] = access
            updated: ModelManifest | SkillManifest
            if node_id in self.ctx.config.models:
                updated = ModelManifest.model_validate(data)
                directory = "models"
            else:
                updated = SkillManifest.model_validate(data)
                directory = "skills"
            self._validate_links(node_id, updated)
            self._write_manifest(directory, node_id, updated)
        except (ValueError, OSError, yaml.YAMLError) as exc:
            QMessageBox.critical(self, "Could not save node", str(exc))
            return
        except Exception as exc:
            QMessageBox.critical(self, "Invalid manifest", str(exc))
            return

        if node_id in self.ctx.config.models:
            if not isinstance(updated, ModelManifest):
                raise TypeError("validated model manifest has an unexpected type")
            self.ctx.config.models[node_id] = updated
        else:
            if not isinstance(updated, SkillManifest):
                raise TypeError("validated skill manifest has an unexpected type")
            self.ctx.config.skills[node_id] = updated
        self._rebuild_graph()
        self.status.setText(
            f"Saved {node_id} manifest. Restart AssiStuff to apply changes to the bus."
        )

    @staticmethod
    def _split_values(text: str) -> list[str]:
        return [item.strip() for item in text.split(",") if item.strip()]

    def _write_manifest(
        self,
        directory: str,
        node_id: str,
        manifest: ModelManifest | SkillManifest,
    ) -> None:
        path = self.ctx.config.project_root / "config" / directory / f"{node_id}.yaml"
        payload = manifest.model_dump(mode="json", exclude_none=True)
        serialized = yaml.safe_dump(
            payload,
            sort_keys=False,
            allow_unicode=True,
        )
        temporary_path: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=path.parent,
                prefix=f".{path.name}.",
                suffix=".tmp",
                delete=False,
            ) as handle:
                temporary_path = handle.name
                handle.write(serialized)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_path, path)
        except OSError:
            if temporary_path and os.path.exists(temporary_path):
                os.unlink(temporary_path)
            raise

    def _validate_links(
        self,
        node_id: str,
        candidate: ModelManifest | SkillManifest,
    ) -> None:
        manifests = dict(self._manifests)
        manifests[node_id] = candidate
        capabilities = {
            capability
            for manifest in manifests.values()
            for capability in manifest.capabilities.provides
        }
        unit_ids = set(manifests)
        for manifest_id, manifest in manifests.items():
            invalid_caps = set(manifest.interop.can_call) - capabilities - {"*"}
            if invalid_caps:
                raise ValueError(
                    f"{manifest_id} may call capabilities that are not provided: "
                    f"{', '.join(sorted(invalid_caps))}"
                )
            invalid_callers = (
                set(manifest.interop.accepts_calls_from) - unit_ids - {"*"}
            )
            if invalid_callers:
                raise ValueError(
                    f"{manifest_id} accepts unknown callers: "
                    f"{', '.join(sorted(invalid_callers))}"
                )

    def _save_runtime(self) -> None:
        if not self._is_current_admin():
            QMessageBox.warning(
                self,
                "Administrator required",
                "Only a level-5 administrator can change model residency settings.",
            )
            return
        selected = [
            self.background_models.item(index).data(Qt.ItemDataRole.UserRole)
            for index in range(self.background_models.count())
            if self.background_models.item(index).checkState() == Qt.CheckState.Checked
        ]
        runtime = self.ctx.config.framework.runtime.residency
        startup_models = set(runtime.pinned) | set(selected)
        if len(startup_models) > runtime.max_loaded:
            QMessageBox.warning(
                self,
                "Too many background models",
                f"Pinned and selected models must total no more than "
                f"{runtime.max_loaded}; change runtime.residency.max_loaded "
                "in framework.yaml.",
            )
            return

        mode = _MODE_LABELS[self.mode_combo.currentText()]
        path = self.ctx.config.project_root / "config" / "framework.yaml"
        temporary_path: str | None = None
        try:
            original = yaml.safe_load(path.read_text(encoding="utf-8"))
            original["runtime"]["residency"]["mode"] = mode
            original["runtime"]["residency"]["background_models"] = selected
            validated = FrameworkConfig.model_validate(original)
            serialized = yaml.safe_dump(
                validated.model_dump(mode="json", exclude_none=True),
                sort_keys=False,
                allow_unicode=True,
            )
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=path.parent,
                prefix=f".{path.name}.",
                suffix=".tmp",
                delete=False,
            ) as handle:
                temporary_path = handle.name
                handle.write(serialized)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_path, path)
            self.ctx.config.framework = validated
        except (OSError, yaml.YAMLError, ValueError) as exc:
            if temporary_path and os.path.exists(temporary_path):
                os.unlink(temporary_path)
            QMessageBox.critical(self, "Runtime settings not saved", str(exc))
            return
        except Exception as exc:
            if temporary_path and os.path.exists(temporary_path):
                os.unlink(temporary_path)
            QMessageBox.critical(self, "Invalid runtime settings", str(exc))
            return
        self.status.setText(
            f"Saved residency mode: {mode.replace('_', ' ')}. "
            "Restart AssiStuff to apply it."
        )

    def _is_current_admin(self) -> bool:
        if not self._can_edit or self.ctx.account_id is None:
            return False
        account_user = User(
            level=self.ctx.user_level,
            name=self.ctx.user_name,
            account_id=self.ctx.account_id,
            authenticated=self.ctx.authenticated,
        )
        try:
            user = AccountRegistry(
                self.ctx.config.user_root / "accounts.db"
            ).resolve_session(account_user, self.ctx.profile)
        except AccountError:
            return False
        return user.level >= 5
