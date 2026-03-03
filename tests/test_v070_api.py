"""
FormicOS v0.7.0 — API v1 Endpoint Tests

Verifies all /api/v1/* endpoints return correct status codes and schema shapes.
Tests error responses conform to ApiErrorV1.
Tests legacy endpoints still work.
Reuses the test fixture pattern from test_server.py.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from src.context import AsyncContextTree
from src.models import (
    ColonyStatus,
    FormicOSConfig,
    load_config,
)
from src.server import create_app


# ── Test Config ───────────────────────────────────────────────────────────


def _make_test_config(tmp_path: Path) -> FormicOSConfig:
    """Build a minimal FormicOSConfig from YAML (matches test_server.py pattern)."""
    config_file = tmp_path / "formicos.yaml"
    config_file.write_text('''
schema_version: "1.0"
identity:
  name: FormicOS
  version: "0.7.1"
hardware:
  gpu: test
  vram_gb: 32
  vram_alert_threshold_gb: 28
inference:
  endpoint: http://localhost:8080/v1
  model: test-model
  model_alias: gpt-4
  max_tokens_per_agent: 5000
  temperature: 0
  timeout_seconds: 120
  context_size: 32768
  intent_model: null
  intent_max_tokens: 512
embedding:
  model: test-embed
  endpoint: http://localhost:8081/v1
  dimensions: 1024
  max_tokens: 8192
  batch_size: 32
  routing_model: all-MiniLM-L6-v2
routing:
  tau: 0.35
  k_in: 3
  broadcast_fallback: true
convergence:
  similarity_threshold: 0.95
  rounds_before_force_halt: 2
  path_diversity_warning_after: 3
summarization:
  epoch_window: 5
  max_epoch_tokens: 400
  max_agent_summary_tokens: 200
  tree_sitter_languages: [python]
temporal:
  episodic_ttl_hours: 72
  stall_repeat_threshold: 3
  stall_window_minutes: 20
  tkg_max_tuples: 5000
castes:
  manager:
    system_prompt_file: manager.md
    tools: []
    model_override: null
persistence:
  session_dir: {session_dir}
  autosave_interval_seconds: 30
approval_required: []
qdrant:
  host: localhost
  port: 6333
  grpc_port: 6334
  collections:
    project_docs:
      embedding: bge-m3
      dimensions: 1024
mcp_gateway:
  enabled: false
  transport: stdio
  command: docker
  args: ["mcp", "gateway", "run"]
  docker_fallback_endpoint: http://localhost:8811
  sse_retry_attempts: 0
  sse_retry_delay_seconds: 1
model_registry:
  test/model:
    type: autoregressive
    backend: llama_cpp
    endpoint: http://localhost:8080/v1
    context_length: 32768
    vram_gb: 25.6
    supports_tools: true
    supports_streaming: true
skill_bank:
  storage_file: {skill_file}
  retrieval_top_k: 3
  dedup_threshold: 0.85
  evolution_interval: 5
  prune_zero_hit_after: 10
subcaste_map:
  heavy:
    primary: test/model
  balanced:
    primary: test/model
  light:
    primary: test/model
teams:
  max_teams_per_colony: 4
  team_summary_max_tokens: 200
  allow_dynamic_spawn: true
colonies: {{}}
'''.format(
        session_dir=str(tmp_path / "sessions").replace("\\", "/"),
        skill_file=str(tmp_path / "skills.json").replace("\\", "/"),
    ))
    return load_config(config_file)


# ── Mock Factories ────────────────────────────────────────────────────────


def _mock_colony_manager() -> MagicMock:
    cm = MagicMock()
    cm.get_all.return_value = []

    info_mock = MagicMock()
    info_mock.colony_id = "test-colony"
    info_mock.task = "test task"
    info_mock.status = ColonyStatus.RUNNING
    info_mock.round = 2
    info_mock.max_rounds = 10
    info_mock.agent_count = 3
    info_mock.teams = []
    info_mock.created_at = 1000000.0
    info_mock.updated_at = 1000000.0
    info_mock.origin = "ui"
    info_mock.client_id = None
    info_mock.webhook_url = None
    info_mock.model_dump.return_value = {
        "colony_id": "test-colony",
        "task": "test task",
        "status": "running",
        "round": 2,
        "max_rounds": 10,
        "agent_count": 3,
        "teams": [],
        "created_at": 1000000.0,
        "updated_at": 1000000.0,
    }

    from src.colony_manager import ColonyNotFoundError

    def _get_info(colony_id):
        if colony_id != "test-colony":
            raise ColonyNotFoundError(colony_id)
        return info_mock

    def _get_context(colony_id):
        if colony_id != "test-colony":
            raise ColonyNotFoundError(colony_id)
        ctx = AsyncContextTree()
        return ctx

    cm.get_info = MagicMock(side_effect=_get_info)
    cm.get_context = MagicMock(side_effect=_get_context)
    cm.create = AsyncMock(return_value=info_mock)
    cm.start = AsyncMock()
    cm.pause = AsyncMock(return_value=Path("/tmp/session.json"))
    cm.resume = AsyncMock()
    cm.destroy = AsyncMock(return_value=Path("/tmp/archive.json"))
    cm.extend = AsyncMock(return_value=15)
    return cm


# ── Fixture ───────────────────────────────────────────────────────────────


@pytest.fixture
async def app_and_client(tmp_path):
    config = _make_test_config(tmp_path)
    app = create_app(config)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Replace services with mocks (same pattern as test_server.py)
        app.state.colony_manager = _mock_colony_manager()
        app.state.model_registry = MagicMock()
        app.state.model_registry.list_models.return_value = {
            "test/model": {"status": "healthy", "backend": "llama_cpp"}
        }
        app.state.model_registry.get_vram_budget.return_value = {"total_gb": 32}
        app.state.session_manager = MagicMock()
        app.state.session_manager.list_sessions = AsyncMock(return_value=[])
        app.state.session_manager.delete_session = AsyncMock()
        app.state.mcp_client = MagicMock()
        app.state.mcp_client.connected = False
        app.state.mcp_client.connect_error = None
        app.state.mcp_client.get_tools.return_value = []
        app.state.skill_bank = MagicMock()
        app.state.skill_bank.get_all.return_value = {"general": [], "task_specific": []}
        app.state.skill_bank.store_single.return_value = "skill-123"
        app.state.skill_bank._find_skill.side_effect = KeyError("not found")
        app.state.approval_gate = MagicMock()
        app.state.approval_gate.get_pending.return_value = []
        app.state.audit_logger = MagicMock()
        app.state.audit_logger.flush = AsyncMock()
        app.state.audit_logger.close = AsyncMock()
        app.state.gpu_stats = {"used_gb": 10.5, "total_gb": 32.0}
        app.state.routing_embedder = None

        if not hasattr(app.state, "ctx"):
            app.state.ctx = AsyncContextTree()

        yield app, client


# ══════════════════════════════════════════════════════════════════════════
# System
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_v1_system(app_and_client):
    _, client = app_and_client
    resp = await client.get("/api/v1/system")
    assert resp.status_code == 200
    data = resp.json()
    assert data["version"] == "0.9.0"
    assert data["schema_version"] == "1.0"


@pytest.mark.asyncio
async def test_v1_system_health(app_and_client):
    _, client = app_and_client
    resp = await client.get("/api/v1/system/health")
    assert resp.status_code == 200
    data = resp.json()
    assert "status" in data
    assert "checks" in data
    assert "llm" in data["checks"]
    assert "mcp" in data["checks"]
    assert "embedding" in data["checks"]


@pytest.mark.asyncio
async def test_v1_system_metrics(app_and_client):
    _, client = app_and_client
    resp = await client.get("/api/v1/system/metrics")
    assert resp.status_code == 200
    assert isinstance(resp.json(), dict)


# ══════════════════════════════════════════════════════════════════════════
# Colonies
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_v1_list_colonies(app_and_client):
    _, client = app_and_client
    resp = await client.get("/api/v1/colonies")
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert isinstance(data["items"], list)


@pytest.mark.asyncio
async def test_v1_create_colony(app_and_client):
    _, client = app_and_client
    resp = await client.post("/api/v1/colonies", json={
        "task": "test task",
        "max_rounds": 5,
    })
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_v1_get_colony(app_and_client):
    _, client = app_and_client
    resp = await client.get("/api/v1/colonies/test-colony")
    assert resp.status_code == 200
    data = resp.json()
    assert data["colony_id"] == "test-colony"
    assert "status" in data
    assert "workspace" in data
    assert "agents" in data


@pytest.mark.asyncio
async def test_v1_get_colony_not_found(app_and_client):
    _, client = app_and_client
    resp = await client.get("/api/v1/colonies/nonexistent")
    assert resp.status_code == 404
    data = resp.json()
    assert data["error_code"] == "COLONY_NOT_FOUND"
    assert data["status"] == 404


@pytest.mark.asyncio
async def test_v1_start_colony(app_and_client):
    _, client = app_and_client
    resp = await client.post("/api/v1/colonies/test-colony/start")
    assert resp.status_code == 200
    assert resp.json()["status"] == "started"


@pytest.mark.asyncio
async def test_v1_pause_colony(app_and_client):
    _, client = app_and_client
    resp = await client.post("/api/v1/colonies/test-colony/pause")
    assert resp.status_code == 200
    assert resp.json()["status"] == "paused"


@pytest.mark.asyncio
async def test_v1_resume_colony(app_and_client):
    _, client = app_and_client
    resp = await client.post("/api/v1/colonies/test-colony/resume")
    assert resp.status_code == 200
    assert resp.json()["status"] == "resumed"


@pytest.mark.asyncio
async def test_v1_destroy_colony(app_and_client):
    _, client = app_and_client
    resp = await client.delete("/api/v1/colonies/test-colony")
    assert resp.status_code == 200
    assert resp.json()["status"] == "destroyed"


@pytest.mark.asyncio
async def test_v1_extend_colony(app_and_client):
    _, client = app_and_client
    resp = await client.post("/api/v1/colonies/test-colony/extend", json={
        "rounds": 5,
        "hint": "keep going",
    })
    assert resp.status_code == 200
    assert resp.json()["new_max_rounds"] == 15


# ══════════════════════════════════════════════════════════════════════════
# Runtime Views
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_v1_topology(app_and_client):
    _, client = app_and_client
    resp = await client.get("/api/v1/colonies/test-colony/topology")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_v1_topology_not_found(app_and_client):
    _, client = app_and_client
    resp = await client.get("/api/v1/colonies/nonexistent/topology")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_v1_topology_history(app_and_client):
    _, client = app_and_client
    resp = await client.get("/api/v1/colonies/test-colony/topology/history")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_v1_decisions(app_and_client):
    _, client = app_and_client
    resp = await client.get("/api/v1/colonies/test-colony/decisions")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_v1_episodes(app_and_client):
    _, client = app_and_client
    resp = await client.get("/api/v1/colonies/test-colony/episodes")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_v1_tkg(app_and_client):
    _, client = app_and_client
    resp = await client.get("/api/v1/colonies/test-colony/tkg")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


# ══════════════════════════════════════════════════════════════════════════
# Results
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_v1_results(app_and_client):
    _, client = app_and_client
    resp = await client.get("/api/v1/colonies/test-colony/results")
    assert resp.status_code == 200
    data = resp.json()
    assert data["colony_id"] == "test-colony"
    assert "status" in data
    assert "files" in data


@pytest.mark.asyncio
async def test_v1_result_files(app_and_client):
    _, client = app_and_client
    resp = await client.get("/api/v1/colonies/test-colony/results/files")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


# ══════════════════════════════════════════════════════════════════════════
# Skills
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_v1_list_skills(app_and_client):
    _, client = app_and_client
    resp = await client.get("/api/v1/skills")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_v1_create_skill(app_and_client):
    _, client = app_and_client
    resp = await client.post("/api/v1/skills", json={
        "content": "test skill",
        "tier": "general",
    })
    assert resp.status_code == 200
    assert resp.json()["status"] == "created"


# ══════════════════════════════════════════════════════════════════════════
# Sessions
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_v1_list_sessions(app_and_client):
    _, client = app_and_client
    resp = await client.get("/api/v1/sessions")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


# ══════════════════════════════════════════════════════════════════════════
# Models
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_v1_list_models(app_and_client):
    _, client = app_and_client
    resp = await client.get("/api/v1/models")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_v1_models_health(app_and_client):
    _, client = app_and_client
    resp = await client.get("/api/v1/models/health")
    assert resp.status_code == 200


# ══════════════════════════════════════════════════════════════════════════
# Approvals
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_v1_pending_approvals(app_and_client):
    _, client = app_and_client
    resp = await client.get("/api/v1/approvals/pending")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


# ══════════════════════════════════════════════════════════════════════════
# Tools
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_v1_list_tools(app_and_client):
    _, client = app_and_client
    resp = await client.get("/api/v1/tools")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_v1_tools_catalog(app_and_client):
    _, client = app_and_client
    resp = await client.get("/api/v1/tools/catalog")
    assert resp.status_code == 200
    data = resp.json()
    assert "connected" in data
    assert "servers" in data


@pytest.mark.asyncio
async def test_v1_workspace_open_nonfatal(app_and_client):
    _, client = app_and_client
    resp = await client.post("/api/v1/colonies/test-colony/workspace/open")
    assert resp.status_code == 200
    data = resp.json()
    assert "path" in data
    assert "opened" in data


# ══════════════════════════════════════════════════════════════════════════
# Error Shape
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_v1_error_conforms_to_api_error_v1(app_and_client):
    """All v1 error responses follow RFC 7807 ProblemDetail format."""
    _, client = app_and_client
    resp = await client.get("/api/v1/colonies/nonexistent")
    assert resp.status_code == 404
    data = resp.json()
    # RFC 7807 fields
    assert "status" in data
    assert "error_code" in data
    assert "detail" in data
    assert data["error_code"] == "COLONY_NOT_FOUND"


# ══════════════════════════════════════════════════════════════════════════
# Legacy Compat
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_legacy_system_still_works(app_and_client):
    _, client = app_and_client
    resp = await client.get("/api/system")
    assert resp.status_code == 200
    data = resp.json()
    assert "version" in data


@pytest.mark.asyncio
async def test_v1_workspace_archive_selected_paths(app_and_client):
    _, client = app_and_client
    ws = Path("workspace") / "test-colony"
    ws.mkdir(parents=True, exist_ok=True)
    (ws / "a.txt").write_text("alpha", encoding="utf-8")
    (ws / "nested").mkdir(exist_ok=True)
    (ws / "nested" / "b.txt").write_text("beta", encoding="utf-8")

    resp = await client.get(
        "/api/v1/colonies/test-colony/workspace/archive",
        params=[("paths", "a.txt"), ("paths", "nested/b.txt")],
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/zip")

    with zipfile.ZipFile(io.BytesIO(resp.content), "r") as zf:
        names = sorted(zf.namelist())
    assert names == ["a.txt", "nested/b.txt"]


@pytest.mark.asyncio
async def test_legacy_supercolony_still_works(app_and_client):
    _, client = app_and_client
    resp = await client.get("/api/supercolony")
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert isinstance(data["items"], list)
