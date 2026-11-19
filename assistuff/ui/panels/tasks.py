"""Tasks panel — planner-backed DAG creation and explicit execution."""

from __future__ import annotations

import asyncio
import logging

from PyQt6.QtCore import QObject, QRunnable, QThreadPool, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from assistuff.tasks import TaskGraph, TaskGraphError, TaskStep

from ..shell.context import UiContext
from ..widgets.task_list import TaskList

logger = logging.getLogger(__name__)

_PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "steps": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "description": {"type": "string"},
                    "depends_on": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
                "required": ["id", "description", "depends_on"],
            },
        }
    },
    "required": ["steps"],
}

_PLAN_PROMPT = """Break the goal into a small dependency-aware task graph.
Return only JSON matching the schema. Each step must have a stable short ID,
a concrete description, and IDs of prerequisite steps. Use no more than
{max_steps} steps. Do not claim that any step has already been completed.

Goal:
{goal}
"""


class _TaskSignals(QObject):
    planned = pyqtSignal(object)
    step_changed = pyqtSignal(object)
    finished = pyqtSignal()
    failed = pyqtSignal(str)


class _TaskWorker(QRunnable):
    def __init__(
        self,
        dispatcher,
        *,
        operation: str,
        goal: str = "",
        graph: TaskGraph | None = None,
        max_steps: int = 12,
    ) -> None:
        super().__init__()
        self.dispatcher = dispatcher
        self.operation = operation
        self.goal = goal
        self.graph = graph
        self.max_steps = max_steps
        self.signals = _TaskSignals()

    @pyqtSlot()
    def run(self) -> None:
        try:
            asyncio.run(self._run_async())
        except Exception as exc:
            logger.exception("task graph %s failed", self.operation)
            self.signals.failed.emit(str(exc))
        finally:
            self.signals.finished.emit()

    async def _run_async(self) -> None:
        if self.operation == "plan":
            prompt = _PLAN_PROMPT.format(
                max_steps=self.max_steps,
                goal=self.goal,
            )
            data = await self.dispatcher.roles.generate_json(
                "planner",
                prompt,
                schema=_PLAN_SCHEMA,
            )
            graph = TaskGraph.from_plan(
                self.goal,
                data,
                max_steps=self.max_steps,
            )
            self.signals.planned.emit(graph)
            return

        if self.operation != "run" or self.graph is None:
            raise TaskGraphError("task worker has no executable task graph")

        while self.graph.pending():
            ready = self.graph.ready()
            if not ready:
                raise TaskGraphError("no runnable tasks remain; graph is blocked")
            step = ready[0]
            step.status = "running"
            self._emit_step_changed(step)
            prior_results = [
                f"{item.id}: {item.result[:1200]}"
                for item in self.graph.steps
                if item.status == "done" and item.result
            ]
            prompt = (
                f"Overall goal: {self.graph.goal}\n\n"
                + (
                    "Completed task results:\n"
                    + "\n".join(prior_results)
                    + "\n\n"
                    if prior_results
                    else ""
                )
                + f"Current task ({step.id}):\n{step.description}"
            )
            try:
                step.result = await self.dispatcher.final_text(prompt)
            except Exception:
                step.status = "failed"
                self._emit_step_changed(step)
                raise
            step.status = "done"
            self._emit_step_changed(step)

    def _emit_step_changed(self, step: TaskStep) -> None:
        self.signals.step_changed.emit(TaskStep(
            id=step.id,
            description=step.description,
            depends_on=list(step.depends_on),
            status=step.status,
            result=step.result,
        ))


class TasksPanel(QWidget):
    def __init__(self, ctx: UiContext, parent=None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self._pool = QThreadPool(self)
        self._active_graph: TaskGraph | None = None
        self._items: dict[str, int] = {}
        self._busy = False

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Task graph"))

        controls = QHBoxLayout()
        self.goal_input = QLineEdit()
        self.goal_input.setPlaceholderText("Describe a goal…")
        self.plan_button = QPushButton("Plan")
        self.run_button = QPushButton("Run")
        self.run_button.setEnabled(False)
        controls.addWidget(self.goal_input, 1)
        controls.addWidget(self.plan_button)
        controls.addWidget(self.run_button)
        layout.addLayout(controls)

        self.status = QLabel("Plans are reviewed before running.")
        layout.addWidget(self.status)
        self.task_list = TaskList()
        self.task_list.setMaximumHeight(420)
        layout.addWidget(self.task_list)

        self.plan_button.clicked.connect(self._on_plan)
        self.run_button.clicked.connect(self._on_run)

    def _on_plan(self) -> None:
        goal = self.goal_input.text().strip()
        if not goal:
            self.status.setText("Enter a goal to plan.")
            return
        if self.ctx.dispatcher is None:
            self.status.setText("Planner unavailable: dispatcher is not initialized.")
            return
        self._active_graph = None
        self.run_button.setEnabled(False)
        self.task_list.clear()
        self._start_worker(
            _TaskWorker(
                self.ctx.dispatcher,
                operation="plan",
                goal=goal,
                max_steps=self.ctx.config.framework.tasks.max_steps,
            )
        )
        self.status.setText("Planning…")

    def _on_run(self) -> None:
        if self.ctx.dispatcher is None or self._active_graph is None:
            return
        self.run_button.setEnabled(False)
        self._start_worker(_TaskWorker(
            self.ctx.dispatcher,
            operation="run",
            graph=self._active_graph,
            max_steps=self.ctx.config.framework.tasks.max_steps,
        ))
        self.status.setText("Running planned tasks…")

    def _start_worker(self, worker: _TaskWorker) -> None:
        self._busy = True
        self.plan_button.setEnabled(False)
        worker.signals.planned.connect(self._on_plan_ready)
        worker.signals.step_changed.connect(self._on_step_changed)
        worker.signals.failed.connect(self._on_failed)
        worker.signals.finished.connect(self._on_finished)
        self._pool.start(worker)

    @pyqtSlot(object)
    def _on_plan_ready(self, graph: TaskGraph) -> None:
        self._active_graph = graph
        self._items.clear()
        self.task_list.clear()
        for step in graph.steps:
            self._items[step.id] = self.task_list.count()
            self.task_list.addItem(self._step_label(step))
        self.run_button.setEnabled(True)
        self.status.setText(
            f"Plan contains {len(graph.steps)} steps. Review it, then choose Run."
        )

    @pyqtSlot(object)
    def _on_step_changed(self, step: TaskStep) -> None:
        row = self._items.get(step.id)
        if row is None:
            return
        self.task_list.item(row).setText(self._step_label(step))

    @staticmethod
    def _step_label(step: TaskStep) -> str:
        dependencies = (
            f" (after {', '.join(step.depends_on)})"
            if step.depends_on
            else ""
        )
        output = f"\n    {step.result[:240]}" if step.result else ""
        return f"[{step.status}] {step.id}: {step.description}{dependencies}{output}"

    @pyqtSlot(str)
    def _on_failed(self, error: str) -> None:
        self.status.setText(f"Task operation failed: {error}")
        QMessageBox.warning(self, "Task operation failed", error)

    @pyqtSlot()
    def _on_finished(self) -> None:
        self._busy = False
        self.plan_button.setEnabled(True)
        graph = self._active_graph
        can_run = (
            graph is not None
            and bool(graph.pending())
            and all(step.status != "failed" for step in graph.steps)
        )
        self.run_button.setEnabled(can_run)
        if graph is not None and not graph.pending():
            self.status.setText("All planned tasks completed.")
