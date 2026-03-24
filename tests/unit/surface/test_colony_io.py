"""Tests for colony artifact read endpoints (Wave 25.5)."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from starlette.testclient import TestClient

from formicos.surface.projections import ColonyProjection
from formicos.surface.routes.colony_io import routes


def _sample_artifact(
    *,
    art_id: str = "art-col1-coder-r1-0",
    name: str = "email_validator.py",
    artifact_type: str = "code",
    mime_type: str = "text/x-python",
    content: str = "def validate(email): ...",
    source_agent_id: str = "coder-0",
    source_round: int = 1,
    source_colony_id: str = "col-1",
    created_at: str = "2026-03-17T00:00:00Z",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "id": art_id,
        "name": name,
        "artifact_type": artifact_type,
        "mime_type": mime_type,
        "content": content,
        "source_agent_id": source_agent_id,
        "source_round": source_round,
        "source_colony_id": source_colony_id,
        "created_at": created_at,
        "metadata": metadata or {},
    }


def _make_colony(
    colony_id: str = "col-1",
    artifacts: list[dict[str, Any]] | None = None,
) -> ColonyProjection:
    return ColonyProjection(
        id=colony_id,
        thread_id="main",
        workspace_id="default",
        task="test task",
        status="completed",
        artifacts=artifacts or [],
    )


def _build_client(
    projections: MagicMock,
    tmp_path: Path,
) -> TestClient:
    from starlette.applications import Starlette

    runtime = MagicMock()
    runtime.colony_manager = None
    route_list = routes(
        runtime=runtime,
        projections=projections,
        data_dir=tmp_path,
    )
    app = Starlette(routes=route_list)
    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# List artifacts
# ---------------------------------------------------------------------------


class TestListColonyArtifacts:
    def test_returns_previews(self, tmp_path: Path) -> None:
        long_content = "x" * 1000
        art = _sample_artifact(content=long_content)
        colony = _make_colony(artifacts=[art])

        proj = MagicMock()
        proj.get_colony.return_value = colony
        client = _build_client(proj, tmp_path)

        resp = client.get("/api/v1/colonies/col-1/artifacts")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["artifacts"]) == 1

        preview = data["artifacts"][0]
        assert preview["id"] == art["id"]
        assert preview["name"] == art["name"]
        assert preview["artifact_type"] == "code"
        assert preview["mime_type"] == "text/x-python"
        assert preview["source_agent_id"] == "coder-0"
        assert preview["source_round"] == 1
        # Content is truncated to 500 chars
        assert preview["content_preview"] == "x" * 500
        # Full content not exposed
        assert "content" not in preview

    def test_empty_artifacts(self, tmp_path: Path) -> None:
        colony = _make_colony(artifacts=[])
        proj = MagicMock()
        proj.get_colony.return_value = colony
        client = _build_client(proj, tmp_path)

        resp = client.get("/api/v1/colonies/col-1/artifacts")
        assert resp.status_code == 200
        assert resp.json()["artifacts"] == []

    def test_colony_not_found(self, tmp_path: Path) -> None:
        proj = MagicMock()
        proj.get_colony.return_value = None
        client = _build_client(proj, tmp_path)

        resp = client.get("/api/v1/colonies/no-such/artifacts")
        assert resp.status_code == 404

    def test_multiple_artifacts_ordered(self, tmp_path: Path) -> None:
        arts = [
            _sample_artifact(art_id=f"art-r{r}-{i}", source_round=r, name=f"out-{i}")
            for r in (1, 2) for i in (0, 1)
        ]
        colony = _make_colony(artifacts=arts)
        proj = MagicMock()
        proj.get_colony.return_value = colony
        client = _build_client(proj, tmp_path)

        resp = client.get("/api/v1/colonies/col-1/artifacts")
        ids = [a["id"] for a in resp.json()["artifacts"]]
        assert ids == ["art-r1-0", "art-r1-1", "art-r2-0", "art-r2-1"]


# ---------------------------------------------------------------------------
# Single artifact detail
# ---------------------------------------------------------------------------


class TestGetColonyArtifact:
    def test_returns_full_content(self, tmp_path: Path) -> None:
        full_content = "def validate(email):\n    return '@' in email\n"
        art = _sample_artifact(content=full_content)
        colony = _make_colony(artifacts=[art])

        proj = MagicMock()
        proj.get_colony.return_value = colony
        client = _build_client(proj, tmp_path)

        resp = client.get(f"/api/v1/colonies/col-1/artifacts/{art['id']}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["content"] == full_content
        assert data["id"] == art["id"]
        assert data["source_colony_id"] == "col-1"
        assert data["created_at"] == "2026-03-17T00:00:00Z"
        assert data["metadata"] == {}

    def test_artifact_not_found(self, tmp_path: Path) -> None:
        colony = _make_colony(artifacts=[_sample_artifact()])
        proj = MagicMock()
        proj.get_colony.return_value = colony
        client = _build_client(proj, tmp_path)

        resp = client.get("/api/v1/colonies/col-1/artifacts/no-such-id")
        assert resp.status_code == 404
        assert resp.json()["error_code"] == "ARTIFACT_NOT_FOUND"

    def test_colony_not_found(self, tmp_path: Path) -> None:
        proj = MagicMock()
        proj.get_colony.return_value = None
        client = _build_client(proj, tmp_path)

        resp = client.get("/api/v1/colonies/no-such/artifacts/art-1")
        assert resp.status_code == 404
        assert resp.json()["error_code"] == "COLONY_NOT_FOUND"

    def test_full_content_not_truncated(self, tmp_path: Path) -> None:
        """Detail endpoint returns full content even if > 500 chars."""
        big_content = "y" * 2000
        art = _sample_artifact(content=big_content)
        colony = _make_colony(artifacts=[art])

        proj = MagicMock()
        proj.get_colony.return_value = colony
        client = _build_client(proj, tmp_path)

        resp = client.get(f"/api/v1/colonies/col-1/artifacts/{art['id']}")
        assert resp.status_code == 200
        assert len(resp.json()["content"]) == 2000


# ---------------------------------------------------------------------------
# Replay safety: artifacts from ColonyCompleted survive projection rebuild
# ---------------------------------------------------------------------------


class TestArtifactReplaySafety:
    """Verify that artifacts populated via projection replay are accessible."""

    def test_replay_populated_artifacts(self, tmp_path: Path) -> None:
        """Simulate a colony whose artifacts were restored from event replay."""
        art = _sample_artifact()
        colony = _make_colony(artifacts=[art])
        # After replay, status is completed and artifacts are on the projection
        assert colony.status == "completed"
        assert len(colony.artifacts) == 1

        proj = MagicMock()
        proj.get_colony.return_value = colony
        client = _build_client(proj, tmp_path)

        # List endpoint
        resp = client.get("/api/v1/colonies/col-1/artifacts")
        assert resp.status_code == 200
        assert len(resp.json()["artifacts"]) == 1

        # Detail endpoint
        resp = client.get(f"/api/v1/colonies/col-1/artifacts/{art['id']}")
        assert resp.status_code == 200
        assert resp.json()["content"] == art["content"]
