"""
FormicOS v0.6.0 -- Server (API Gateway) Tests

Uses httpx.AsyncClient + ASGITransport to test the FastAPI application
without starting a real server or any backend services.  All dependencies
are mocked via app.state overrides after create_app().
"""

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from src.context import AsyncContextTree
from src.models import (
    ColonyConfig,
    ColonyStatus,
    FormicOSConfig,
    Skill,
    SkillTier,
    load_config,
)
from src.server import ConnectionManager, create_app, _poll_gpu


# ── Test Configuration ───────────────────────────────────────────────────


def _make_test_config(tmp_path: Path) -> FormicOSConfig:
    """Build a minimal FormicOSConfig for testing."""
    config_file = tmp_path / "formicos.yaml"
    config_file.write_text('''
schema_version: "0.6.0"
identity:
  name: FormicOS
  version: "0.6.0"
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


# ── Mock Factories ───────────────────────────────────────────────────────


def _mock_colony_manager() -> MagicMock:
    """Create a mock ColonyManager with async methods."""
    cm = MagicMock()
    cm.get_all.return_value = []

    info_mock = MagicMock()
    info_mock.colony_id = "test-colony"
    info_mock.task = "test task"
    info_mock.status = ColonyStatus.CREATED
    info_mock.round = 0
    info_mock.max_rounds = 10
    info_mock.agent_count = 5
    info_mock.teams = []
    info_mock.created_at = time.time()
    info_mock.updated_at = time.time()
    info_mock.model_dump.return_value = {
        "colony_id": "test-colony",
        "task": "test task",
        "status": "created",
        "round": 0,
        "max_rounds": 10,
        "agent_count": 5,
        "teams": [],
        "created_at": info_mock.created_at,
        "updated_at": info_mock.updated_at,
    }

    cm.create = AsyncMock(return_value=info_mock)
    cm.start = AsyncMock()
    cm.pause = AsyncMock(return_value=Path("/tmp/session.json"))
    cm.resume = AsyncMock()
    cm.destroy = AsyncMock(return_value=Path("/tmp/archive.json"))
    cm.extend = AsyncMock(return_value=15)
    cm.get_context = MagicMock(return_value=AsyncContextTree())
    return cm


def _mock_model_registry() -> MagicMock:
    """Create a mock ModelRegistry."""
    mr = MagicMock()
    mr.list_models.return_value = {
        "test/model": {
            "type": "autoregressive",
            "backend": "llama_cpp",
            "endpoint": "http://localhost:8080/v1",
            "model_string": None,
            "context_length": 32768,
            "vram_gb": 25.6,
            "supports_tools": True,
            "supports_streaming": True,
            "requires_approval": False,
            "status": "unknown",
        }
    }
    mr.get_vram_budget.return_value = {
        "total_vram": 32.0,
        "allocated": 25.6,
        "available": 6.4,
        "models": [{"model_id": "test/model", "vram_gb": 25.6}],
    }
    mr.has_model.return_value = True
    return mr


def _mock_session_manager() -> MagicMock:
    """Create a mock SessionManager."""
    sm = MagicMock()
    sm.list_sessions = AsyncMock(return_value=[])
    sm.delete_session = AsyncMock()
    return sm


def _mock_mcp_client() -> MagicMock:
    """Create a mock MCPGatewayClient."""
    mcp = MagicMock()
    mcp.connected = False
    mcp.connect_error = None
    mcp.connect = AsyncMock(return_value=True)
    mcp.disconnect = AsyncMock()
    mcp.get_tools.return_value = []
    mcp.health_check = AsyncMock(return_value=True)
    return mcp


def _mock_skill_bank() -> MagicMock:
    """Create a mock SkillBank."""
    sb = MagicMock()
    sb.get_all.return_value = {
        "general": [],
        "task_specific": [],
        "lesson": [],
    }
    sb.store_single.return_value = "gen_abc12345"
    sb.update.return_value = None
    sb.delete.return_value = None
    sb._find_skill.return_value = Skill(
        skill_id="gen_abc12345",
        content="Test skill",
        tier=SkillTier.GENERAL,
    )
    return sb


def _mock_approval_gate() -> MagicMock:
    """Create a mock ApprovalGate."""
    gate = MagicMock()
    gate.respond.return_value = None
    gate.get_pending.return_value = []
    return gate


def _mock_audit_logger() -> MagicMock:
    """Create a mock AuditLogger."""
    al = MagicMock()
    al.flush = AsyncMock()
    al.close = AsyncMock()
    return al


# ── Fixtures ─────────────────────────────────────────────────────────────


@pytest.fixture
async def app_and_client(tmp_path):
    """
    Create a test app with all services mocked and an httpx AsyncClient.

    Yields (app, client) so tests can inspect/modify app.state.
    """
    config = _make_test_config(tmp_path)
    app = create_app(config)

    # Override the lifespan-initialised services with mocks.
    # The lifespan still runs, but we replace its results immediately
    # after entering the AsyncClient context (which triggers the lifespan).
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Replace services with mocks
        app.state.colony_manager = _mock_colony_manager()
        app.state.model_registry = _mock_model_registry()
        app.state.session_manager = _mock_session_manager()
        app.state.mcp_client = _mock_mcp_client()
        app.state.skill_bank = _mock_skill_bank()
        app.state.approval_gate = _mock_approval_gate()
        app.state.audit_logger = _mock_audit_logger()
        app.state.gpu_stats = {"used_gb": 10.5, "total_gb": 32.0}

        # Ensure a context tree is available
        if not hasattr(app.state, "ctx"):
            app.state.ctx = AsyncContextTree()

        yield app, client


@pytest.fixture
async def client(app_and_client):
    """Shorthand: just the httpx AsyncClient."""
    _, c = app_and_client
    return c


@pytest.fixture
async def app(app_and_client):
    """Shorthand: just the FastAPI app."""
    a, _ = app_and_client
    return a


# ═══════════════════════════════════════════════════════════════════════════
# Tests
# ═══════════════════════════════════════════════════════════════════════════


# ── 1. GET /api/system ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_system(app_and_client):
    app, client = app_and_client
    resp = await client.get("/api/system")
    assert resp.status_code == 200
    data = resp.json()
    assert "version" in data
    assert "gpu" in data
    assert "vram_budget" in data
    assert data["version"] == "0.9.0"


# ── 2. GET /api/colony ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_colony(app_and_client):
    app, client = app_and_client
    ctx: AsyncContextTree = app.state.ctx
    await ctx.set("colony", "task", "build something")
    await ctx.set("colony", "status", "running")
    await ctx.set("colony", "round", 3)
    await ctx.set("colony", "agents", ["a1", "a2"])

    resp = await client.get("/api/colony")
    assert resp.status_code == 200
    data = resp.json()
    assert data["task"] == "build something"
    assert data["status"] == "running"
    assert data["round"] == 3
    assert data["agents"] == ["a1", "a2"]


# ── 3. GET /api/topology ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_topology(app_and_client):
    app, client = app_and_client

    # No topology set yet -> empty
    resp = await client.get("/api/topology")
    assert resp.status_code == 200
    data = resp.json()
    assert data["edges"] == []

    # Set a topology
    ctx: AsyncContextTree = app.state.ctx
    await ctx.set("colony", "topology", {
        "edges": [{"sender": "a", "receiver": "b", "weight": 0.5}],
        "execution_order": ["a", "b"],
        "density": 0.5,
    })
    resp = await client.get("/api/topology")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["edges"]) == 1


# ── 4. GET /api/decisions ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_decisions(app_and_client):
    app, client = app_and_client
    resp = await client.get("/api/decisions")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


# ── 5. GET /api/episodes ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_episodes(app_and_client):
    app, client = app_and_client
    resp = await client.get("/api/episodes")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


# ── 6. GET /api/sessions ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_sessions(app_and_client):
    app, client = app_and_client
    resp = await client.get("/api/sessions")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
    app.state.session_manager.list_sessions.assert_awaited_once()


# ── 7. DELETE /api/sessions/{id} ────────────────────────────────────────


@pytest.mark.asyncio
async def test_delete_session(app_and_client):
    app, client = app_and_client
    resp = await client.delete("/api/sessions/test-session-1")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "deleted"
    assert data["session_id"] == "test-session-1"
    app.state.session_manager.delete_session.assert_awaited_once_with("test-session-1")


@pytest.mark.asyncio
async def test_delete_session_not_found(app_and_client):
    app, client = app_and_client
    app.state.session_manager.delete_session = AsyncMock(
        side_effect=FileNotFoundError("not found")
    )
    resp = await client.delete("/api/sessions/nonexistent")
    assert resp.status_code == 404
    data = resp.json()
    assert data["error_code"] == "SESSION_NOT_FOUND"


# ── 8. GET /api/models ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_models(app_and_client):
    app, client = app_and_client
    resp = await client.get("/api/models")
    assert resp.status_code == 200
    data = resp.json()
    assert "test/model" in data
    assert data["test/model"]["backend"] == "llama_cpp"


# ── 9. POST /api/run ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_run_colony(app_and_client):
    app, client = app_and_client
    resp = await client.post("/api/run", json={
        "task": "Build a REST API",
        "max_rounds": 5,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "running"
    assert data["task"] == "Build a REST API"
    assert "colony_id" in data

    # Verify colony_manager.create and .start were called
    app.state.colony_manager.create.assert_awaited_once()
    app.state.colony_manager.start.assert_awaited_once()


# ── 10. POST /api/colony/{id}/create ────────────────────────────────────


@pytest.mark.asyncio
async def test_create_colony(app_and_client):
    app, client = app_and_client
    resp = await client.post("/api/colony/my-colony/create", json={
        "task": "Design a database schema",
        "max_rounds": 8,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["colony_id"] == "test-colony"  # from mock
    app.state.colony_manager.create.assert_awaited_once()


# ── 11. POST /api/colony/{id}/start ─────────────────────────────────────


@pytest.mark.asyncio
async def test_start_colony(app_and_client):
    app, client = app_and_client
    resp = await client.post("/api/colony/test-colony/start")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "started"
    assert data["colony_id"] == "test-colony"


# ── 12. POST /api/colony/{id}/pause ─────────────────────────────────────


@pytest.mark.asyncio
async def test_pause_colony(app_and_client):
    app, client = app_and_client
    resp = await client.post("/api/colony/test-colony/pause")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "paused"


# ── 13. DELETE /api/colony/{id}/destroy ─────────────────────────────────


@pytest.mark.asyncio
async def test_destroy_colony(app_and_client):
    app, client = app_and_client
    resp = await client.delete("/api/colony/test-colony/destroy")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "destroyed"
    app.state.colony_manager.destroy.assert_awaited_once_with("test-colony")


# ── 14. POST /api/colony/extend ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_extend_colony(app_and_client):
    app, client = app_and_client
    resp = await client.post("/api/colony/extend", json={
        "colony_id": "test-colony",
        "rounds": 5,
        "hint": "Try a different approach",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["new_max_rounds"] == 15
    app.state.colony_manager.extend.assert_awaited_once_with(
        "test-colony", 5, "Try a different approach"
    )


# ── 15. GET /api/supercolony ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_supercolony(app_and_client):
    app, client = app_and_client
    resp = await client.get("/api/supercolony")
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert isinstance(data["items"], list)
    assert "total" in data
    app.state.colony_manager.get_all.assert_called_once()


# ── 16. POST /api/approve ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_approve(app_and_client):
    app, client = app_and_client
    resp = await client.post("/api/approve", json={
        "request_id": "req-123",
        "approved": True,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "resolved"
    assert data["approved"] is True
    app.state.approval_gate.respond.assert_called_once_with("req-123", True)


@pytest.mark.asyncio
async def test_approve_not_found(app_and_client):
    app, client = app_and_client
    app.state.approval_gate.respond.side_effect = KeyError("not found")
    resp = await client.post("/api/approve", json={
        "request_id": "nonexistent",
        "approved": False,
    })
    assert resp.status_code == 404
    data = resp.json()
    assert data["error_code"] == "APPROVAL_NOT_FOUND"


# ── 17. POST /api/intervene ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_intervene(app_and_client):
    app, client = app_and_client
    ctx: AsyncContextTree = app.state.ctx
    await ctx.set("colony", "colony_id", "test-colony")

    resp = await client.post("/api/intervene", json={
        "hint": "Focus on error handling",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "injected"
    assert data["hint"] == "Focus on error handling"
    assert data["colony_id"] == "test-colony"

    # Verify hint stored in context tree
    stored_hint = ctx.get("colony", "operator_hint")
    assert stored_hint == "Focus on error handling"


@pytest.mark.asyncio
async def test_intervene_with_explicit_colony_id(app_and_client):
    app, client = app_and_client
    resp = await client.post("/api/intervene", json={
        "colony_id": "explicit-colony",
        "hint": "Use microservices",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["colony_id"] == "explicit-colony"


@pytest.mark.asyncio
async def test_intervene_no_active_colony(app_and_client):
    app, client = app_and_client
    # No colony_id set and no explicit colony_id in body
    resp = await client.post("/api/intervene", json={
        "hint": "Something",
    })
    assert resp.status_code == 404
    data = resp.json()
    assert data["error_code"] == "NO_ACTIVE_COLONY"


# ── 18. GET /api/prompts ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_prompts(app_and_client, tmp_path):
    app, client = app_and_client

    # Create a temporary prompts directory
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()
    (prompts_dir / "manager.md").write_text("You are a manager.")
    (prompts_dir / "coder.md").write_text("You are a coder.")
    (prompts_dir / "_descriptor_suffix.md").write_text("suffix")

    with patch("src.server.Path") as _mock_path_class:
        # We need to be more careful -- only patch the prompts_dir lookup
        pass

    # Use the real endpoint but with the actual config/prompts directory
    resp = await client.get("/api/prompts")
    assert resp.status_code == 200
    # The response is a list (may be empty if config/prompts doesn't exist in test)
    assert isinstance(resp.json(), list)


# ── 19. SkillBank CRUD ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_skill_bank_get_all(app_and_client):
    app, client = app_and_client
    resp = await client.get("/api/skill-bank")
    assert resp.status_code == 200
    data = resp.json()
    assert "general" in data
    assert "task_specific" in data
    assert "lesson" in data


@pytest.mark.asyncio
async def test_skill_create(app_and_client):
    app, client = app_and_client
    resp = await client.post("/api/skill-bank/skill", json={
        "content": "Always validate input before processing",
        "tier": "general",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "created"
    assert data["skill_id"] == "gen_abc12345"
    app.state.skill_bank.store_single.assert_called_once()


@pytest.mark.asyncio
async def test_skill_update(app_and_client):
    app, client = app_and_client
    resp = await client.put("/api/skill-bank/skill/gen_abc12345", json={
        "content": "Updated skill content",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "updated"
    app.state.skill_bank.update.assert_called_once_with(
        "gen_abc12345", "Updated skill content"
    )


@pytest.mark.asyncio
async def test_skill_delete(app_and_client):
    app, client = app_and_client
    resp = await client.delete("/api/skill-bank/skill/gen_abc12345")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "deleted"
    app.state.skill_bank.delete.assert_called_once_with("gen_abc12345")


@pytest.mark.asyncio
async def test_skill_get_by_id(app_and_client):
    app, client = app_and_client
    resp = await client.get("/api/skill-bank/skill/gen_abc12345")
    assert resp.status_code == 200
    data = resp.json()
    assert data["skill_id"] == "gen_abc12345"
    assert data["content"] == "Test skill"


@pytest.mark.asyncio
async def test_skill_not_found(app_and_client):
    app, client = app_and_client
    app.state.skill_bank._find_skill.side_effect = KeyError("not found")
    resp = await client.get("/api/skill-bank/skill/nonexistent")
    assert resp.status_code == 404
    data = resp.json()
    assert data["error_code"] == "SKILL_NOT_FOUND"


@pytest.mark.asyncio
async def test_skill_delete_not_found(app_and_client):
    app, client = app_and_client
    app.state.skill_bank.delete.side_effect = KeyError("not found")
    resp = await client.delete("/api/skill-bank/skill/nonexistent")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_skill_update_not_found(app_and_client):
    app, client = app_and_client
    app.state.skill_bank.update.side_effect = KeyError("not found")
    resp = await client.put("/api/skill-bank/skill/nonexistent", json={
        "content": "something",
    })
    assert resp.status_code == 404


# ── 20. POST /api/mcp/reconnect ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_mcp_reconnect(app_and_client):
    app, client = app_and_client
    app.state.mcp_client.connected = False
    app.state.mcp_client.connect = AsyncMock(return_value=True)
    app.state.mcp_client.get_tools.return_value = [
        {"id": "tool1"}, {"id": "tool2"}
    ]

    resp = await client.post("/api/mcp/reconnect")
    assert resp.status_code == 200
    data = resp.json()
    assert data["connected"] is True
    assert data["tools_count"] == 2


@pytest.mark.asyncio
async def test_mcp_reconnect_failure(app_and_client):
    app, client = app_and_client
    app.state.mcp_client.connected = False
    app.state.mcp_client.connect = AsyncMock(return_value=False)
    app.state.mcp_client.connect_error = "Connection refused"

    resp = await client.post("/api/mcp/reconnect")
    assert resp.status_code == 200
    data = resp.json()
    assert data["connected"] is False
    assert data["error"] == "Connection refused"


# ── 21. Error responses return structured JSON ──────────────────────────


@pytest.mark.asyncio
async def test_error_response_structure(app_and_client):
    """Colony not found errors return structured JSON with error_code, error_detail, request_id."""
    app, client = app_and_client
    from src.colony_manager import ColonyNotFoundError
    app.state.colony_manager.start = AsyncMock(
        side_effect=ColonyNotFoundError("Colony 'xyz' not found")
    )

    resp = await client.post("/api/colony/xyz/start")
    assert resp.status_code == 404
    data = resp.json()
    assert "error_code" in data
    assert "error_detail" in data
    assert "request_id" in data
    assert data["error_code"] == "COLONY_NOT_FOUND"


@pytest.mark.asyncio
async def test_invalid_transition_error(app_and_client):
    app, client = app_and_client
    from src.colony_manager import InvalidTransitionError
    app.state.colony_manager.pause = AsyncMock(
        side_effect=InvalidTransitionError("Cannot pause a CREATED colony")
    )

    resp = await client.post("/api/colony/test-colony/pause")
    assert resp.status_code == 409
    data = resp.json()
    assert data["error_code"] == "INVALID_TRANSITION"


# ── Additional endpoint tests ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_tkg(app_and_client):
    app, client = app_and_client
    resp = await client.get("/api/tkg")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_get_epochs(app_and_client):
    app, client = app_and_client
    resp = await client.get("/api/epochs")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_colony_resume_endpoint(app_and_client):
    app, client = app_and_client
    resp = await client.post("/api/colony/test-colony/resume")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "resumed"


@pytest.mark.asyncio
async def test_extend_colony_not_found(app_and_client):
    app, client = app_and_client
    from src.colony_manager import ColonyNotFoundError
    app.state.colony_manager.extend = AsyncMock(
        side_effect=ColonyNotFoundError("not found")
    )
    resp = await client.post("/api/colony/extend", json={
        "colony_id": "missing",
        "rounds": 3,
    })
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_legacy_resume_no_colony(app_and_client):
    """POST /api/resume with no active colony returns 404."""
    app, client = app_and_client
    resp = await client.post("/api/resume")
    assert resp.status_code == 404
    data = resp.json()
    assert data["error_code"] == "NO_ACTIVE_COLONY"


@pytest.mark.asyncio
async def test_legacy_resume_with_colony(app_and_client):
    """POST /api/resume with an active colony resumes it."""
    app, client = app_and_client
    ctx: AsyncContextTree = app.state.ctx
    await ctx.set("colony", "colony_id", "dashboard-colony")

    resp = await client.post("/api/resume")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "resumed"
    assert data["colony_id"] == "dashboard-colony"


@pytest.mark.asyncio
async def test_delete_active_session_clears_context(app_and_client):
    """Deleting the active session should clear colony context."""
    app, client = app_and_client
    ctx: AsyncContextTree = app.state.ctx
    await ctx.set("colony", "session_id", "active-session")
    await ctx.set("colony", "task", "some task")

    resp = await client.delete("/api/sessions/active-session")
    assert resp.status_code == 200

    # Context should be cleared
    assert ctx.get("colony", "task") is None


# ── ConnectionManager unit test ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_connection_manager():
    """Unit test for WebSocket ConnectionManager."""
    mgr = ConnectionManager()
    assert len(mgr.active) == 0

    # Create a mock WebSocket
    ws = AsyncMock()
    ws.accept = AsyncMock()
    await mgr.connect(ws)
    assert len(mgr.active) == 1

    # Broadcast should call send_json on all connected sockets
    await mgr.broadcast({"type": "test"})
    ws.send_json.assert_awaited_once_with({"type": "test"})

    # Disconnect
    mgr.disconnect(ws)
    assert len(mgr.active) == 0


@pytest.mark.asyncio
async def test_connection_manager_broadcast_removes_dead():
    """Broadcast removes sockets that raise on send."""
    mgr = ConnectionManager()

    ws_good = AsyncMock()
    ws_good.accept = AsyncMock()
    ws_bad = AsyncMock()
    ws_bad.accept = AsyncMock()
    ws_bad.send_json.side_effect = RuntimeError("dead socket")

    await mgr.connect(ws_good)
    await mgr.connect(ws_bad)
    assert len(mgr.active) == 2

    await mgr.broadcast({"type": "test"})
    # Bad socket should have been removed
    assert ws_bad not in mgr.active
    assert ws_good in mgr.active


# ── GPU polling unit test ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_poll_gpu_success():
    """_poll_gpu returns parsed GPU stats when nvidia-smi succeeds."""
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = "8192, 32768"

    with patch("src.server.asyncio.to_thread", new_callable=AsyncMock) as mock_thread:
        mock_thread.return_value = mock_result
        stats = await _poll_gpu()

    assert stats["used_gb"] == round(8192 / 1024, 2)
    assert stats["total_gb"] == round(32768 / 1024, 2)


@pytest.mark.asyncio
async def test_poll_gpu_failure():
    """_poll_gpu returns unknown stats when nvidia-smi fails."""
    with patch("src.server.asyncio.to_thread", new_callable=AsyncMock) as mock_thread:
        mock_thread.side_effect = FileNotFoundError("nvidia-smi not found")
        stats = await _poll_gpu()

    assert stats["status"] == "unknown"
    assert stats["used_gb"] == 0


@pytest.mark.asyncio
async def test_poll_gpu_vram_sanity_check():
    """_poll_gpu applies cascading /1024 correction when used > total * 2."""
    mock_result = MagicMock()
    mock_result.returncode = 0
    # Simulate a driver that returns bytes instead of MiB
    # used = 8589934592 (8 GiB in bytes), total = 32768 (32 GiB in MiB)
    # After first /1024: 8388608 -- still > 65536, so second /1024: 8192
    mock_result.stdout = "8589934592, 32768"

    with patch("src.server.asyncio.to_thread", new_callable=AsyncMock) as mock_thread:
        mock_thread.return_value = mock_result
        stats = await _poll_gpu()

    # After double /1024 on used: 8589934592 / 1024 / 1024 = 8192
    assert stats["used_gb"] == round(8192 / 1024, 2)
    assert stats["total_gb"] == round(32768 / 1024, 2)


# ── Colony creation with custom agents ──────────────────────────────────


@pytest.mark.asyncio
async def test_create_colony_with_agents(app_and_client):
    app, client = app_and_client
    resp = await client.post("/api/colony/custom-colony/create", json={
        "task": "Custom task",
        "agents": [
            {"agent_id": "arch_1", "caste": "architect"},
            {"agent_id": "code_1", "caste": "coder"},
        ],
        "max_rounds": 15,
    })
    assert resp.status_code == 200
    app.state.colony_manager.create.assert_awaited_once()

    # Verify the ColonyConfig passed to create()
    call_args = app.state.colony_manager.create.call_args
    config_arg = call_args[0][0]  # positional arg
    assert isinstance(config_arg, ColonyConfig)
    assert config_arg.colony_id == "custom-colony"
    assert config_arg.task == "Custom task"
    assert config_arg.max_rounds == 15
    assert len(config_arg.agents) == 2
    assert config_arg.agents[0].agent_id == "arch_1"


# ── Run with custom agents ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_run_with_custom_agents(app_and_client):
    app, client = app_and_client
    resp = await client.post("/api/run", json={
        "task": "Custom run task",
        "agents": [
            {"agent_id": "coder_1", "caste": "coder"},
        ],
        "max_rounds": 3,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "running"


# ── Skill create duplicate ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_skill_create_duplicate(app_and_client):
    app, client = app_and_client
    app.state.skill_bank.store_single.side_effect = ValueError("Duplicate")
    resp = await client.post("/api/skill-bank/skill", json={
        "content": "Duplicate skill",
        "tier": "general",
    })
    assert resp.status_code == 409
    data = resp.json()
    assert data["error_code"] == "SKILL_DUPLICATE"


# ── MCP reconnect when already connected ────────────────────────────────


@pytest.mark.asyncio
async def test_mcp_reconnect_disconnects_first(app_and_client):
    app, client = app_and_client
    app.state.mcp_client.connected = True
    app.state.mcp_client.connect = AsyncMock(return_value=True)
    app.state.mcp_client.disconnect = AsyncMock()
    app.state.mcp_client.get_tools.return_value = []

    resp = await client.post("/api/mcp/reconnect")
    assert resp.status_code == 200
    app.state.mcp_client.disconnect.assert_awaited_once()
    app.state.mcp_client.connect.assert_awaited_once()
