import unittest

from assistuff.tasks import TaskGraph, TaskGraphError


class TaskGraphTests(unittest.TestCase):
    def test_ready_steps_respect_dependencies(self) -> None:
        graph = TaskGraph.from_plan(
            "Prepare release",
            {
                "steps": [
                    {"id": "test", "description": "Run tests", "depends_on": []},
                    {
                        "id": "publish",
                        "description": "Publish package",
                        "depends_on": ["test"],
                    },
                ]
            },
            max_steps=4,
        )

        self.assertEqual([step.id for step in graph.ready()], ["test"])
        graph.get("test").status = "done"
        self.assertEqual([step.id for step in graph.ready()], ["publish"])

    def test_rejects_unknown_dependencies_and_cycles(self) -> None:
        with self.assertRaisesRegex(TaskGraphError, "unknown step"):
            TaskGraph.from_plan(
                "Plan",
                {"steps": [{
                    "id": "a",
                    "description": "A",
                    "depends_on": ["missing"],
                }]},
                max_steps=2,
            )

        with self.assertRaisesRegex(TaskGraphError, "dependency cycle"):
            TaskGraph.from_plan(
                "Plan",
                {"steps": [
                    {"id": "a", "description": "A", "depends_on": ["b"]},
                    {"id": "b", "description": "B", "depends_on": ["a"]},
                ]},
                max_steps=2,
            )

    def test_rejects_plans_over_configured_step_limit(self) -> None:
        with self.assertRaisesRegex(TaskGraphError, "max_steps=1"):
            TaskGraph.from_plan(
                "Plan",
                {"steps": [
                    {"id": "a", "description": "A", "depends_on": []},
                    {"id": "b", "description": "B", "depends_on": []},
                ]},
                max_steps=1,
            )
