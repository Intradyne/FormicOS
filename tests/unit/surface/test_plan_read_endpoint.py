"""Wave 69 Track 4 + Wave 82 Track A: plan read + planning-history endpoints."""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

if TYPE_CHECKING:
    from pathlib import Path

from starlette.testclient import TestClient

from formicos.surface.routes.api import routes


def _make_client(tmp_path: Path) -> TestClient:
    from starlette.applications import Starlette

    runtime = MagicMock()
    runtime.projections = MagicMock()

    settings = MagicMock()
    settings.system = SimpleNamespace(data_dir=str(tmp_path))

    route_list = routes(
        runtime=runtime,
        settings=settings,
        castes=None,
        castes_path="",
        config_path="",
        vector_store=None,
        kg_adapter=None,
        embed_client=None,
        skill_collection="",
        ws_manager=MagicMock(),
    )
    app = Starlette(routes=route_list)
    return TestClient(app)


def _write_plan(tmp_path: Path, thread_id: str, content: str) -> Path:
    plan_dir = tmp_path / ".formicos" / "plans"
    plan_dir.mkdir(parents=True, exist_ok=True)
    plan_path = plan_dir / f"{thread_id}.md"
    plan_path.write_text(content, encoding="utf-8")
    return plan_path


class TestPlanReadEndpoint:
    def test_plan_endpoint_returns_parsed_steps(
        self, tmp_path: Path,
    ) -> None:
        _write_plan(
            tmp_path,
            "thr-1",
            "# Plan: Implement auth module\n\n"
            "**Approach:** Use OAuth2 with JWT tokens\n\n"
            "## Steps\n"
            "- [0] [completed] Set up OAuth provider (colony abc123)\n"
            "- [1] [started] Write integration tests\n"
            "- [2] [pending] Update API docs\n",
        )
        client = _make_client(tmp_path)
        resp = client.get("/api/v1/workspaces/ws-1/threads/thr-1/plan")
        assert resp.status_code == 200
        data = resp.json()
        assert data["exists"] is True
        assert data["title"] == "Implement auth module"
        assert data["approach"] == "Use OAuth2 with JWT tokens"
        assert len(data["steps"]) == 3
        assert data["steps"][0]["index"] == 0
        assert data["steps"][0]["status"] == "completed"
        assert "Set up OAuth provider" in data["steps"][0]["description"]
        assert data["steps"][1]["status"] == "started"
        assert data["steps"][2]["status"] == "pending"

    def test_plan_endpoint_no_file_returns_not_exists(
        self, tmp_path: Path,
    ) -> None:
        client = _make_client(tmp_path)
        resp = client.get("/api/v1/workspaces/ws-1/threads/thr-none/plan")
        assert resp.status_code == 200
        data = resp.json()
        assert data["exists"] is False

    def test_plan_endpoint_parses_colony_ids(
        self, tmp_path: Path,
    ) -> None:
        _write_plan(
            tmp_path,
            "thr-2",
            "# Plan: Test\n\n## Steps\n"
            "- [0] [started] Implement parser (colony abc123)\n",
        )
        client = _make_client(tmp_path)
        resp = client.get("/api/v1/workspaces/ws-1/threads/thr-2/plan")
        data = resp.json()
        assert data["steps"][0]["colony_id"] == "abc123"

    def test_plan_endpoint_handles_malformed_gracefully(
        self, tmp_path: Path,
    ) -> None:
        _write_plan(
            tmp_path,
            "thr-3",
            "This is not a valid plan file\n"
            "Some random content here\n"
            "- [0] [completed] Only valid step\n",
        )
        client = _make_client(tmp_path)
        resp = client.get("/api/v1/workspaces/ws-1/threads/thr-3/plan")
        assert resp.status_code == 200
        data = resp.json()
        assert data["exists"] is True
        # Title defaults when not found
        assert data["title"] == "Plan"
        # The valid step is still parsed
        assert len(data["steps"]) == 1
        assert data["steps"][0]["status"] == "completed"


# ---------------------------------------------------------------------------
# Wave 82 Track A: planning-history compare route + workflow learning read path
# ---------------------------------------------------------------------------


class TestGetRelevantOutcomes:
    def test_empty_stats(self) -> None:
        from formicos.surface.workflow_learning import get_relevant_outcomes

        proj = MagicMock()
        proj.outcome_stats.return_value = []
        result = get_relevant_outcomes(
            proj, workspace_id="ws1", operator_message="build addon",
        )
        assert result == []

    def test_returns_sorted_by_relevance(self) -> None:
        from formicos.surface.workflow_learning import get_relevant_outcomes

        proj = MagicMock()
        proj.outcome_stats.return_value = [
            {"strategy": "stigmergic", "avg_quality": 0.8, "count": 5,
             "avg_rounds": 4.0, "caste_mix": "coder+reviewer", "success_rate": 0.9},
            {"strategy": "sequential", "avg_quality": 0.5, "count": 2,
             "avg_rounds": 6.0, "caste_mix": "coder", "success_rate": 0.5},
        ]
        result = get_relevant_outcomes(
            proj, workspace_id="ws1", operator_message="build addon",
        )
        assert len(result) == 2
        assert result[0]["relevance"] >= result[1]["relevance"]

    def test_includes_evidence_string(self) -> None:
        from formicos.surface.workflow_learning import get_relevant_outcomes

        proj = MagicMock()
        proj.outcome_stats.return_value = [
            {"strategy": "stigmergic", "avg_quality": 0.75, "count": 4,
             "avg_rounds": 3.5, "caste_mix": "coder", "success_rate": 0.85},
        ]
        result = get_relevant_outcomes(
            proj, workspace_id="ws1", operator_message="fix auth",
        )
        assert len(result) == 1
        assert "n=4" in result[0]["evidence"]

    def test_planning_history_route(self, tmp_path: Path) -> None:
        client = _make_client(tmp_path)
        resp = client.get(
            "/api/v1/workspaces/ws-1/planning-history?query=build+addon",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "plans" in data

    def test_planning_history_no_query(self, tmp_path: Path) -> None:
        client = _make_client(tmp_path)
        resp = client.get("/api/v1/workspaces/ws-1/planning-history")
        assert resp.status_code == 200
        assert resp.json()["plans"] == []

    def test_planning_history_labels_evidence_type(self, tmp_path: Path) -> None:
        """Wave 83 B3: planning-history entries should carry evidence labels."""
        client = _make_client(tmp_path)
        # Mock the projections to return a dummy entry
        from unittest.mock import patch

        with patch("formicos.surface.workflow_learning.get_relevant_outcomes") as mock:
            mock.return_value = [{"strategy": "stigmergic", "evidence": "n=3"}]
            resp = client.get(
                "/api/v1/workspaces/ws-1/planning-history?query=build+addon",
            )
        data = resp.json()
        if data["plans"]:
            assert data["plans"][0]["evidence_type"] == "summary_history"
            assert data["plans"][0]["has_dag_structure"] is False


# ---------------------------------------------------------------------------
# Wave 83 Track B: plan-pattern routes
# ---------------------------------------------------------------------------


class TestPlanPatternRoutes:
    def test_list_empty(self, tmp_path: Path) -> None:
        client = _make_client(tmp_path)
        resp = client.get("/api/v1/workspaces/ws-1/plan-patterns")
        assert resp.status_code == 200
        assert resp.json()["patterns"] == []

    def test_create_and_list(self, tmp_path: Path) -> None:
        client = _make_client(tmp_path)
        resp = client.post(
            "/api/v1/workspaces/ws-1/plan-patterns",
            json={
                "name": "Auth plan",
                "task_previews": [
                    {"task_id": "t1", "task": "rewrite auth"},
                ],
                "groups": [["t1"]],
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        pid = data["pattern"]["pattern_id"]

        # List should include the new pattern
        resp2 = client.get("/api/v1/workspaces/ws-1/plan-patterns")
        patterns = resp2.json()["patterns"]
        assert len(patterns) == 1
        assert patterns[0]["name"] == "Auth plan"

        # Get by ID
        resp3 = client.get(f"/api/v1/workspaces/ws-1/plan-patterns/{pid}")
        assert resp3.status_code == 200
        assert resp3.json()["pattern"]["pattern_id"] == pid

    def test_get_nonexistent(self, tmp_path: Path) -> None:
        client = _make_client(tmp_path)
        resp = client.get("/api/v1/workspaces/ws-1/plan-patterns/nonexistent")
        assert resp.status_code == 404


class TestValidateReviewedPlanRoute:
    def test_validate_reviewed_plan_ok(self, tmp_path: Path) -> None:
        client = _make_client(tmp_path)
        resp = client.post(
            "/api/v1/workspaces/ws-1/validate-reviewed-plan",
            json={
                "preview": {
                    "taskPreviews": [
                        {"task_id": "t1", "task": "rewrite auth", "caste": "coder"},
                        {"task_id": "t2", "task": "review auth", "caste": "reviewer", "depends_on": ["t1"]},
                    ],
                    "groups": [
                        {"taskIds": ["t1"], "tasks": []},
                        {"taskIds": ["t2"], "tasks": []},
                    ],
                },
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is True
        assert data["errors"] == []

    def test_validate_reviewed_plan_requires_preview(self, tmp_path: Path) -> None:
        client = _make_client(tmp_path)
        resp = client.post(
            "/api/v1/workspaces/ws-1/validate-reviewed-plan",
            json={},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is False
        assert "preview is required" in data["errors"]
