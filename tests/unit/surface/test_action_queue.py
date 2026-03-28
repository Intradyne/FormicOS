"""Tests for Wave 71.0 Team B: Durable action queue."""

from __future__ import annotations

import gzip
import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from starlette.testclient import TestClient

from formicos.surface.action_queue import (
    STATUS_APPROVED,
    STATUS_EXECUTED,
    STATUS_FAILED,
    STATUS_PENDING_REVIEW,
    STATUS_REJECTED,
    STATUS_SELF_REJECTED,
    append_action,
    compact_action_log,
    create_action,
    list_actions,
    queue_from_insight,
    read_actions,
    update_action,
)


WS_ID = "ws-test-1"


# ---------------------------------------------------------------------------
# Test 1: Queue appends and reads action records correctly
# ---------------------------------------------------------------------------


class TestAppendAndRead:
    def test_append_and_read(self, tmp_path: Path) -> None:
        data_dir = str(tmp_path)
        action = create_action(kind="maintenance", title="Test action")
        append_action(data_dir, WS_ID, action)

        actions = read_actions(data_dir, WS_ID)
        assert len(actions) == 1
        assert actions[0]["kind"] == "maintenance"
        assert actions[0]["title"] == "Test action"
        assert actions[0]["status"] == STATUS_PENDING_REVIEW
        assert actions[0]["action_id"].startswith("act-")

    def test_multiple_appends(self, tmp_path: Path) -> None:
        data_dir = str(tmp_path)
        for i in range(5):
            action = create_action(kind="maintenance", title=f"Action {i}")
            append_action(data_dir, WS_ID, action)

        actions = read_actions(data_dir, WS_ID)
        assert len(actions) == 5

    def test_read_empty(self, tmp_path: Path) -> None:
        actions = read_actions(str(tmp_path), WS_ID)
        assert actions == []

    def test_create_action_fields(self) -> None:
        action = create_action(
            kind="continuation",
            title="Resume work",
            detail="Thread stalled",
            source_category="stalled_thread",
            blast_radius=0.3,
            estimated_cost=0.05,
            confidence=0.8,
            requires_approval=True,
            created_by="coordinator",
        )
        assert action["kind"] == "continuation"
        assert action["blast_radius"] == 0.3
        assert action["requires_approval"] is True
        assert action["status"] == STATUS_PENDING_REVIEW


# ---------------------------------------------------------------------------
# Test 2: Status transitions
# ---------------------------------------------------------------------------


class TestStatusTransitions:
    def test_pending_to_approved_to_executed(self, tmp_path: Path) -> None:
        data_dir = str(tmp_path)
        action = create_action(kind="maintenance", title="Fix stale")
        append_action(data_dir, WS_ID, action)
        aid = action["action_id"]

        # Approve
        updated = update_action(data_dir, WS_ID, aid, {"status": STATUS_APPROVED})
        assert updated is not None
        assert updated["status"] == STATUS_APPROVED

        # Execute
        updated = update_action(data_dir, WS_ID, aid, {"status": STATUS_EXECUTED})
        assert updated is not None
        assert updated["status"] == STATUS_EXECUTED

    def test_pending_to_rejected(self, tmp_path: Path) -> None:
        data_dir = str(tmp_path)
        action = create_action(kind="maintenance", title="Risky")
        append_action(data_dir, WS_ID, action)

        updated = update_action(
            data_dir, WS_ID, action["action_id"],
            {"status": STATUS_REJECTED, "operator_reason": "Too risky"},
        )
        assert updated is not None
        assert updated["status"] == STATUS_REJECTED
        assert updated["operator_reason"] == "Too risky"

    def test_update_nonexistent(self, tmp_path: Path) -> None:
        result = update_action(str(tmp_path), WS_ID, "fake-id", {"status": "approved"})
        assert result is None


# ---------------------------------------------------------------------------
# Test 3: Approve/reject endpoints return structured JSON
# ---------------------------------------------------------------------------


class TestEndpoints:
    def _make_app(self, data_dir: str) -> Any:
        from starlette.applications import Starlette
        from starlette.requests import Request
        from starlette.responses import JSONResponse
        from starlette.routing import Route

        async def list_op_actions(request: Request) -> JSONResponse:
            status_filter = request.query_params.get("status", "")
            kind_filter = request.query_params.get("kind", "")
            limit = int(request.query_params.get("limit", "100"))
            result = list_actions(
                data_dir, request.path_params["workspace_id"],
                status=status_filter, kind=kind_filter, limit=limit,
            )
            return JSONResponse(result)

        async def approve_ep(request: Request) -> JSONResponse:
            ws = request.path_params["workspace_id"]
            aid = request.path_params["action_id"]
            updated = update_action(data_dir, ws, aid, {"status": STATUS_APPROVED})
            if updated is None:
                return JSONResponse({"error": "not found"}, status_code=404)
            return JSONResponse({"ok": True, "action_id": aid})

        async def reject_ep(request: Request) -> JSONResponse:
            ws = request.path_params["workspace_id"]
            aid = request.path_params["action_id"]
            body: dict[str, Any] = {}
            try:
                body = await request.json()
            except Exception:
                pass
            reason = body.get("reason", "")
            updated = update_action(
                data_dir, ws, aid,
                {"status": STATUS_REJECTED, "operator_reason": reason},
            )
            if updated is None:
                return JSONResponse({"error": "not found"}, status_code=404)
            return JSONResponse({"ok": True, "action_id": aid})

        return Starlette(routes=[
            Route(
                "/api/v1/workspaces/{workspace_id}/operations/actions",
                list_op_actions, methods=["GET"],
            ),
            Route(
                "/api/v1/workspaces/{workspace_id}/operations/actions/{action_id}/approve",
                approve_ep, methods=["POST"],
            ),
            Route(
                "/api/v1/workspaces/{workspace_id}/operations/actions/{action_id}/reject",
                reject_ep, methods=["POST"],
            ),
        ])

    def test_list_endpoint(self, tmp_path: Path) -> None:
        data_dir = str(tmp_path)
        for i in range(3):
            append_action(
                data_dir, WS_ID,
                create_action(kind="maintenance", title=f"A{i}"),
            )
        app = self._make_app(data_dir)
        client = TestClient(app)
        resp = client.get(f"/api/v1/workspaces/{WS_ID}/operations/actions")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 3
        assert "counts_by_status" in data
        assert "counts_by_kind" in data

    def test_list_filter_by_status(self, tmp_path: Path) -> None:
        data_dir = str(tmp_path)
        a1 = create_action(kind="maintenance", title="A1")
        a2 = create_action(kind="maintenance", title="A2")
        a2["status"] = STATUS_APPROVED
        append_action(data_dir, WS_ID, a1)
        append_action(data_dir, WS_ID, a2)

        app = self._make_app(data_dir)
        client = TestClient(app)
        resp = client.get(
            f"/api/v1/workspaces/{WS_ID}/operations/actions?status=approved",
        )
        data = resp.json()
        assert data["total"] == 1
        assert data["actions"][0]["title"] == "A2"

    def test_approve_endpoint(self, tmp_path: Path) -> None:
        data_dir = str(tmp_path)
        action = create_action(kind="maintenance", title="Approvable")
        append_action(data_dir, WS_ID, action)
        aid = action["action_id"]

        app = self._make_app(data_dir)
        client = TestClient(app)
        resp = client.post(
            f"/api/v1/workspaces/{WS_ID}/operations/actions/{aid}/approve",
        )
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

        # Verify persisted
        actions = read_actions(data_dir, WS_ID)
        assert actions[0]["status"] == STATUS_APPROVED

    def test_reject_with_reason(self, tmp_path: Path) -> None:
        data_dir = str(tmp_path)
        action = create_action(kind="maintenance", title="Rejectable")
        append_action(data_dir, WS_ID, action)
        aid = action["action_id"]

        app = self._make_app(data_dir)
        client = TestClient(app)
        resp = client.post(
            f"/api/v1/workspaces/{WS_ID}/operations/actions/{aid}/reject",
            json={"reason": "Not needed"},
        )
        assert resp.status_code == 200

        actions = read_actions(data_dir, WS_ID)
        assert actions[0]["status"] == STATUS_REJECTED
        assert actions[0]["operator_reason"] == "Not needed"

    def test_approve_nonexistent(self, tmp_path: Path) -> None:
        app = self._make_app(str(tmp_path))
        client = TestClient(app)
        resp = client.post(
            f"/api/v1/workspaces/{WS_ID}/operations/actions/fake-id/approve",
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Test 4: Compact action log archives old entries
# ---------------------------------------------------------------------------


class TestCompaction:
    def test_compact_under_threshold(self, tmp_path: Path) -> None:
        data_dir = str(tmp_path)
        for i in range(50):
            append_action(
                data_dir, WS_ID,
                create_action(kind="maintenance", title=f"A{i}"),
            )
        result = compact_action_log(data_dir, WS_ID)
        assert result is False  # below threshold

    def test_compact_above_threshold(self, tmp_path: Path) -> None:
        data_dir = str(tmp_path)
        for i in range(1100):
            append_action(
                data_dir, WS_ID,
                create_action(kind="maintenance", title=f"A{i}"),
            )

        result = compact_action_log(data_dir, WS_ID)
        assert result is True

        # Verify active file has only 500 entries
        remaining = read_actions(data_dir, WS_ID)
        assert len(remaining) == 500

        # Verify archive exists
        ops_dir = tmp_path / ".formicos" / "operations" / WS_ID
        archives = list(ops_dir.glob("actions.*.jsonl.gz"))
        assert len(archives) == 1

        # Verify archive content
        with gzip.open(archives[0], "rt", encoding="utf-8") as gz:
            archived_lines = gz.readlines()
        assert len(archived_lines) == 600


# ---------------------------------------------------------------------------
# Test 5: End-to-end operational loop
# ---------------------------------------------------------------------------


class TestOperationalLoop:
    def test_insight_queued_on_blast_radius_escalation(
        self, tmp_path: Path,
    ) -> None:
        """Proactive insight with escalate blast radius -> queued as pending_review."""
        data_dir = str(tmp_path)

        action = queue_from_insight(
            data_dir, WS_ID,
            insight_category="contradiction",
            insight_title="Contradicting entries found",
            insight_detail="Entries X and Y disagree",
            suggested_colony={
                "caste": "researcher",
                "strategy": "sequential",
                "max_rounds": 3,
                "task": "Resolve contradiction",
                "estimated_cost": 0.10,
            },
            blast_radius=0.7,
            estimated_cost=0.10,
            reason="Blast radius escalation (score=0.70)",
        )

        assert action["status"] == STATUS_PENDING_REVIEW
        assert action["kind"] == "maintenance"
        assert action["blast_radius"] == 0.7

        # Approve it
        updated = update_action(
            data_dir, WS_ID, action["action_id"],
            {"status": STATUS_APPROVED},
        )
        assert updated is not None
        assert updated["status"] == STATUS_APPROVED

        # Mark executed (simulating sweep)
        updated = update_action(
            data_dir, WS_ID, action["action_id"],
            {"status": STATUS_EXECUTED, "executed_at": "2026-03-26T12:00:00Z"},
        )
        assert updated is not None
        assert updated["status"] == STATUS_EXECUTED

        # Verify full history is durable
        actions = read_actions(data_dir, WS_ID)
        assert len(actions) == 1
        assert actions[0]["status"] == STATUS_EXECUTED


# ---------------------------------------------------------------------------
# Test 6: Self-rejected actions recorded with reason
# ---------------------------------------------------------------------------


class TestSelfRejected:
    def test_self_rejected_with_reason(self, tmp_path: Path) -> None:
        data_dir = str(tmp_path)
        action = queue_from_insight(
            data_dir, WS_ID,
            insight_category="stale_cluster",
            insight_title="Stale cluster detected",
            reason="Suggest-only autonomy level",
            self_rejected=True,
        )

        assert action["status"] == STATUS_SELF_REJECTED
        assert action["operator_reason"] == "Suggest-only autonomy level"

        # Verify persisted
        actions = read_actions(data_dir, WS_ID)
        assert len(actions) == 1
        assert actions[0]["status"] == STATUS_SELF_REJECTED

    def test_category_not_in_auto_actions_queued(self, tmp_path: Path) -> None:
        data_dir = str(tmp_path)
        action = queue_from_insight(
            data_dir, WS_ID,
            insight_category="coverage_gap",
            insight_title="Coverage gap in domain X",
            reason="Category 'coverage_gap' not in auto_actions",
            self_rejected=True,
        )
        assert action["status"] == STATUS_SELF_REJECTED
        assert "auto_actions" in action["operator_reason"]
