"""Tests for file-mediated handoff in parallel plans (Wave 80 Track C)."""

from __future__ import annotations

from formicos.core.types import ColonyTask, DelegationPlan


class TestColonyTaskExpectedOutputs:
    def test_accepts_expected_outputs(self) -> None:
        t = ColonyTask(
            task_id="t1", task="Build API", caste="coder",
            expected_outputs=["src/api.py", "tests/test_api.py"],
        )
        assert t.expected_outputs == ["src/api.py", "tests/test_api.py"]

    def test_defaults_to_empty(self) -> None:
        t = ColonyTask(task_id="t1", task="Build API", caste="coder")
        assert t.expected_outputs == []

    def test_coexists_with_target_files(self) -> None:
        t = ColonyTask(
            task_id="t1", task="Review", caste="reviewer",
            target_files=["src/main.py"],
            expected_outputs=["review_report.md"],
        )
        assert t.target_files == ["src/main.py"]
        assert t.expected_outputs == ["review_report.md"]


class TestAutoWireTargetFiles:
    """Test the auto-wiring logic that fills downstream target_files
    from upstream expected_outputs inside _spawn_parallel().

    These tests exercise the wiring logic directly on ColonyTask objects
    to avoid needing a full runtime mock.
    """

    @staticmethod
    def _auto_wire(tasks: list[ColonyTask]) -> list[ColonyTask]:
        """Reproduce the auto-wiring logic from queen_tools._spawn_parallel."""
        output_map: dict[str, list[str]] = {
            t.task_id: list(t.expected_outputs) for t in tasks if t.expected_outputs
        }
        if not output_map:
            return tasks
        result: list[ColonyTask] = []
        for t in tasks:
            if t.depends_on and not t.target_files:
                upstream_files: list[str] = []
                seen: set[str] = set()
                for dep_id in t.depends_on:
                    for f in output_map.get(dep_id, []):
                        if f not in seen:
                            upstream_files.append(f)
                            seen.add(f)
                if upstream_files:
                    t = t.model_copy(update={"target_files": upstream_files})
            result.append(t)
        return result

    def test_fills_downstream_target_files(self) -> None:
        tasks = [
            ColonyTask(
                task_id="api", task="Build API", caste="coder",
                expected_outputs=["src/api.py", "src/models.py"],
            ),
            ColonyTask(
                task_id="test", task="Write tests", caste="coder",
                depends_on=["api"],
            ),
        ]
        wired = self._auto_wire(tasks)
        assert wired[1].target_files == ["src/api.py", "src/models.py"]

    def test_preserves_explicit_target_files(self) -> None:
        tasks = [
            ColonyTask(
                task_id="api", task="Build API", caste="coder",
                expected_outputs=["src/api.py"],
            ),
            ColonyTask(
                task_id="test", task="Write tests", caste="coder",
                depends_on=["api"],
                target_files=["src/existing.py"],
            ),
        ]
        wired = self._auto_wire(tasks)
        assert wired[1].target_files == ["src/existing.py"]

    def test_deduplicates_upstream_outputs(self) -> None:
        tasks = [
            ColonyTask(
                task_id="a", task="Build A", caste="coder",
                expected_outputs=["shared.py", "utils.py"],
            ),
            ColonyTask(
                task_id="b", task="Build B", caste="coder",
                expected_outputs=["shared.py", "config.py"],
            ),
            ColonyTask(
                task_id="c", task="Integrate", caste="coder",
                depends_on=["a", "b"],
            ),
        ]
        wired = self._auto_wire(tasks)
        assert wired[2].target_files == ["shared.py", "utils.py", "config.py"]

    def test_no_wiring_without_depends_on(self) -> None:
        tasks = [
            ColonyTask(
                task_id="a", task="Build A", caste="coder",
                expected_outputs=["src/a.py"],
            ),
            ColonyTask(
                task_id="b", task="Build B", caste="coder",
            ),
        ]
        wired = self._auto_wire(tasks)
        assert wired[1].target_files == []

    def test_no_wiring_when_upstream_has_no_outputs(self) -> None:
        tasks = [
            ColonyTask(task_id="a", task="Research", caste="researcher"),
            ColonyTask(
                task_id="b", task="Build", caste="coder",
                depends_on=["a"],
            ),
        ]
        wired = self._auto_wire(tasks)
        assert wired[1].target_files == []

    def test_preserves_upstream_order(self) -> None:
        tasks = [
            ColonyTask(
                task_id="first", task="A", caste="coder",
                expected_outputs=["z.py", "a.py"],
            ),
            ColonyTask(
                task_id="second", task="B", caste="coder",
                depends_on=["first"],
            ),
        ]
        wired = self._auto_wire(tasks)
        assert wired[1].target_files == ["z.py", "a.py"]


class TestDelegationPlanWithOutputs:
    def test_plan_serializes_expected_outputs(self) -> None:
        plan = DelegationPlan(
            reasoning="test",
            tasks=[
                ColonyTask(
                    task_id="t1", task="Build", caste="coder",
                    expected_outputs=["out.py"],
                ),
            ],
            parallel_groups=[["t1"]],
        )
        dumped = plan.model_dump()
        assert dumped["tasks"][0]["expected_outputs"] == ["out.py"]
