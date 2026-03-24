from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

from starlette.applications import Starlette
from starlette.testclient import TestClient

from formicos.surface.routes.a2a import routes as a2a_routes


def _make_app(runtime: object, projections: object) -> Starlette:
    app = Starlette(routes=a2a_routes(runtime=runtime, projections=projections))
    app.state.ws_manager = SimpleNamespace(
        subscribe_colony=AsyncMock(),
        unsubscribe_colony=lambda *_args, **_kwargs: None,
    )
    return app


def test_create_task_returns_immediately_and_schedules_background_start(
    monkeypatch,
) -> None:
    scheduled: list[object] = []

    def _fake_create_task(coro: object) -> object:
        scheduled.append(coro)
        close = getattr(coro, "close", None)
        if callable(close):
            close()
        return SimpleNamespace()

    colony_manager = SimpleNamespace(start_colony=AsyncMock())
    runtime = SimpleNamespace(
        colony_manager=colony_manager,
        create_thread=AsyncMock(),
        spawn_colony=AsyncMock(return_value="colony-a2a-1"),
    )
    projections = SimpleNamespace(
        workspaces={"default": SimpleNamespace(
            threads={}, budget_limit=0, budget=SimpleNamespace(total_cost=0),
        )},
        workspace_colonies=lambda _workspace_id: [],
        get_colony=lambda _task_id: None,
        templates={},
    )

    monkeypatch.setattr("formicos.surface.routes.a2a.load_all_templates", AsyncMock(return_value=[]))
    monkeypatch.setattr("formicos.surface.routes.a2a.asyncio.create_task", _fake_create_task)

    client = TestClient(_make_app(runtime, projections))
    response = client.post("/a2a/tasks", json={"description": "write code review helper"})

    assert response.status_code == 201
    body = response.json()
    assert body["task_id"] == "colony-a2a-1"
    assert body["status"] == "running"
    assert body["team"][0]["tier"] == "standard"
    assert "selection" in body
    assert body["selection"]["source"] == "classifier"
    assert "stream_url" not in body
    runtime.create_thread.assert_awaited_once()
    runtime.spawn_colony.assert_awaited_once()
    assert len(scheduled) == 1


def test_list_tasks_rejects_invalid_limit(monkeypatch) -> None:
    runtime = SimpleNamespace(
        colony_manager=SimpleNamespace(start_colony=AsyncMock()),
        create_thread=AsyncMock(),
        spawn_colony=AsyncMock(return_value="colony-a2a-1"),
    )
    projections = SimpleNamespace(
        workspaces={"default": SimpleNamespace(threads={})},
        workspace_colonies=lambda _workspace_id: [],
        get_colony=lambda _task_id: None,
    )
    monkeypatch.setattr("formicos.surface.routes.a2a.load_all_templates", AsyncMock(return_value=[]))

    client = TestClient(_make_app(runtime, projections))
    response = client.get("/a2a/tasks?limit=abc")

    assert response.status_code == 400
    assert response.json()["error_code"] == "LIMIT_INVALID"


def test_get_task_result_returns_transcript_payload(monkeypatch) -> None:
    runtime = SimpleNamespace(
        colony_manager=SimpleNamespace(start_colony=AsyncMock()),
        create_thread=AsyncMock(),
        spawn_colony=AsyncMock(return_value="colony-a2a-1"),
        kill_colony=AsyncMock(),
    )
    colony = SimpleNamespace(
        id="colony-a2a-1",
        status="completed",
        quality_score=0.82,
        skills_extracted=2,
        cost=0.0045,
    )
    projections = SimpleNamespace(
        workspaces={"default": SimpleNamespace(threads={})},
        workspace_colonies=lambda _workspace_id: [],
        get_colony=lambda _task_id: colony,
    )
    monkeypatch.setattr(
        "formicos.surface.routes.a2a.build_transcript",
        lambda _colony: {"final_output": "done", "rounds_completed": 3},
    )

    client = TestClient(_make_app(runtime, projections))
    response = client.get("/a2a/tasks/colony-a2a-1/result")

    assert response.status_code == 200
    assert response.json() == {
        "task_id": "colony-a2a-1",
        "status": "completed",
        "output": "done",
        "transcript": {"final_output": "done", "rounds_completed": 3},
        "quality_score": 0.82,
        "skills_extracted": 2,
        "cost": 0.0045,
    }


def test_attach_terminal_task_emits_snapshot_and_finish(monkeypatch) -> None:
    runtime = SimpleNamespace(
        colony_manager=SimpleNamespace(start_colony=AsyncMock()),
        create_thread=AsyncMock(),
        spawn_colony=AsyncMock(return_value="colony-a2a-1"),
        kill_colony=AsyncMock(),
    )
    colony = SimpleNamespace(
        id="colony-a2a-1",
        status="completed",
        workspace_id="default",
        thread_id="a2a-write-code",
        quality_score=0.82,
        skills_extracted=2,
        cost=0.0045,
    )
    projections = SimpleNamespace(
        workspaces={"default": SimpleNamespace(threads={})},
        workspace_colonies=lambda _workspace_id: [],
        get_colony=lambda _task_id: colony,
    )
    monkeypatch.setattr(
        "formicos.surface.transcript.build_transcript",
        lambda _colony: {"colony_id": "colony-a2a-1", "status": "completed"},
    )

    client = TestClient(_make_app(runtime, projections))
    response = client.get("/a2a/tasks/colony-a2a-1/events")

    assert response.status_code == 200
    assert "RUN_STARTED" in response.text
    assert "STATE_SNAPSHOT" in response.text
    assert "RUN_FINISHED" in response.text
