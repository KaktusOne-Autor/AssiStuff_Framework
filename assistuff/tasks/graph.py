"""Validated task DAG used by the desktop task planner."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_STEP_ID_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$")


class TaskGraphError(ValueError):
    """Raised when a planned task graph is invalid."""


@dataclass
class TaskStep:
    id: str
    description: str
    depends_on: list[str] = field(default_factory=list)
    status: str = "pending"
    result: str = ""


class TaskGraph:
    def __init__(self, goal: str, steps: list[TaskStep], *, max_steps: int) -> None:
        self.goal = goal.strip()
        self.steps = steps
        if not self.goal:
            raise TaskGraphError("task goal must not be empty")
        if not self.steps:
            raise TaskGraphError("task plan must contain at least one step")
        if len(self.steps) > max_steps:
            raise TaskGraphError(f"task plan exceeds max_steps={max_steps}")
        self._validate()

    @classmethod
    def from_plan(
        cls,
        goal: str,
        data: dict,
        *,
        max_steps: int,
    ) -> "TaskGraph":
        raw_steps = data.get("steps")
        if not isinstance(raw_steps, list):
            raise TaskGraphError("planner response must contain a steps array")
        steps: list[TaskStep] = []
        for raw in raw_steps:
            if not isinstance(raw, dict):
                raise TaskGraphError("each planned step must be an object")
            step_id = raw.get("id")
            description = raw.get("description")
            dependencies = raw.get("depends_on", [])
            if not isinstance(step_id, str) or not isinstance(description, str):
                raise TaskGraphError("each step requires string id and description")
            if not isinstance(dependencies, list) or not all(
                isinstance(item, str) for item in dependencies
            ):
                raise TaskGraphError(f"step {step_id!r} has invalid dependencies")
            steps.append(TaskStep(
                id=step_id.strip(),
                description=description.strip(),
                depends_on=list(dict.fromkeys(item.strip() for item in dependencies)),
            ))
        return cls(goal, steps, max_steps=max_steps)

    def _validate(self) -> None:
        by_id: dict[str, TaskStep] = {}
        for step in self.steps:
            if not _STEP_ID_RE.fullmatch(step.id):
                raise TaskGraphError(f"invalid task step ID: {step.id!r}")
            if not step.description:
                raise TaskGraphError(f"task step {step.id!r} has no description")
            if step.id in by_id:
                raise TaskGraphError(f"duplicate task step ID: {step.id!r}")
            by_id[step.id] = step

        for step in self.steps:
            for dependency in step.depends_on:
                if dependency not in by_id:
                    raise TaskGraphError(
                        f"task step {step.id!r} depends on unknown step {dependency!r}"
                    )
                if dependency == step.id:
                    raise TaskGraphError(f"task step {step.id!r} depends on itself")

        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(step_id: str) -> None:
            if step_id in visiting:
                raise TaskGraphError("task plan contains a dependency cycle")
            if step_id in visited:
                return
            visiting.add(step_id)
            for dependency in by_id[step_id].depends_on:
                visit(dependency)
            visiting.remove(step_id)
            visited.add(step_id)

        for step_id in by_id:
            visit(step_id)

    def ready(self) -> list[TaskStep]:
        completed = {step.id for step in self.steps if step.status == "done"}
        return [
            step for step in self.steps
            if step.status == "pending"
            and all(dependency in completed for dependency in step.depends_on)
        ]

    def pending(self) -> list[TaskStep]:
        return [step for step in self.steps if step.status == "pending"]

    def get(self, step_id: str) -> TaskStep:
        for step in self.steps:
            if step.id == step_id:
                return step
        raise KeyError(step_id)
