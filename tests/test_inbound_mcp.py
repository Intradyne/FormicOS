"""
Tests for FormicOS Inbound MCP Memory Server.

Covers:
1. Session file reading (parse context.json, extract colony scope, handle missing)
2. Stigmergy resource (read_resource returns topology JSON, unknown colony)
3. Qdrant resource (scroll latest, handle Qdrant down)
4. query_formic_memory tool (formatted results, empty results, top_k)
5. get_colony_failure_history tool (extract failures, last 3, no failures)
"""

from __future__ import annotations

import json
import time

import httpx
import pytest

from src.mcp.inbound_memory_server import (
    extract_colony_scope,
    extract_failure_history,
    read_session_state,
    _qdrant_scroll_latest,
    _qdrant_search,
)


# ── Fixtures ──────────────────────────────────────────────────────────────


def _make_context(
    colony_id: str = "alpha",
    task: str = "Build a web app",
    status: str = "completed",
    round_num: int = 3,
    agents: list | None = None,
    decisions: list | None = None,
    tkg: list | None = None,
) -> dict:
    """Create a realistic context.json dict."""
    agents = agents or [
        {"id": "coder_01", "caste": "coder"},
        {"id": "reviewer_01", "caste": "reviewer"},
    ]
    return {
        "schema_version": "0.6.0",
        "colony": {
            "colony_id": colony_id,
            "task": task,
            "status": status,
            "round": round_num,
            "topology": {
                "round": round_num,
                "edges": [{"from": "coder_01", "to": "reviewer_01"}],
                "execution_order": [a["id"] for a in agents],
                "density": 0.5,
                "nodes": agents,
            },
            "topology_history": [
                {
                    "round": i,
                    "edges": [],
                    "execution_order": [a["id"] for a in agents],
                    "density": 0.0,
                    "nodes": agents,
                }
                for i in range(round_num + 1)
            ],
            "checkpoint": {
                "round_history": [
                    {
                        "round": i,
                        "goal": f"Goal {i}",
                        "summary": f"Round {i} summary",
                    }
                    for i in range(round_num + 1)
                ],
            },
        },
        "knowledge": {},
        "mcp": {},
        "project": {},
        "supercolony": {},
        "system": {},
        "_episodes": [],
        "_epoch_summaries": [],
        "_tkg": tkg or [],
        "_decisions": decisions or [],
        "_file_locks": {},
    }


def _write_session(tmp_path, session_name: str, ctx: dict):
    """Write a context.json file into a session dir."""
    d = tmp_path / session_name
    d.mkdir(parents=True, exist_ok=True)
    (d / "context.json").write_text(json.dumps(ctx), encoding="utf-8")
    return d


# ── 1. Session File Reading ──────────────────────────────────────────────


def test_read_session_state_finds_colony(tmp_path):
    """read_session_state returns correct context for matching colony_id."""
    ctx = _make_context(colony_id="alpha")
    _write_session(tmp_path, "sess_001", ctx)

    result = read_session_state(tmp_path, "alpha")
    assert result is not None
    assert result["colony"]["colony_id"] == "alpha"


def test_read_session_state_returns_none_for_unknown(tmp_path):
    """read_session_state returns None for non-existent colony_id."""
    ctx = _make_context(colony_id="alpha")
    _write_session(tmp_path, "sess_001", ctx)

    result = read_session_state(tmp_path, "nonexistent")
    assert result is None


def test_read_session_state_missing_dir():
    """read_session_state returns None when session dir doesn't exist."""
    from pathlib import Path
    result = read_session_state(Path("/nonexistent/path"), "alpha")
    assert result is None


def test_read_session_state_skips_invalid_json(tmp_path):
    """read_session_state skips files with invalid JSON."""
    d = tmp_path / "broken_session"
    d.mkdir()
    (d / "context.json").write_text("{invalid json", encoding="utf-8")

    # Also add a valid session
    ctx = _make_context(colony_id="beta")
    _write_session(tmp_path, "good_session", ctx)

    result = read_session_state(tmp_path, "beta")
    assert result is not None
    assert result["colony"]["colony_id"] == "beta"


def test_read_session_state_skips_dirs_without_context(tmp_path):
    """Session dirs without context.json are skipped."""
    (tmp_path / "empty_dir").mkdir()
    result = read_session_state(tmp_path, "anything")
    assert result is None


def test_extract_colony_scope():
    """extract_colony_scope returns expected fields."""
    ctx = _make_context(colony_id="alpha", task="Build app", round_num=2)
    scope = extract_colony_scope(ctx)

    assert scope["colony_id"] == "alpha"
    assert scope["task"] == "Build app"
    assert scope["round"] == 2
    assert scope["topology"] is not None
    assert len(scope["topology_history"]) == 3  # rounds 0, 1, 2
    assert len(scope["round_history"]) == 3
    assert scope["agents"] == ["coder_01", "reviewer_01"]


def test_extract_colony_scope_empty():
    """extract_colony_scope handles missing colony gracefully."""
    scope = extract_colony_scope({})
    assert scope["colony_id"] is None
    assert scope["agents"] == []


# ── 2. Stigmergy Resource ────────────────────────────────────────────────


def test_stigmergy_resource_returns_topology(tmp_path):
    """Stigmergy resource returns JSON with topology history."""
    ctx = _make_context(colony_id="gamma", round_num=5)
    _write_session(tmp_path, "sess_gamma", ctx)

    data = read_session_state(tmp_path, "gamma")
    scope = extract_colony_scope(data)

    assert scope["colony_id"] == "gamma"
    assert len(scope["topology_history"]) == 6  # rounds 0-5
    assert scope["topology"]["round"] == 5


def test_stigmergy_resource_unknown_colony(tmp_path):
    """Requesting an unknown colony returns None."""
    ctx = _make_context(colony_id="delta")
    _write_session(tmp_path, "sess_delta", ctx)

    result = read_session_state(tmp_path, "unknown")
    assert result is None


# ── 3. Qdrant Resource ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_qdrant_scroll_latest_success(monkeypatch):
    """_qdrant_scroll_latest returns formatted entries on success."""
    mock_response = httpx.Response(
        200,
        json={
            "result": {
                "points": [
                    {
                        "id": 1,
                        "payload": {
                            "content": "Memory entry 1",
                            "source": "colony_a",
                            "timestamp": 1700000000.0,
                        },
                    },
                    {
                        "id": 2,
                        "payload": {
                            "text": "Memory entry 2",
                            "source": "colony_b",
                        },
                    },
                ],
            },
        },
    )

    async def mock_post(self, url, **kwargs):
        return mock_response

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    result = await _qdrant_scroll_latest("localhost", 6333, "swarm_memory")
    entries = json.loads(result)
    assert len(entries) == 2
    assert entries[0]["content"] == "Memory entry 1"
    assert entries[1]["content"] == "Memory entry 2"  # fallback to "text"


@pytest.mark.asyncio
async def test_qdrant_scroll_latest_unreachable(monkeypatch):
    """_qdrant_scroll_latest returns error JSON when Qdrant is down."""

    async def mock_post(self, url, **kwargs):
        raise httpx.ConnectError("Connection refused")

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    result = await _qdrant_scroll_latest("localhost", 6333, "swarm_memory")
    data = json.loads(result)
    assert "error" in data
    assert "unreachable" in data["error"]


@pytest.mark.asyncio
async def test_qdrant_scroll_latest_error_status(monkeypatch):
    """_qdrant_scroll_latest handles non-200 status from Qdrant."""
    mock_response = httpx.Response(404, text="Collection not found")

    async def mock_post(self, url, **kwargs):
        return mock_response

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    result = await _qdrant_scroll_latest("localhost", 6333, "missing_coll")
    data = json.loads(result)
    assert "error" in data
    assert "404" in data["error"]


# ── 4. query_formic_memory Tool ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_qdrant_search_success(monkeypatch):
    """_qdrant_search returns Markdown-formatted results."""
    call_count = 0

    async def mock_post(self, url, **kwargs):
        nonlocal call_count
        call_count += 1
        if "embeddings" in url:
            return httpx.Response(200, json={
                "data": [{"embedding": [0.1] * 1024}],
            })
        else:
            return httpx.Response(200, json={
                "result": {
                    "points": [
                        {
                            "payload": {
                                "content": "First result content",
                                "source": "colony_a",
                            },
                            "score": 0.95,
                        },
                        {
                            "payload": {
                                "content": "Second result content",
                                "source": "colony_b",
                            },
                            "score": 0.82,
                        },
                    ],
                },
            })

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    result = await _qdrant_search(
        "localhost", 6333, "http://embed:8080/v1",
        "test query", "swarm_memory", 5,
    )
    assert "Search Results" in result
    assert "First result content" in result
    assert "Second result content" in result
    assert "0.950" in result
    assert call_count == 2  # embed + search


@pytest.mark.asyncio
async def test_qdrant_search_no_results(monkeypatch):
    """_qdrant_search returns 'No results' when collection is empty."""

    async def mock_post(self, url, **kwargs):
        if "embeddings" in url:
            return httpx.Response(200, json={
                "data": [{"embedding": [0.1] * 1024}],
            })
        return httpx.Response(200, json={
            "result": {"points": []},
        })

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    result = await _qdrant_search(
        "localhost", 6333, "http://embed:8080/v1",
        "obscure query", "swarm_memory", 5,
    )
    assert "No results" in result


@pytest.mark.asyncio
async def test_qdrant_search_embed_failure(monkeypatch):
    """_qdrant_search handles embedding API failure."""

    async def mock_post(self, url, **kwargs):
        if "embeddings" in url:
            return httpx.Response(500, text="Internal error")
        return httpx.Response(200, json={"result": {"points": []}})

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    result = await _qdrant_search(
        "localhost", 6333, "http://embed:8080/v1",
        "query", "swarm_memory", 5,
    )
    assert "error" in result.lower() or "500" in result


@pytest.mark.asyncio
async def test_qdrant_search_connection_failure(monkeypatch):
    """_qdrant_search handles connection failure gracefully."""

    async def mock_post(self, url, **kwargs):
        raise httpx.ConnectError("Connection refused")

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    result = await _qdrant_search(
        "localhost", 6333, "http://embed:8080/v1",
        "query", "swarm_memory", 5,
    )
    assert "failed" in result.lower() or "error" in result.lower()


# ── 5. get_colony_failure_history Tool ───────────────────────────────────


def test_extract_failure_history_from_decisions(tmp_path):
    """Extracts failures from decisions with force_halt type."""
    ctx = _make_context(
        colony_id="fail_colony",
        decisions=[
            {
                "schema_version": "0.6.0",
                "round_num": 3,
                "decision_type": "force_halt",
                "detail": "Colony halted: budget exhausted",
                "timestamp": time.time(),
                "recommendations": [],
                "enriched_recommendations": [],
            },
            {
                "schema_version": "0.6.0",
                "round_num": 2,
                "decision_type": "manager_goal",
                "detail": "Goal: fix the tests",
                "timestamp": time.time() - 100,
                "recommendations": [],
                "enriched_recommendations": [],
            },
        ],
    )
    _write_session(tmp_path, "sess_fail", ctx)

    failures = extract_failure_history(tmp_path, "fail_colony")
    assert len(failures) == 1
    assert failures[0]["decision_type"] == "force_halt"
    assert failures[0]["colony_id"] == "fail_colony"


def test_extract_failure_history_from_tkg(tmp_path):
    """Extracts failures from TKG tuples with failure predicates."""
    ctx = _make_context(
        colony_id="tkg_colony",
        tkg=[
            {
                "schema_version": "0.6.0",
                "subject": "coder_01",
                "predicate": "Failed_Test",
                "object_": "test_auth.py::test_login failed with AssertionError",
                "round_num": 2,
                "timestamp": time.time(),
                "team_id": None,
            },
            {
                "schema_version": "0.6.0",
                "subject": "coder_01",
                "predicate": "Produced",
                "object_": "auth.py",
                "round_num": 2,
                "timestamp": time.time(),
                "team_id": None,
            },
        ],
    )
    _write_session(tmp_path, "sess_tkg", ctx)

    failures = extract_failure_history(tmp_path, "tkg_colony")
    assert len(failures) == 1
    assert failures[0]["predicate"] == "Failed_Test"
    assert failures[0]["source"] == "tkg"


def test_extract_failure_history_from_enriched_recommendations(tmp_path):
    """Extracts failures from enriched_recommendations with escalate action."""
    ctx = _make_context(
        colony_id="rec_colony",
        decisions=[
            {
                "schema_version": "0.6.0",
                "round_num": 4,
                "decision_type": "convergence",
                "detail": "Colony stuck",
                "timestamp": time.time(),
                "recommendations": [],
                "enriched_recommendations": [
                    {
                        "action": "escalate",
                        "confidence_score": 0.9,
                        "evidence": "No progress in 3 rounds",
                    },
                ],
            },
        ],
    )
    _write_session(tmp_path, "sess_rec", ctx)

    failures = extract_failure_history(tmp_path, "rec_colony")
    assert len(failures) == 1
    assert failures[0]["source"] == "decision"


def test_extract_failure_history_limits_to_3(tmp_path):
    """Returns at most 3 failure records."""
    now = time.time()
    decisions = [
        {
            "schema_version": "0.6.0",
            "round_num": i,
            "decision_type": "force_halt",
            "detail": f"Halt {i}",
            "timestamp": now - (10 * i),
            "recommendations": [],
            "enriched_recommendations": [],
        }
        for i in range(5)
    ]
    ctx = _make_context(colony_id="many_fails", decisions=decisions)
    _write_session(tmp_path, "sess_many", ctx)

    failures = extract_failure_history(tmp_path, "many_fails")
    assert len(failures) == 3


def test_extract_failure_history_sorted_by_timestamp(tmp_path):
    """Failures are sorted newest-first."""
    now = time.time()
    ctx = _make_context(
        colony_id="sorted_colony",
        decisions=[
            {
                "schema_version": "0.6.0",
                "round_num": 1,
                "decision_type": "force_halt",
                "detail": "Old halt",
                "timestamp": now - 1000,
                "recommendations": [],
                "enriched_recommendations": [],
            },
            {
                "schema_version": "0.6.0",
                "round_num": 5,
                "decision_type": "intervene",
                "detail": "Recent intervene",
                "timestamp": now,
                "recommendations": [],
                "enriched_recommendations": [],
            },
        ],
    )
    _write_session(tmp_path, "sess_sorted", ctx)

    failures = extract_failure_history(tmp_path, "sorted_colony")
    assert len(failures) == 2
    assert failures[0]["detail"] == "Recent intervene"
    assert failures[1]["detail"] == "Old halt"


def test_extract_failure_history_no_failures(tmp_path):
    """Returns empty list when no failures exist."""
    ctx = _make_context(colony_id="healthy")
    _write_session(tmp_path, "sess_healthy", ctx)

    failures = extract_failure_history(tmp_path, "healthy")
    assert failures == []


def test_extract_failure_history_all_colonies(tmp_path):
    """Without colony_id filter, collects failures from all sessions."""
    ctx1 = _make_context(
        colony_id="col_a",
        decisions=[{
            "schema_version": "0.6.0",
            "round_num": 1,
            "decision_type": "force_halt",
            "detail": "A halted",
            "timestamp": time.time(),
            "recommendations": [],
            "enriched_recommendations": [],
        }],
    )
    ctx2 = _make_context(
        colony_id="col_b",
        tkg=[{
            "schema_version": "0.6.0",
            "subject": "agent",
            "predicate": "Error",
            "object_": "Connection timeout",
            "round_num": 2,
            "timestamp": time.time() - 10,
            "team_id": None,
        }],
    )
    _write_session(tmp_path, "sess_a", ctx1)
    _write_session(tmp_path, "sess_b", ctx2)

    failures = extract_failure_history(tmp_path, colony_id=None)
    assert len(failures) == 2
    colony_ids = {f["colony_id"] for f in failures}
    assert colony_ids == {"col_a", "col_b"}


def test_extract_failure_history_missing_dir():
    """Returns empty list when session dir doesn't exist."""
    from pathlib import Path
    failures = extract_failure_history(Path("/nonexistent"))
    assert failures == []
