"""Wave 69 Track 4: GET /workspaces/{id}/threads/{id}/plan endpoint tests."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

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
