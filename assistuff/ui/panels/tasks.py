"""Tasks panel — task graph planning and execution."""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..shell.context import UiContext
from ..widgets.task_list import TaskList


class TasksPanel(QWidget):
    def __init__(self, ctx: UiContext, parent=None) -> None:
        super().__init__(parent)
        self.ctx = ctx

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Task graph"))

        controls = QHBoxLayout()
        self.goal_input = QLineEdit()
        self.goal_input.setPlaceholderText("Опишите цель...")
        self.plan_button = QPushButton("Plan")
        self.run_button = QPushButton("Run")
        self.run_button.setEnabled(False)
        controls.addWidget(self.goal_input, 1)
        controls.addWidget(self.plan_button)
        controls.addWidget(self.run_button)
        layout.addLayout(controls)

        self.task_list = TaskList()
        layout.addWidget(self.task_list)

        self.plan_button.clicked.connect(self._on_plan)
        self.run_button.clicked.connect(self._on_run)
        self._active_plan_id: str | None = None

    def _on_plan(self) -> None:
        goal = self.goal_input.text().strip()
        if not goal:
            return
        self.task_list.clear()
        self.task_list.addItem("[planned] task graph planner not wired in this build")
        self._active_plan_id = None
        self.run_button.setEnabled(False)

    def _on_run(self) -> None:
        self.task_list.addItem("[run] task execution not wired in this build")