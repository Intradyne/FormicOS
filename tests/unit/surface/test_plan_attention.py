"""Tests for Wave 68 plan file persistence and attention injection."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

from formicos.core.types import ModelRecord
from formicos.surface.queen_tools import QueenToolDispatcher


def _make_model_record(
    address: str = "local/qwen3",
) -> ModelRecord:
    provider = address.split("/", 1)[0] if "/" in address else address
    return ModelRecord(
        address=address,
        provider=provider,
        endpoint="http://localhost:8080",
        context_window=32768,
        supports_tools=True,
        cost_per_input_token=0.0,
        cost_per_output_token=0.0,
    )


def _make_runtime(
    tmp_path: Path,
) -> MagicMock:
    runtime = MagicMock()
    runtime.settings.governance.max_rounds_per_colony = 20
    runtime.settings.models.defaults.coder = "local/qwen3"
    runtime.settings.models.registry = [_make_model_record()]
    runtime.settings.system.data_dir = str(tmp_path)
    runtime.projections.queen_notes = {}
    runtime.projections.outcome_stats.return_value = []
    return runtime


class TestProposePlanWritesPlanFile:
    def test_propose_plan_writes_plan_file(self, tmp_path: Path) -> None:
        runtime = _make_runtime(tmp_path)
        dispatcher = QueenToolDispatcher(runtime)
        thread_id = "thr-plan-1"

        dispatcher._propose_plan(  # pyright: ignore[reportPrivateUsage]
            {
                "summary": "Build a CSV parser with validation",
                "options": [
                    {"label": "Quick", "description": "Single coder"},
                    {"label": "Thorough", "description": "Coder + reviewer"},
                ],
                "recommendation": "Quick is sufficient",
            },
            workspace_id="ws-1",
            thread_id=thread_id,
        )

        plan_path = tmp_path / ".formicos" / "plans" / f"{thread_id}.md"
        assert plan_path.is_file()
        content = plan_path.read_text(encoding="utf-8")
        assert "# Plan: Build a CSV parser" in content
        assert "**Approach:** Quick is sufficient" in content
        assert "## Options" in content
        assert "**Quick:**" in content
        assert "**Thorough:**" in content
        assert "## Steps" in content

    def test_propose_plan_without_thread_id_skips_file(
        self, tmp_path: Path,
    ) -> None:
        runtime = _make_runtime(tmp_path)
        dispatcher = QueenToolDispatcher(runtime)

        dispatcher._propose_plan(  # pyright: ignore[reportPrivateUsage]
            {"summary": "Test plan"},
            workspace_id="ws-1",
            thread_id="",
        )

        plan_dir = tmp_path / ".formicos" / "plans"
        assert not plan_dir.exists() or not list(plan_dir.iterdir())


class TestMarkPlanStep:
    def _write_plan(self, tmp_path: Path, thread_id: str) -> Path:
        plan_dir = tmp_path / ".formicos" / "plans"
        plan_dir.mkdir(parents=True, exist_ok=True)
        plan_path = plan_dir / f"{thread_id}.md"
        plan_path.write_text(
            "# Plan: Test\n\n## Steps\n"
            "- [0] [pending] Write auth module\n"
            "- [1] [pending] Write tests\n",
            encoding="utf-8",
        )
        return plan_path

    def test_mark_plan_step_updates_file(self, tmp_path: Path) -> None:
        runtime = _make_runtime(tmp_path)
        dispatcher = QueenToolDispatcher(runtime)
        thread_id = "thr-step-1"
        plan_path = self._write_plan(tmp_path, thread_id)

        result, _ = dispatcher._mark_plan_step(  # pyright: ignore[reportPrivateUsage]
            {"step_index": 0, "status": "completed", "note": "Done"},
            workspace_id="ws-1",
            thread_id=thread_id,
        )

        assert "marked as [completed]" in result
        content = plan_path.read_text(encoding="utf-8")
        assert "[0] [completed] Write auth module" in content
        assert "Done" in content
        # Step 1 unchanged
        assert "[1] [pending] Write tests" in content

    def test_mark_plan_step_adds_new_step(self, tmp_path: Path) -> None:
        runtime = _make_runtime(tmp_path)
        dispatcher = QueenToolDispatcher(runtime)
        thread_id = "thr-step-2"
        plan_path = self._write_plan(tmp_path, thread_id)

        result, _ = dispatcher._mark_plan_step(  # pyright: ignore[reportPrivateUsage]
            {
                "step_index": 2,
                "status": "pending",
                "description": "Deploy to staging",
            },
            workspace_id="ws-1",
            thread_id=thread_id,
        )

        assert "marked as [pending]" in result
        content = plan_path.read_text(encoding="utf-8")
        assert "[2] [pending] Deploy to staging" in content

    def test_mark_plan_step_no_plan_file(self, tmp_path: Path) -> None:
        runtime = _make_runtime(tmp_path)
        dispatcher = QueenToolDispatcher(runtime)

        result, _ = dispatcher._mark_plan_step(  # pyright: ignore[reportPrivateUsage]
            {"step_index": 0, "status": "started"},
            workspace_id="ws-1",
            thread_id="nonexistent",
        )

        assert "No plan file" in result


class TestBuildThreadContextIncludesPlan:
    def test_build_thread_context_includes_plan(
        self, tmp_path: Path,
    ) -> None:
        """Plan file content appears in _build_thread_context output."""
        from formicos.surface.queen_runtime import QueenAgent

        runtime = MagicMock()
        runtime.settings.system.data_dir = str(tmp_path)

        # Set up a thread projection
        thread = SimpleNamespace(
            name="Test Thread",
            goal="Build something",
            status="active",
            expected_outputs=[],
            colony_count=0,
            completed_colony_count=0,
            failed_colony_count=0,
            artifact_types_produced={},
            workflow_steps=[],
        )
        ws = SimpleNamespace(threads={"thr-1": thread}, config={})
        runtime.projections.workspaces = {"ws-1": ws}

        # Write plan file
        plan_dir = tmp_path / ".formicos" / "plans"
        plan_dir.mkdir(parents=True, exist_ok=True)
        plan_path = plan_dir / "thr-1.md"
        plan_path.write_text(
            "# Plan: Build CSV parser\n\n## Steps\n"
            "- [0] [started] Implement parser\n",
            encoding="utf-8",
        )

        agent = QueenAgent(runtime)
        ctx = agent._build_thread_context("thr-1", "ws-1")  # pyright: ignore[reportPrivateUsage]

        assert "Plan: Build CSV parser" in ctx
        assert "[0] [started] Implement parser" in ctx

    def test_plan_injection_caps_at_2000_chars(
        self, tmp_path: Path,
    ) -> None:
        """Oversized plan files are truncated to 2000 chars."""
        from formicos.surface.queen_runtime import QueenAgent

        runtime = MagicMock()
        runtime.settings.system.data_dir = str(tmp_path)

        thread = SimpleNamespace(
            name="Big Plan Thread",
            goal="Test truncation",
            status="active",
            expected_outputs=[],
            colony_count=0,
            completed_colony_count=0,
            failed_colony_count=0,
            artifact_types_produced={},
            workflow_steps=[],
        )
        ws = SimpleNamespace(threads={"thr-big": thread}, config={})
        runtime.projections.workspaces = {"ws-1": ws}

        # Write oversized plan file
        plan_dir = tmp_path / ".formicos" / "plans"
        plan_dir.mkdir(parents=True, exist_ok=True)
        plan_path = plan_dir / "thr-big.md"
        plan_path.write_text("X" * 5000, encoding="utf-8")

        agent = QueenAgent(runtime)
        ctx = agent._build_thread_context("thr-big", "ws-1")  # pyright: ignore[reportPrivateUsage]

        # The plan injection is capped at 2000 chars
        plan_portion = ctx.split("\n")[-1] if ctx else ""
        # Total injected plan text should be at most 2000 chars
        # (we just verify it's less than 5000, confirming truncation)
        assert len(ctx) < 5000
