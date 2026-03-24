"""Wave 48 cleanup: POST /api/v1/preview-colony endpoint tests.

Covers:
- Happy path returns structured preview with expected keys
- Missing task returns error
- Castes payload accepted in frontend shape
- Invalid castes returns error
- Optional target_files pass through
- fast_path flag passes through
- Route uses preview semantics (no colony dispatched)
- max_rounds clamped to [1, 50]
"""

from __future__ import annotations

from unittest.mock import MagicMock

from starlette.testclient import TestClient

from formicos.surface.routes.api import routes


def _make_client() -> TestClient:
    """Build a TestClient wired to the API routes with a minimal mock runtime."""
    from starlette.applications import Starlette

    runtime = MagicMock()
    runtime.projections = MagicMock()

    route_list = routes(
        runtime=runtime,
        settings=MagicMock(),
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


class TestPreviewColonyEndpoint:
    """Verify POST /api/v1/preview-colony returns preview metadata."""

    def test_happy_path_returns_expected_keys(self) -> None:
        client = _make_client()
        resp = client.post("/api/v1/preview-colony", json={
            "task": "Fix auth bug",
            "castes": [{"caste": "coder", "tier": "standard", "count": 1}],
            "strategy": "stigmergic",
            "max_rounds": 10,
            "budget_limit": 2.50,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["task"] == "Fix auth bug"
        assert data["strategy"] == "stigmergic"
        assert data["maxRounds"] == 10
        assert data["budgetLimit"] == 2.50
        assert data["estimatedCost"] == 2.50
        assert data["preview"] is True
        assert isinstance(data["team"], list)
        assert data["team"][0]["caste"] == "coder"
        assert isinstance(data["summary"], str)
        assert "PREVIEW" in data["summary"]

    def test_missing_task_returns_error(self) -> None:
        client = _make_client()
        resp = client.post("/api/v1/preview-colony", json={
            "castes": [{"caste": "coder"}],
        })
        assert resp.status_code != 200
        data = resp.json()
        assert "task" in data.get("message", data.get("error", "")).lower()

    def test_missing_castes_returns_error(self) -> None:
        client = _make_client()
        resp = client.post("/api/v1/preview-colony", json={
            "task": "Fix bug",
        })
        assert resp.status_code != 200

    def test_empty_castes_returns_error(self) -> None:
        client = _make_client()
        resp = client.post("/api/v1/preview-colony", json={
            "task": "Fix bug",
            "castes": [],
        })
        assert resp.status_code != 200

    def test_frontend_caste_shape_accepted(self) -> None:
        """Frontend sends {caste, tier, count} — verify this is accepted."""
        client = _make_client()
        resp = client.post("/api/v1/preview-colony", json={
            "task": "Review code",
            "castes": [
                {"caste": "coder", "tier": "standard", "count": 2},
                {"caste": "reviewer", "tier": "standard", "count": 1},
            ],
            "strategy": "stigmergic",
            "max_rounds": 8,
            "budget_limit": 3.00,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["team"]) == 2
        assert data["team"][0]["caste"] == "coder"
        assert data["team"][0]["count"] == 2
        assert data["team"][1]["caste"] == "reviewer"

    def test_target_files_pass_through(self) -> None:
        client = _make_client()
        resp = client.post("/api/v1/preview-colony", json={
            "task": "Fix tests",
            "castes": [{"caste": "coder"}],
            "target_files": ["src/app.py", "tests/test_app.py"],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["targetFiles"] == ["src/app.py", "tests/test_app.py"]

    def test_fast_path_passes_through(self) -> None:
        client = _make_client()
        resp = client.post("/api/v1/preview-colony", json={
            "task": "Quick fix",
            "castes": [{"caste": "coder", "tier": "flash"}],
            "fast_path": True,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["fastPath"] is True
        assert "fast_path" in data["summary"]

    def test_does_not_dispatch_colony(self) -> None:
        """Preview must not call any colony dispatch methods on runtime."""
        from starlette.applications import Starlette

        runtime = MagicMock()
        runtime.projections = MagicMock()

        route_list = routes(
            runtime=runtime,
            settings=MagicMock(),
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
        client = TestClient(app)

        resp = client.post("/api/v1/preview-colony", json={
            "task": "Fix bug",
            "castes": [{"caste": "coder"}],
        })
        assert resp.status_code == 200
        # Runtime should not have any colony dispatch calls
        runtime.spawn_colony.assert_not_called()
        runtime.emit_and_broadcast.assert_not_called()

    def test_max_rounds_clamped(self) -> None:
        client = _make_client()
        resp = client.post("/api/v1/preview-colony", json={
            "task": "Big task",
            "castes": [{"caste": "coder"}],
            "max_rounds": 999,
        })
        assert resp.status_code == 200
        assert resp.json()["maxRounds"] == 50

    def test_invalid_caste_tier_returns_error(self) -> None:
        client = _make_client()
        resp = client.post("/api/v1/preview-colony", json={
            "task": "Fix bug",
            "castes": [{"caste": "coder", "tier": "nonexistent"}],
        })
        assert resp.status_code != 200

    def test_default_strategy_and_rounds(self) -> None:
        """When strategy and max_rounds are omitted, defaults are used."""
        client = _make_client()
        resp = client.post("/api/v1/preview-colony", json={
            "task": "Simple task",
            "castes": [{"caste": "coder"}],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["strategy"] == "stigmergic"
        assert data["maxRounds"] == 10

    def test_invalid_json_returns_error(self) -> None:
        client = _make_client()
        resp = client.post(
            "/api/v1/preview-colony",
            content=b"not json",
            headers={"content-type": "application/json"},
        )
        assert resp.status_code != 200
