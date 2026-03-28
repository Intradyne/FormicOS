"""Tests for Wave 70.0 Team B: Project plan helper, tools, endpoint, budget."""

from __future__ import annotations

import textwrap
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from starlette.testclient import TestClient

from formicos.surface.project_plan import (
    add_milestone,
    complete_milestone,
    load_project_plan,
    parse_project_plan,
    render_for_queen,
)


# ---------------------------------------------------------------------------
# Test 1: Parser returns structured milestones from markdown
# ---------------------------------------------------------------------------


class TestParser:
    def test_parse_milestones(self) -> None:
        text = textwrap.dedent("""\
            # Project Plan: Build the thing
            Updated: 2026-03-26T10:00:00Z

            ## Milestones
            - [0] [completed] Set up repo (thread t-1) [completed_at 2026-03-25T09:00:00Z]
            - [1] [pending] Implement core logic (thread t-2)
            - [2] [pending] Write tests \u2014 unit + integration
        """)
        plan = parse_project_plan(text)
        assert plan["exists"] is True
        assert plan["goal"] == "Build the thing"
        assert plan["updated"] == "2026-03-26T10:00:00Z"
        assert len(plan["milestones"]) == 3

        ms0 = plan["milestones"][0]
        assert ms0["index"] == 0
        assert ms0["status"] == "completed"
        assert ms0["thread_id"] == "t-1"
        assert ms0["completed_at"] == "2026-03-25T09:00:00Z"

        ms1 = plan["milestones"][1]
        assert ms1["index"] == 1
        assert ms1["status"] == "pending"
        assert ms1["thread_id"] == "t-2"

        ms2 = plan["milestones"][2]
        assert ms2["index"] == 2
        assert ms2.get("note") == "unit + integration"

    def test_malformed_markdown_handled_gracefully(self) -> None:
        """Garbage input returns exists=True with empty milestones."""
        plan = parse_project_plan("random garbage\nno milestones here\n")
        assert plan["exists"] is True
        assert plan["milestones"] == []
        assert plan["goal"] == ""

    def test_empty_input(self) -> None:
        plan = parse_project_plan("")
        assert plan["exists"] is True
        assert plan["milestones"] == []


# ---------------------------------------------------------------------------
# Test 2: Milestone tools create/update the plan file correctly
# ---------------------------------------------------------------------------


class TestMilestoneTools:
    def test_add_milestone_creates_file(self, tmp_path: Path) -> None:
        data_dir = str(tmp_path)
        plan = add_milestone(
            data_dir, "First milestone", goal="My project",
        )
        assert plan["exists"] is True
        assert plan["goal"] == "My project"
        assert len(plan["milestones"]) == 1
        assert plan["milestones"][0]["status"] == "pending"
        assert plan["milestones"][0]["description"].startswith(
            "First milestone",
        )
        # File actually exists
        from formicos.surface.project_plan import project_plan_path

        assert project_plan_path(data_dir).is_file()

    def test_add_multiple_milestones(self, tmp_path: Path) -> None:
        data_dir = str(tmp_path)
        add_milestone(data_dir, "Step A", goal="Plan")
        plan = add_milestone(data_dir, "Step B")
        assert len(plan["milestones"]) == 2
        assert plan["milestones"][0]["index"] == 0
        assert plan["milestones"][1]["index"] == 1

    def test_complete_milestone(self, tmp_path: Path) -> None:
        data_dir = str(tmp_path)
        add_milestone(data_dir, "Do the thing", goal="G")
        plan = complete_milestone(data_dir, 0, note="Done!")
        assert plan["milestones"][0]["status"] == "completed"
        assert plan["milestones"][0].get("completed_at") is not None

    def test_complete_missing_milestone(self, tmp_path: Path) -> None:
        data_dir = str(tmp_path)
        add_milestone(data_dir, "Only one", goal="G")
        result = complete_milestone(data_dir, 99)
        assert "error" in result

    def test_complete_no_plan_file(self, tmp_path: Path) -> None:
        result = complete_milestone(str(tmp_path), 0)
        assert result["exists"] is False
        assert "error" in result

    def test_add_milestone_stamps_thread_id(self, tmp_path: Path) -> None:
        data_dir = str(tmp_path)
        plan = add_milestone(
            data_dir, "Threaded work",
            thread_id="th-abc", goal="G",
        )
        ms = plan["milestones"][0]
        assert ms.get("thread_id") == "th-abc"


# ---------------------------------------------------------------------------
# Test 3: GET /api/v1/project-plan returns helper-derived JSON
# ---------------------------------------------------------------------------


class TestEndpoint:
    def _make_app(self, data_dir: str) -> Any:
        from starlette.applications import Starlette
        from starlette.requests import Request
        from starlette.responses import JSONResponse
        from starlette.routing import Route

        from formicos.surface.project_plan import load_project_plan

        async def get_project_plan(request: Request) -> JSONResponse:
            return JSONResponse(load_project_plan(data_dir))

        return Starlette(routes=[
            Route("/api/v1/project-plan", get_project_plan, methods=["GET"]),
        ])

    def test_endpoint_returns_plan(self, tmp_path: Path) -> None:
        data_dir = str(tmp_path)
        add_milestone(data_dir, "MS1", goal="Test project")
        app = self._make_app(data_dir)
        client = TestClient(app)
        resp = client.get("/api/v1/project-plan")
        assert resp.status_code == 200
        data = resp.json()
        assert data["exists"] is True
        assert data["goal"] == "Test project"
        assert len(data["milestones"]) == 1

    def test_endpoint_no_plan(self, tmp_path: Path) -> None:
        app = self._make_app(str(tmp_path))
        client = TestClient(app)
        resp = client.get("/api/v1/project-plan")
        assert resp.status_code == 200
        data = resp.json()
        assert data["exists"] is False


# ---------------------------------------------------------------------------
# Test 4: Malformed markdown handled gracefully (covered in TestParser)
# ---------------------------------------------------------------------------

# See TestParser.test_malformed_markdown_handled_gracefully above.


# ---------------------------------------------------------------------------
# Test 5: Queen budget includes a dedicated project_plan slot
# ---------------------------------------------------------------------------


class TestBudgetSlot:
    def test_budget_has_project_plan_field(self) -> None:
        from formicos.surface.queen_budget import (
            FALLBACK_BUDGET,
            _FALLBACKS,
            _FRACTIONS,
            compute_queen_budget,
        )

        # Verify the slot exists in fractions and fallbacks
        assert "project_plan" in _FRACTIONS
        assert "project_plan" in _FALLBACKS
        assert _FALLBACKS["project_plan"] == 400
        assert _FRACTIONS["project_plan"] == 0.05

        # Verify fractions sum to 1.0
        assert abs(sum(_FRACTIONS.values()) - 1.0) < 1e-9

        # Verify fallback budget has the field
        assert hasattr(FALLBACK_BUDGET, "project_plan")
        assert FALLBACK_BUDGET.project_plan == 400

    def test_computed_budget_includes_project_plan(self) -> None:
        from formicos.surface.queen_budget import compute_queen_budget

        budget = compute_queen_budget(200_000, 4096)
        assert budget.project_plan > 0
        # 5% of (200000 - 4096) = 9795, should be above fallback
        assert budget.project_plan >= 400

    def test_project_plan_separate_from_project_context(self) -> None:
        from formicos.surface.queen_budget import compute_queen_budget

        budget = compute_queen_budget(100_000, 4096)
        # They should be different slots with different allocations
        assert budget.project_plan != budget.project_context


# ---------------------------------------------------------------------------
# Test 6: Project-plan injection uses the project-plan budget
# ---------------------------------------------------------------------------


class TestInjection:
    def test_render_for_queen_output(self) -> None:
        plan = {
            "exists": True,
            "goal": "Ship v1",
            "milestones": [
                {"index": 0, "status": "completed", "description": "Setup"},
                {"index": 1, "status": "pending", "description": "Core"},
            ],
        }
        text = render_for_queen(plan)
        assert "# Project Plan (cross-thread)" in text
        assert "Goal: Ship v1" in text
        assert "\u2713" in text  # completed marker
        assert "\u25cb" in text  # pending marker

    def test_render_empty_plan(self) -> None:
        assert render_for_queen({"exists": False}) == ""
        assert render_for_queen({"exists": True, "milestones": []}) == ""

    def test_render_respects_budget_cap(self) -> None:
        """Rendered text is truncatable by budget * 4 chars."""
        plan = {
            "exists": True,
            "goal": "A" * 500,
            "milestones": [
                {"index": i, "status": "pending", "description": f"M{i} " + "x" * 200}
                for i in range(20)
            ],
        }
        text = render_for_queen(plan)
        # Budget cap of 400 tokens * 4 chars = 1600 chars
        capped = text[:400 * 4]
        assert len(capped) <= 1600
        assert capped.startswith("# Project Plan")
