"""Tests for Wave 71.0 Track 7-9: thread_plan + operations_coordinator."""

from __future__ import annotations

import textwrap
from pathlib import Path
from typing import Any

import pytest

from formicos.surface.thread_plan import (
    load_all_thread_plans,
    load_thread_plan,
    parse_thread_plan,
    render_for_queen,
    thread_plan_path,
)
from formicos.surface.operations_coordinator import (
    build_operations_summary,
    render_continuity_block,
)


# ---------------------------------------------------------------------------
# thread_plan.py tests
# ---------------------------------------------------------------------------


class TestThreadPlanPath:
    def test_canonical_path(self, tmp_path: Path) -> None:
        p = thread_plan_path(str(tmp_path), "thr_abc123")
        assert p == tmp_path / ".formicos" / "plans" / "thr_abc123.md"


class TestParseThreadPlan:
    SAMPLE_PLAN = textwrap.dedent("""\
        # Thread Plan: Build the knowledge graph
        Thread: thr_abc123

        ## Steps
        - [0] [completed] Set up database schema
        - [1] [completed] Implement entity extraction
        - [2] [pending] Wire up retrieval endpoint
        - [3] [pending] Add integration tests
    """)

    def test_parse_basic(self) -> None:
        plan = parse_thread_plan(self.SAMPLE_PLAN)
        assert plan["exists"] is True
        assert plan["goal"] == "Build the knowledge graph"
        assert plan["thread_id"] == "thr_abc123"
        assert len(plan["steps"]) == 4

    def test_parse_step_structure(self) -> None:
        plan = parse_thread_plan(self.SAMPLE_PLAN)
        step0 = plan["steps"][0]
        assert step0["index"] == 0
        assert step0["status"] == "completed"
        assert step0["description"] == "Set up database schema"

    def test_summary_counts(self) -> None:
        plan = parse_thread_plan(self.SAMPLE_PLAN)
        summary = plan["summary"]
        assert summary["total"] == 4
        assert summary["completed"] == 2
        assert summary["pending"] == 2
        assert summary["failed"] == 0

    def test_empty_text(self) -> None:
        plan = parse_thread_plan("")
        assert plan["exists"] is True
        assert plan["steps"] == []
        assert plan["summary"]["total"] == 0

    def test_plan_prefix(self) -> None:
        text = "# Plan: Simple goal\n- [0] [pending] Do thing\n"
        plan = parse_thread_plan(text)
        assert plan["goal"] == "Simple goal"
        assert len(plan["steps"]) == 1


class TestLoadThreadPlan:
    def test_load_existing(self, tmp_path: Path) -> None:
        plans_dir = tmp_path / ".formicos" / "plans"
        plans_dir.mkdir(parents=True)
        (plans_dir / "thr_xyz.md").write_text(
            "# Thread Plan: Test\n- [0] [pending] Do it\n",
            encoding="utf-8",
        )
        plan = load_thread_plan(str(tmp_path), "thr_xyz")
        assert plan["exists"] is True
        assert plan["thread_id"] == "thr_xyz"
        assert len(plan["steps"]) == 1

    def test_load_missing(self, tmp_path: Path) -> None:
        plan = load_thread_plan(str(tmp_path), "thr_missing")
        assert plan["exists"] is False

    def test_load_empty_args(self) -> None:
        assert load_thread_plan("", "thr_a")["exists"] is False
        assert load_thread_plan("/tmp", "")["exists"] is False


class TestLoadAllThreadPlans:
    def test_load_multiple(self, tmp_path: Path) -> None:
        plans_dir = tmp_path / ".formicos" / "plans"
        plans_dir.mkdir(parents=True)
        (plans_dir / "thr_a.md").write_text(
            "# Thread Plan: A\n- [0] [pending] Step A\n",
            encoding="utf-8",
        )
        (plans_dir / "thr_b.md").write_text(
            "# Thread Plan: B\n- [0] [completed] Step B\n",
            encoding="utf-8",
        )
        plans = load_all_thread_plans(str(tmp_path))
        assert len(plans) == 2
        thread_ids = {p["thread_id"] for p in plans}
        assert "thr_a" in thread_ids
        assert "thr_b" in thread_ids

    def test_empty_dir(self, tmp_path: Path) -> None:
        assert load_all_thread_plans(str(tmp_path)) == []


class TestRenderForQueen:
    def test_render_basic(self) -> None:
        plan = parse_thread_plan(
            "# Thread Plan: Test\nThread: thr_abc\n"
            "- [0] [completed] Done\n- [1] [pending] Next\n",
        )
        text = render_for_queen(plan)
        assert "[Plan:thr_abc]" in text
        assert "Test" in text
        assert "1/2" in text
        # Only pending steps shown
        assert "Next" in text
        assert "Done" not in text

    def test_render_empty(self) -> None:
        assert render_for_queen({"exists": False}) == ""
        assert render_for_queen({"exists": True, "steps": []}) == ""


# ---------------------------------------------------------------------------
# operations_coordinator.py tests
# ---------------------------------------------------------------------------


def _make_workspace_dir(
    tmp_path: Path,
    *,
    project_plan: str = "",
    thread_plans: dict[str, str] | None = None,
    sessions: dict[str, str] | None = None,
) -> str:
    """Create a minimal .formicos directory structure for testing."""
    formicos = tmp_path / ".formicos"

    if project_plan:
        (formicos / "project_plan.md").parent.mkdir(parents=True, exist_ok=True)
        (formicos / "project_plan.md").write_text(project_plan, encoding="utf-8")

    if thread_plans:
        plans_dir = formicos / "plans"
        plans_dir.mkdir(parents=True, exist_ok=True)
        for tid, content in thread_plans.items():
            (plans_dir / f"{tid}.md").write_text(content, encoding="utf-8")

    if sessions:
        sessions_dir = formicos / "sessions"
        sessions_dir.mkdir(parents=True, exist_ok=True)
        for tid, content in sessions.items():
            (sessions_dir / f"{tid}.md").write_text(content, encoding="utf-8")

    return str(tmp_path)


class TestBuildOperationsSummary:
    def test_empty_data_dir(self) -> None:
        result = build_operations_summary("", "ws_1")
        assert result["workspace_id"] == "ws_1"
        assert result["pending_review_count"] == 0
        assert result["continuation_candidates"] == []

    def test_with_project_plan(self, tmp_path: Path) -> None:
        data_dir = _make_workspace_dir(
            tmp_path,
            project_plan=(
                "# Project Plan: Test\n"
                "- [0] [pending] First milestone\n"
                "- [1] [completed] Second milestone\n"
            ),
        )
        result = build_operations_summary(data_dir, "ws_1")
        assert result["active_milestone_count"] == 1

    def test_continuation_with_pending_steps(self, tmp_path: Path) -> None:
        data_dir = _make_workspace_dir(
            tmp_path,
            thread_plans={
                "thr_a": (
                    "# Thread Plan: Alpha\nThread: thr_a\n"
                    "- [0] [completed] Step 1\n"
                    "- [1] [pending] Step 2\n"
                ),
            },
            sessions={
                "thr_a": "# Session Summary: Alpha\n",
            },
        )
        result = build_operations_summary(data_dir, "ws_1")
        candidates = result["continuation_candidates"]
        assert len(candidates) >= 1
        assert candidates[0]["ready_for_autonomy"] is True

    def test_failed_steps_block_autonomy(self, tmp_path: Path) -> None:
        data_dir = _make_workspace_dir(
            tmp_path,
            thread_plans={
                "thr_b": (
                    "# Thread Plan: Beta\nThread: thr_b\n"
                    "- [0] [completed] Step 1\n"
                    "- [1] [failed] Step 2\n"
                    "- [2] [pending] Step 3\n"
                ),
            },
        )
        result = build_operations_summary(data_dir, "ws_1")
        candidates = result["continuation_candidates"]
        assert len(candidates) >= 1
        assert candidates[0]["ready_for_autonomy"] is False
        assert "failures" in candidates[0]["blocked_reason"]

    def test_sync_issue_milestone_plan_mismatch(self, tmp_path: Path) -> None:
        data_dir = _make_workspace_dir(
            tmp_path,
            project_plan=(
                "# Project Plan: Test\n"
                "- [0] [pending] Build alpha (thread thr_a)\n"
            ),
            thread_plans={
                "thr_a": (
                    "# Thread Plan: Alpha\nThread: thr_a\n"
                    "- [0] [completed] Step 1\n"
                    "- [1] [completed] Step 2\n"
                ),
            },
        )
        result = build_operations_summary(data_dir, "ws_1")
        assert len(result["sync_issues"]) >= 1
        assert result["sync_issues"][0]["type"] == "milestone_plan_mismatch"

    def test_stalled_thread_count(self, tmp_path: Path) -> None:
        data_dir = _make_workspace_dir(
            tmp_path,
            thread_plans={
                "thr_a": (
                    "# Thread Plan: A\nThread: thr_a\n"
                    "- [0] [pending] Waiting\n"
                ),
                "thr_b": (
                    "# Thread Plan: B\nThread: thr_b\n"
                    "- [0] [completed] Done\n"
                ),
            },
        )
        result = build_operations_summary(data_dir, "ws_1")
        assert result["stalled_thread_count"] == 1

    def test_no_projections(self, tmp_path: Path) -> None:
        data_dir = _make_workspace_dir(tmp_path)
        result = build_operations_summary(data_dir, "ws_1", projections=None)
        assert result["last_operator_activity_at"] is None
        assert result["operator_active"] is False


class TestRenderContinuityBlock:
    def test_empty_summary(self) -> None:
        summary: dict[str, Any] = {
            "pending_review_count": 0,
            "active_milestone_count": 0,
            "stalled_thread_count": 0,
            "idle_for_minutes": None,
            "continuation_candidates": [],
            "sync_issues": [],
            "recent_progress": [],
        }
        assert render_continuity_block(summary) == ""

    def test_with_counts(self) -> None:
        summary: dict[str, Any] = {
            "pending_review_count": 2,
            "active_milestone_count": 1,
            "stalled_thread_count": 0,
            "idle_for_minutes": 47,
            "continuation_candidates": [],
            "sync_issues": [],
            "recent_progress": [],
        }
        text = render_continuity_block(summary)
        assert "# Operational Loop Summary" in text
        assert "2 pending review" in text
        assert "operator idle 47m" in text

    def test_with_candidates(self) -> None:
        summary: dict[str, Any] = {
            "pending_review_count": 0,
            "active_milestone_count": 1,
            "stalled_thread_count": 0,
            "idle_for_minutes": None,
            "continuation_candidates": [
                {
                    "description": "Thread thr_abc: 2/3 steps done",
                    "ready_for_autonomy": True,
                    "blocked_reason": "",
                },
            ],
            "sync_issues": [],
            "recent_progress": [],
        }
        text = render_continuity_block(summary)
        assert "Continuations:" in text
        assert "[READY]" in text

    def test_with_sync_issues(self) -> None:
        summary: dict[str, Any] = {
            "pending_review_count": 0,
            "active_milestone_count": 0,
            "stalled_thread_count": 0,
            "idle_for_minutes": None,
            "continuation_candidates": [],
            "sync_issues": [
                {"description": "Milestone pending but plan complete"},
            ],
            "recent_progress": [
                {"description": "Thread thr_x: 3/3 steps completed"},
            ],
        }
        text = render_continuity_block(summary)
        assert "Sync issues:" in text
        assert "Recent:" in text
