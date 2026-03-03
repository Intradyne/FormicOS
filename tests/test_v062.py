"""
FormicOS v0.6.2 -- Tests for Caste CRUD, Per-Agent MCP Tools, Workspace Browser

Covers:
  1.  CasteConfig validates with mcp_tools and subcaste_overrides
  2.  AgentConfig accepts string caste values (including custom like "dytopo")
  3.  AgentState caste validator normalizes to lowercase
  4.  BuiltinCaste enum includes DYTOPO
  5.  AgentFactory injects MCP tools filtered by caste config
  6.  AgentFactory with empty mcp_tools allows all MCP tools (dytopo behavior)
  7.  AgentFactory resolves per-caste subcaste overrides before global map
  8.  AgentFactory scoped MCP gateway callback blocks disallowed tools
  9.  SharedWorkspaceManager.list_files() returns entries, excludes .git
  10. SharedWorkspaceManager.read_file() reads text content
  11. SharedWorkspaceManager.read_file() sandbox-validated
  12. SharedWorkspaceManager.write_file() writes bytes
  13. Caste CRUD API: list castes
  14. Caste CRUD API: create caste
  15. Caste CRUD API: create duplicate caste rejected
  16. Caste CRUD API: update caste
  17. Caste CRUD API: update nonexistent caste returns 404
  18. Caste CRUD API: delete caste
  19. Caste CRUD API: delete manager caste blocked
  20. Caste CRUD API: delete nonexistent caste returns 404
  21. Workspace API: list files
  22. Workspace API: read file
  23. Workspace API: read file not found
  24. Workspace API: upload file
  25. Default colony creation uses manager + architect + coder
  26. Backward compatibility: existing caste names still work as strings
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from src.models import (
    AgentConfig,
    AgentState,
    BuiltinCaste,
    Caste,
    CasteConfig,
    ColonyConfig,
    ColonyStatus,
    FormicOSConfig,
    SubcasteMapEntry,
    SubcasteTier,
    load_config,
)
from src.stigmergy import SharedWorkspaceManager, SandboxViolationError


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════


def _make_test_config(tmp_path: Path) -> FormicOSConfig:
    """Build a minimal FormicOSConfig for testing, including dytopo caste."""
    session_dir = str(tmp_path / "sessions").replace("\\", "/")
    skill_file = str(tmp_path / "skills.json").replace("\\", "/")
    config_file = tmp_path / "formicos.yaml"
    config_file.write_text(f'''
schema_version: "0.6.0"
identity:
  name: FormicOS
  version: "0.6.2"
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
    mcp_tools: []
    model_override: null
    description: "Colony manager"
  architect:
    system_prompt_file: architect.md
    tools: [file_read]
    mcp_tools: [sequentialthinking_sequentialthinking]
    model_override: null
    description: "Solution architect"
  coder:
    system_prompt_file: coder.md
    tools: [file_read, file_write, code_execute]
    mcp_tools: [filesystem_read_file, filesystem_write_file]
    model_override: null
    description: "Code writer"
  dytopo:
    system_prompt_file: dytopo.md
    tools: [file_read, file_write, code_execute, fetch]
    mcp_tools: []
    model_override: null
    description: "Generalist agent"
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
  cloud/claude-opus:
    type: autoregressive
    backend: anthropic_api
    endpoint: https://api.anthropic.com/v1
    model_string: claude-opus-4-6
    context_length: 200000
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
''')
    return load_config(config_file)


def _mock_mcp_client(tools: list[dict] | None = None) -> MagicMock:
    """Create a mock MCPGatewayClient with tools."""
    mcp = MagicMock()
    mcp.connected = True
    mcp.connect_error = None
    mcp.connect = AsyncMock(return_value=True)
    mcp.disconnect = AsyncMock()
    mcp.get_tools.return_value = tools or [
        {"id": "sequentialthinking_sequentialthinking", "name": "sequentialthinking", "description": "Step-by-step reasoning", "parameters": {"type": "object", "properties": {}}, "enabled": True},
        {"id": "filesystem_read_file", "name": "read_file", "description": "Read a file", "parameters": {"type": "object", "properties": {}}, "enabled": True},
        {"id": "filesystem_write_file", "name": "write_file", "description": "Write a file", "parameters": {"type": "object", "properties": {}}, "enabled": True},
        {"id": "fetch_fetch", "name": "fetch", "description": "Fetch URL", "parameters": {"type": "object", "properties": {}}, "enabled": True},
        {"id": "tavily_search", "name": "search", "description": "Web search", "parameters": {"type": "object", "properties": {}}, "enabled": True},
    ]
    mcp.call_tool = AsyncMock(return_value="tool result")
    mcp.health_check = AsyncMock(return_value=True)
    return mcp


# ═══════════════════════════════════════════════════════════════════════════
# 1. CasteConfig validates with mcp_tools and subcaste_overrides
# ═══════════════════════════════════════════════════════════════════════════


def test_caste_config_with_mcp_tools_and_subcaste_overrides():
    """CasteConfig should validate with mcp_tools list and subcaste_overrides dict."""
    cc = CasteConfig(
        system_prompt_file="custom.md",
        tools=["file_read", "file_write"],
        mcp_tools=["filesystem_read_file", "tavily_search"],
        model_override=None,
        subcaste_overrides={
            "heavy": SubcasteMapEntry(primary="cloud/claude-opus"),
        },
        description="A custom caste for testing",
    )
    assert cc.mcp_tools == ["filesystem_read_file", "tavily_search"]
    assert "heavy" in cc.subcaste_overrides
    assert cc.subcaste_overrides["heavy"].primary == "cloud/claude-opus"
    assert cc.description == "A custom caste for testing"


def test_caste_config_empty_mcp_tools():
    """CasteConfig with empty mcp_tools should validate (means all MCP tools allowed)."""
    cc = CasteConfig(
        system_prompt_file="dytopo.md",
        tools=["file_read"],
        mcp_tools=[],
    )
    assert cc.mcp_tools == []
    assert cc.subcaste_overrides == {}
    assert cc.description == ""


# ═══════════════════════════════════════════════════════════════════════════
# 2. AgentConfig accepts string caste values
# ═══════════════════════════════════════════════════════════════════════════


def test_agent_config_string_caste():
    """AgentConfig should accept free-form string caste values like 'dytopo'."""
    ac = AgentConfig(agent_id="dytopo_001", caste="dytopo")
    assert ac.caste == "dytopo"

    ac2 = AgentConfig(agent_id="custom_001", caste="Designer")
    assert ac2.caste == "designer"  # lowercased by validator

    ac3 = AgentConfig(agent_id="arch_001", caste="architect")
    assert ac3.caste == "architect"


# ═══════════════════════════════════════════════════════════════════════════
# 3. AgentState caste validator normalizes to lowercase
# ═══════════════════════════════════════════════════════════════════════════


def test_agent_state_caste_lowercase():
    """AgentState caste field should be normalized to lowercase."""
    state = AgentState(agent_id="test_001", caste="DYTOPO")
    assert state.caste == "dytopo"

    state2 = AgentState(agent_id="test_002", caste="  Architect  ")
    assert state2.caste == "architect"


# ═══════════════════════════════════════════════════════════════════════════
# 4. BuiltinCaste enum includes DYTOPO
# ═══════════════════════════════════════════════════════════════════════════


def test_builtin_caste_includes_dytopo():
    """BuiltinCaste enum should include DYTOPO value."""
    assert BuiltinCaste.DYTOPO.value == "dytopo"
    # Backward compat alias
    assert Caste.DYTOPO.value == "dytopo"
    # All original castes still exist
    assert BuiltinCaste.MANAGER.value == "manager"
    assert BuiltinCaste.ARCHITECT.value == "architect"
    assert BuiltinCaste.CODER.value == "coder"
    assert BuiltinCaste.REVIEWER.value == "reviewer"
    assert BuiltinCaste.RESEARCHER.value == "researcher"


# ═══════════════════════════════════════════════════════════════════════════
# 5. AgentFactory injects MCP tools filtered by caste config
# ═══════════════════════════════════════════════════════════════════════════


def test_agent_factory_filters_mcp_tools(tmp_path: Path):
    """AgentFactory should only inject MCP tools that match the caste's mcp_tools list."""
    from src.agents import AgentFactory

    config = _make_test_config(tmp_path)
    mcp = _mock_mcp_client()

    factory = AgentFactory(
        model_registry=config.model_registry,
        config=config,
        mcp_client=mcp,
    )

    # Architect caste only has sequentialthinking_sequentialthinking in mcp_tools
    agent = factory.create(agent_id="arch_01", caste="architect")

    # Should have file_read (builtin) + sequentialthinking (MCP)
    tool_ids = [t["id"] for t in agent.tools]
    assert "file_read" in tool_ids
    assert "sequentialthinking_sequentialthinking" in tool_ids
    # Should NOT have filesystem or tavily tools
    assert "filesystem_read_file" not in tool_ids
    assert "tavily_search" not in tool_ids


# ═══════════════════════════════════════════════════════════════════════════
# 6. AgentFactory with empty mcp_tools allows all MCP tools (dytopo)
# ═══════════════════════════════════════════════════════════════════════════


def test_agent_factory_empty_mcp_tools_allows_all(tmp_path: Path):
    """Empty mcp_tools list should include ALL MCP tools (dytopo behavior)."""
    from src.agents import AgentFactory

    config = _make_test_config(tmp_path)
    mcp = _mock_mcp_client()

    factory = AgentFactory(
        model_registry=config.model_registry,
        config=config,
        mcp_client=mcp,
    )

    # Dytopo caste has empty mcp_tools → all MCP tools
    agent = factory.create(agent_id="dytopo_01", caste="dytopo")

    tool_ids = [t["id"] for t in agent.tools]
    # All 5 MCP tools should be present
    assert "sequentialthinking_sequentialthinking" in tool_ids
    assert "filesystem_read_file" in tool_ids
    assert "filesystem_write_file" in tool_ids
    assert "fetch_fetch" in tool_ids
    assert "tavily_search" in tool_ids
    # Plus the builtin tools from caste config
    assert "file_read" in tool_ids
    assert "file_write" in tool_ids


# ═══════════════════════════════════════════════════════════════════════════
# 7. AgentFactory resolves per-caste subcaste overrides before global map
# ═══════════════════════════════════════════════════════════════════════════


def test_agent_factory_per_caste_subcaste_overrides(tmp_path: Path):
    """Per-caste subcaste_overrides should take precedence over global subcaste_map."""
    from src.agents import AgentFactory

    config = _make_test_config(tmp_path)

    # Add a per-caste subcaste override for architect heavy → cloud/claude-opus
    config.castes["architect"].subcaste_overrides = {
        "heavy": SubcasteMapEntry(primary="cloud/claude-opus"),
    }

    factory = AgentFactory(
        model_registry=config.model_registry,
        config=config,
    )

    # Create architect with heavy subcaste → should use cloud/claude-opus
    agent = factory.create(
        agent_id="arch_heavy",
        caste="architect",
        subcaste_tier=SubcasteTier.HEAVY,
    )
    # The model_name should be the cloud model's model_string
    assert agent.model_name == "claude-opus-4-6"

    # Create architect with balanced subcaste → should use global map (test/model)
    agent_balanced = factory.create(
        agent_id="arch_balanced",
        caste="architect",
        subcaste_tier=SubcasteTier.BALANCED,
    )
    assert agent_balanced.model_name == "test/model"


# ═══════════════════════════════════════════════════════════════════════════
# 8. AgentFactory scoped MCP gateway callback blocks disallowed tools
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_agent_factory_mcp_callback_scoped(tmp_path: Path):
    """MCP gateway callback should reject tools not in the caste's allowed set."""
    from src.agents import AgentFactory

    config = _make_test_config(tmp_path)
    mcp = _mock_mcp_client()

    factory = AgentFactory(
        model_registry=config.model_registry,
        config=config,
        mcp_client=mcp,
    )

    # Coder caste has mcp_tools: [filesystem_read_file, filesystem_write_file]
    agent = factory.create(agent_id="coder_01", caste="coder")

    # The callback should exist
    assert agent.mcp_gateway_callback is not None

    # Allowed tool should pass through
    result = await agent.mcp_gateway_callback("filesystem_read_file", {"path": "test.py"})
    assert result == "tool result"

    # Disallowed tool should be rejected
    result = await agent.mcp_gateway_callback("tavily_search", {"query": "test"})
    assert "not assigned" in result.lower() or "ERROR" in result

    # Dytopo caste has empty mcp_tools → None allowed set → all pass
    dytopo_agent = factory.create(agent_id="dytopo_01", caste="dytopo")
    assert dytopo_agent.mcp_gateway_callback is not None
    result = await dytopo_agent.mcp_gateway_callback("tavily_search", {"query": "test"})
    assert result == "tool result"


# ═══════════════════════════════════════════════════════════════════════════
# 9. SharedWorkspaceManager.list_files() returns entries, excludes .git
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_workspace_list_files(tmp_path: Path):
    """list_files() should return file entries and exclude .git."""
    ws = tmp_path / "workspace"
    ws.mkdir()

    # Create some files and a .git dir
    (ws / "output.txt").write_text("hello")
    (ws / "data.json").write_text("{}")
    (ws / "subdir").mkdir()
    (ws / "subdir" / "nested.py").write_text("pass")
    (ws / ".git").mkdir()
    (ws / ".git" / "config").write_text("[core]")

    mgr = SharedWorkspaceManager(ws)
    entries = await mgr.list_files()

    names = [e["name"] for e in entries]
    assert "output.txt" in names
    assert "data.json" in names
    assert "subdir" in names
    assert ".git" not in names

    # Check entry structure
    txt_entry = next(e for e in entries if e["name"] == "output.txt")
    assert txt_entry["is_dir"] is False
    assert txt_entry["size"] > 0
    assert "path" in txt_entry
    assert "modified" in txt_entry

    dir_entry = next(e for e in entries if e["name"] == "subdir")
    assert dir_entry["is_dir"] is True


@pytest.mark.asyncio
async def test_workspace_list_files_subpath(tmp_path: Path):
    """list_files() with subpath should list files in a subdirectory."""
    ws = tmp_path / "workspace"
    ws.mkdir()
    (ws / "subdir").mkdir()
    (ws / "subdir" / "nested.py").write_text("pass")
    (ws / "subdir" / "data.csv").write_text("a,b")

    mgr = SharedWorkspaceManager(ws)
    entries = await mgr.list_files("subdir")

    names = [e["name"] for e in entries]
    assert "nested.py" in names
    assert "data.csv" in names
    assert len(entries) == 2


# ═══════════════════════════════════════════════════════════════════════════
# 10. SharedWorkspaceManager.read_file() reads text content
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_workspace_read_file(tmp_path: Path):
    """read_file() should return file content as text."""
    ws = tmp_path / "workspace"
    ws.mkdir()
    (ws / "hello.txt").write_text("Hello, FormicOS!")

    mgr = SharedWorkspaceManager(ws)
    content = await mgr.read_file("hello.txt")
    assert content == "Hello, FormicOS!"


@pytest.mark.asyncio
async def test_workspace_read_file_not_found(tmp_path: Path):
    """read_file() should raise FileNotFoundError for missing files."""
    ws = tmp_path / "workspace"
    ws.mkdir()

    mgr = SharedWorkspaceManager(ws)
    with pytest.raises(FileNotFoundError):
        await mgr.read_file("nonexistent.txt")


# ═══════════════════════════════════════════════════════════════════════════
# 11. SharedWorkspaceManager.read_file() sandbox-validated
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_workspace_read_file_sandbox(tmp_path: Path):
    """read_file() should reject paths outside workspace."""
    ws = tmp_path / "workspace"
    ws.mkdir()

    mgr = SharedWorkspaceManager(ws)
    with pytest.raises(SandboxViolationError):
        await mgr.read_file("../../etc/passwd")


# ═══════════════════════════════════════════════════════════════════════════
# 12. SharedWorkspaceManager.write_file() writes bytes
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_workspace_write_file(tmp_path: Path):
    """write_file() should write content and return bytes written."""
    ws = tmp_path / "workspace"
    ws.mkdir()

    mgr = SharedWorkspaceManager(ws)
    content = b"uploaded content here"
    written = await mgr.write_file("upload.txt", content)
    assert written == len(content)
    assert (ws / "upload.txt").read_bytes() == content


@pytest.mark.asyncio
async def test_workspace_write_file_creates_dirs(tmp_path: Path):
    """write_file() should create parent directories as needed."""
    ws = tmp_path / "workspace"
    ws.mkdir()

    mgr = SharedWorkspaceManager(ws)
    content = b"nested content"
    written = await mgr.write_file("deep/nested/file.txt", content)
    assert written == len(content)
    assert (ws / "deep" / "nested" / "file.txt").read_bytes() == content


@pytest.mark.asyncio
async def test_workspace_write_file_sandbox(tmp_path: Path):
    """write_file() should reject paths outside workspace."""
    ws = tmp_path / "workspace"
    ws.mkdir()

    mgr = SharedWorkspaceManager(ws)
    with pytest.raises(SandboxViolationError):
        await mgr.write_file("../../evil.txt", b"escape attempt")


# ═══════════════════════════════════════════════════════════════════════════
# Server API Tests — Fixtures
# ═══════════════════════════════════════════════════════════════════════════


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
    info_mock.agent_count = 1
    info_mock.teams = []
    info_mock.created_at = time.time()
    info_mock.updated_at = time.time()
    info_mock.model_dump.return_value = {
        "colony_id": "test-colony",
        "task": "test task",
        "status": "created",
        "round": 0,
        "max_rounds": 10,
        "agent_count": 1,
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

    from src.context import AsyncContextTree
    cm.get_context = MagicMock(return_value=AsyncContextTree())
    return cm


def _mock_model_registry() -> MagicMock:
    mr = MagicMock()
    mr.list_models.return_value = {
        "test/model": {
            "type": "autoregressive",
            "backend": "llama_cpp",
            "endpoint": "http://localhost:8080/v1",
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
    return mr


def _mock_server_mcp_client() -> MagicMock:
    mcp = MagicMock()
    mcp.connected = False
    mcp.connect_error = None
    mcp.connect = AsyncMock(return_value=True)
    mcp.disconnect = AsyncMock()
    mcp.get_tools.return_value = []
    mcp.health_check = AsyncMock(return_value=True)
    return mcp


@pytest.fixture
async def v062_app_and_client(tmp_path):
    """Create a test app with v0.6.2 config and mocked services."""
    from src.context import AsyncContextTree
    from src.server import create_app
    from src.models import Skill, SkillTier

    config = _make_test_config(tmp_path)

    # Create prompt files so caste CRUD endpoints can read them
    prompts_dir = Path("config/prompts")
    prompts_dir.mkdir(parents=True, exist_ok=True)

    app = create_app(config)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        app.state.colony_manager = _mock_colony_manager()
        app.state.model_registry = _mock_model_registry()
        app.state.mcp_client = _mock_server_mcp_client()
        app.state.gpu_stats = {"used_gb": 10.5, "total_gb": 32.0}

        # Mock session manager
        sm = MagicMock()
        sm.list_sessions = AsyncMock(return_value=[])
        sm.delete_session = AsyncMock()
        app.state.session_manager = sm

        # Mock skill bank
        sb = MagicMock()
        sb.get_all.return_value = {"general": [], "task_specific": [], "lesson": []}
        sb.store_single.return_value = "gen_test"
        sb._find_skill.return_value = Skill(
            skill_id="gen_test", content="Test", tier=SkillTier.GENERAL,
        )
        app.state.skill_bank = sb

        # Mock approval gate
        gate = MagicMock()
        gate.respond.return_value = None
        app.state.approval_gate = gate

        # Mock audit logger
        al = MagicMock()
        al.flush = AsyncMock()
        al.close = AsyncMock()
        app.state.audit_logger = al

        if not hasattr(app.state, "ctx"):
            app.state.ctx = AsyncContextTree()

        # Ensure config is available (lifespan sets it, but we need it immediately)
        app.state.config = config

        yield app, client


# ═══════════════════════════════════════════════════════════════════════════
# 13. Caste CRUD API: list castes
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_api_list_castes(v062_app_and_client):
    """GET /api/castes should return all castes with config."""
    app, client = v062_app_and_client
    resp = await client.get("/api/castes")
    assert resp.status_code == 200
    data = resp.json()
    assert "manager" in data
    assert "dytopo" in data
    assert "architect" in data
    assert "coder" in data
    # Check structure
    assert "tools" in data["coder"]
    assert "mcp_tools" in data["coder"]
    assert "description" in data["manager"]


# ═══════════════════════════════════════════════════════════════════════════
# 14. Caste CRUD API: create caste
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_api_create_caste(v062_app_and_client, tmp_path):
    """POST /api/castes should create a new caste."""
    app, client = v062_app_and_client
    resp = await client.post("/api/castes", json={
        "name": "designer",
        "system_prompt": "You are a UI/UX designer agent.",
        "tools": ["file_read", "file_write"],
        "mcp_tools": ["fetch_fetch"],
        "description": "UI/UX design specialist",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "designer"
    assert data["status"] == "created"

    # Verify the caste is now in config
    config: FormicOSConfig = app.state.config
    assert "designer" in config.castes
    assert config.castes["designer"].description == "UI/UX design specialist"
    assert config.castes["designer"].mcp_tools == ["fetch_fetch"]

    # Verify prompt file was created
    prompt_path = Path("config/prompts/designer.md")
    assert prompt_path.exists()
    assert "UI/UX designer" in prompt_path.read_text()

    # Cleanup
    if prompt_path.exists():
        prompt_path.unlink()


# ═══════════════════════════════════════════════════════════════════════════
# 15. Caste CRUD API: create duplicate caste rejected
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_api_create_duplicate_caste(v062_app_and_client):
    """POST /api/castes with existing name should return 409."""
    app, client = v062_app_and_client
    resp = await client.post("/api/castes", json={
        "name": "manager",
        "system_prompt": "duplicate",
    })
    assert resp.status_code == 409
    data = resp.json()
    assert data["error_code"] == "CASTE_EXISTS"


# ═══════════════════════════════════════════════════════════════════════════
# 16. Caste CRUD API: update caste
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_api_update_caste(v062_app_and_client):
    """PUT /api/castes/{name} should update caste config."""
    app, client = v062_app_and_client
    resp = await client.put("/api/castes/coder", json={
        "tools": ["file_read", "file_write", "code_execute", "fetch"],
        "description": "Updated coder description",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "updated"

    config: FormicOSConfig = app.state.config
    assert "fetch" in config.castes["coder"].tools
    assert config.castes["coder"].description == "Updated coder description"


# ═══════════════════════════════════════════════════════════════════════════
# 17. Caste CRUD API: update nonexistent caste returns 404
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_api_update_nonexistent_caste(v062_app_and_client):
    """PUT /api/castes/{name} for nonexistent caste should return 404."""
    app, client = v062_app_and_client
    resp = await client.put("/api/castes/nonexistent", json={
        "description": "nope",
    })
    assert resp.status_code == 404
    data = resp.json()
    assert data["error_code"] == "CASTE_NOT_FOUND"


# ═══════════════════════════════════════════════════════════════════════════
# 18. Caste CRUD API: delete caste
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_api_delete_caste(v062_app_and_client, tmp_path):
    """DELETE /api/castes/{name} should remove caste and prompt file."""
    app, client = v062_app_and_client

    # First create a caste to delete
    resp = await client.post("/api/castes", json={
        "name": "throwaway",
        "system_prompt": "temporary caste",
    })
    assert resp.status_code == 200

    # Now delete it
    resp = await client.delete("/api/castes/throwaway")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "deleted"

    config: FormicOSConfig = app.state.config
    assert "throwaway" not in config.castes


# ═══════════════════════════════════════════════════════════════════════════
# 19. Caste CRUD API: delete manager caste blocked
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_api_delete_manager_blocked(v062_app_and_client):
    """DELETE /api/castes/manager should return 403."""
    app, client = v062_app_and_client
    resp = await client.delete("/api/castes/manager")
    assert resp.status_code == 403
    data = resp.json()
    assert data["error_code"] == "PROTECTED_CASTE"


# ═══════════════════════════════════════════════════════════════════════════
# 20. Caste CRUD API: delete nonexistent caste returns 404
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_api_delete_nonexistent_caste(v062_app_and_client):
    """DELETE /api/castes/{name} for nonexistent caste should return 404."""
    app, client = v062_app_and_client
    resp = await client.delete("/api/castes/nonexistent")
    assert resp.status_code == 404


# ═══════════════════════════════════════════════════════════════════════════
# 21. Workspace API: list files
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_api_workspace_list_files(v062_app_and_client, tmp_path):
    """GET /api/workspace/{colony_id}/files should list workspace files."""
    app, client = v062_app_and_client

    # Create workspace directory with files
    ws = Path("./workspace/test-colony")
    ws.mkdir(parents=True, exist_ok=True)
    try:
        (ws / "result.txt").write_text("colony output")
        (ws / "code.py").write_text("print('hello')")

        resp = await client.get("/api/workspace/test-colony/files")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        names = [e["name"] for e in data]
        assert "result.txt" in names
        assert "code.py" in names
    finally:
        # Cleanup
        import shutil
        if ws.exists():
            shutil.rmtree(ws)


# ═══════════════════════════════════════════════════════════════════════════
# 22. Workspace API: read file
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_api_workspace_read_file(v062_app_and_client):
    """GET /api/workspace/{colony_id}/file should read file content."""
    app, client = v062_app_and_client

    ws = Path("./workspace/read-colony")
    ws.mkdir(parents=True, exist_ok=True)
    try:
        (ws / "readme.txt").write_text("Hello from workspace")

        resp = await client.get(
            "/api/workspace/read-colony/file",
            params={"path": "readme.txt"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["content"] == "Hello from workspace"
        assert data["path"] == "readme.txt"
    finally:
        import shutil
        if ws.exists():
            shutil.rmtree(ws)


# ═══════════════════════════════════════════════════════════════════════════
# 23. Workspace API: read file not found
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_api_workspace_read_file_not_found(v062_app_and_client):
    """GET /api/workspace/{colony_id}/file for missing file should return 404."""
    app, client = v062_app_and_client

    ws = Path("./workspace/notfound-colony")
    ws.mkdir(parents=True, exist_ok=True)
    try:
        resp = await client.get(
            "/api/workspace/notfound-colony/file",
            params={"path": "missing.txt"},
        )
        assert resp.status_code == 404
        data = resp.json()
        assert data["error_code"] == "FILE_NOT_FOUND"
    finally:
        import shutil
        if ws.exists():
            shutil.rmtree(ws)


# ═══════════════════════════════════════════════════════════════════════════
# 24. Workspace API: upload file
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_api_workspace_upload_file(v062_app_and_client):
    """POST /api/workspace/{colony_id}/upload should write file."""
    app, client = v062_app_and_client

    ws = Path("./workspace/upload-colony")
    try:
        resp = await client.post(
            "/api/workspace/upload-colony/upload",
            content=b"uploaded file content",
            headers={"X-Filename": "uploaded.txt"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["path"] == "uploaded.txt"
        assert data["bytes_written"] == len(b"uploaded file content")

        # Verify file exists
        assert (ws / "uploaded.txt").read_bytes() == b"uploaded file content"
    finally:
        import shutil
        if ws.exists():
            shutil.rmtree(ws)


@pytest.mark.asyncio
async def test_api_workspace_upload_missing_filename(v062_app_and_client):
    """POST /api/workspace/{colony_id}/upload without X-Filename should return 400."""
    app, client = v062_app_and_client

    resp = await client.post(
        "/api/workspace/upload-colony/upload",
        content=b"data",
    )
    assert resp.status_code == 400
    data = resp.json()
    assert data["error_code"] == "MISSING_FILENAME"


# ═══════════════════════════════════════════════════════════════════════════
# 25. Default colony creation uses manager + architect + coder
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_default_colony_uses_multi_agent_team(v062_app_and_client):
    """POST /api/colony/{id}/create with no agents should default to manager + architect + coder."""
    app, client = v062_app_and_client
    resp = await client.post("/api/colony/default-colony/create", json={
        "task": "Test default agents",
    })
    assert resp.status_code == 200

    # Check the ColonyConfig passed to cm.create()
    call_args = app.state.colony_manager.create.call_args
    config_arg = call_args[0][0]
    assert isinstance(config_arg, ColonyConfig)
    assert len(config_arg.agents) == 3
    castes = [a.caste for a in config_arg.agents]
    assert "manager" in castes
    assert "architect" in castes
    assert "coder" in castes


@pytest.mark.asyncio
async def test_default_run_uses_multi_agent_team(v062_app_and_client):
    """POST /api/run with no agents should default to manager + architect + coder."""
    app, client = v062_app_and_client
    resp = await client.post("/api/run", json={
        "task": "Test default run",
    })
    assert resp.status_code == 200

    call_args = app.state.colony_manager.create.call_args
    config_arg = call_args[0][0]
    assert len(config_arg.agents) == 3
    castes = [a.caste for a in config_arg.agents]
    assert "manager" in castes
    assert "architect" in castes
    assert "coder" in castes


# ═══════════════════════════════════════════════════════════════════════════
# 26. Backward compatibility: existing caste names still work as strings
# ═══════════════════════════════════════════════════════════════════════════


def test_backward_compat_caste_names():
    """All original BuiltinCaste enum values should work as plain strings."""
    for bc in BuiltinCaste:
        # AgentConfig should accept both enum and string
        ac = AgentConfig(agent_id=f"test_{bc.value}", caste=bc.value)
        assert ac.caste == bc.value

        # AgentState should accept both
        state = AgentState(agent_id=f"test_{bc.value}", caste=bc.value)
        assert state.caste == bc.value


def test_backward_compat_caste_alias():
    """Caste alias should still point to BuiltinCaste."""
    assert Caste is BuiltinCaste
    assert Caste.MANAGER is BuiltinCaste.MANAGER
    assert Caste.CODER is BuiltinCaste.CODER


def test_config_loads_with_dytopo_caste(tmp_path: Path):
    """FormicOSConfig should load correctly with dytopo caste defined."""
    config = _make_test_config(tmp_path)
    assert "dytopo" in config.castes
    assert config.castes["dytopo"].description == "Generalist agent"
    assert config.castes["dytopo"].mcp_tools == []
    assert "file_read" in config.castes["dytopo"].tools
    assert "cloud/claude-opus" in config.model_registry
    assert config.model_registry["cloud/claude-opus"].backend.value == "anthropic_api"


# ═══════════════════════════════════════════════════════════════════════════
# 27. Suggest Team API
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_suggest_team_returns_agents(v062_app_and_client):
    """POST /api/suggest-team should return agent suggestions."""
    app, client = v062_app_and_client

    # Mock the AsyncOpenAI call
    llm_response = json.dumps({
        "agents": [
            {"caste": "architect", "subcaste_tier": "balanced"},
            {"caste": "coder", "subcaste_tier": "balanced"},
            {"caste": "reviewer", "subcaste_tier": "light"},
        ],
        "colony_name": "snake-game",
        "max_rounds": 8,
    })

    mock_choice = MagicMock()
    mock_choice.message.content = llm_response
    mock_completion = MagicMock()
    mock_completion.choices = [mock_choice]

    app.state.aio_session = MagicMock()  # v0.8.0: shared aiohttp session

    with patch("src.llm_client.AioLLMClient") as mock_openai_cls:
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_completion)
        mock_openai_cls.return_value = mock_client

        resp = await client.post("/api/suggest-team", json={
            "task": "Build a snake game in Python",
        })
        assert resp.status_code == 200
        data = resp.json()

        assert len(data["agents"]) == 3
        castes = [a["caste"] for a in data["agents"]]
        assert "architect" in castes
        assert "coder" in castes
        assert "reviewer" in castes
        assert data["colony_name"] == "snake-game"
        assert data["max_rounds"] == 8


@pytest.mark.asyncio
async def test_suggest_team_llm_failure_returns_defaults(v062_app_and_client):
    """POST /api/suggest-team should return defaults if LLM fails."""
    app, client = v062_app_and_client

    app.state.aio_session = MagicMock()  # v0.8.0: shared aiohttp session

    with patch("src.llm_client.AioLLMClient") as mock_openai_cls:
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(
            side_effect=Exception("LLM unavailable")
        )
        mock_openai_cls.return_value = mock_client

        resp = await client.post("/api/suggest-team", json={
            "task": "Some task",
        })
        assert resp.status_code == 200
        data = resp.json()

        # Should get sensible defaults
        assert len(data["agents"]) >= 2
        assert "colony_name" in data
        assert data["max_rounds"] == 5


# ═══════════════════════════════════════════════════════════════════════════
# 28. Agent.execute_raw() direct LLM call
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_execute_raw_returns_direct_llm_output():
    """execute_raw() should make a direct LLM call and return raw content."""
    from src.agents import Agent

    mock_client = AsyncMock()
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = '{"goal": "Write snake game", "terminate": false}'
    mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

    agent = Agent(
        id="manager_01",
        caste="manager",
        system_prompt="You are a manager.",
        model_client=mock_client,
        model_name="test-model",
    )

    result = await agent.execute_raw(
        system_override="Custom system prompt",
        user_prompt="Set a goal for round 0",
    )

    assert "goal" in result
    assert "Write snake game" in result
    # Verify the call used the overridden system prompt
    call_args = mock_client.chat.completions.create.call_args
    messages = call_args.kwargs["messages"]
    assert messages[0]["content"] == "Custom system prompt"
    assert messages[1]["content"] == "Set a goal for round 0"


@pytest.mark.asyncio
async def test_execute_raw_returns_empty_on_failure():
    """execute_raw() should return '{}' on LLM failure."""
    from src.agents import Agent

    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(
        side_effect=Exception("LLM down")
    )

    agent = Agent(
        id="manager_01",
        caste="manager",
        system_prompt="You are a manager.",
        model_client=mock_client,
        model_name="test-model",
    )

    result = await agent.execute_raw(
        system_override="System",
        user_prompt="Goal?",
    )
    assert result == "{}"


# ═══════════════════════════════════════════════════════════════════════════
# 29. Round 0 broadcast topology
# ═══════════════════════════════════════════════════════════════════════════


def test_broadcast_topology_creates_no_edges():
    """_broadcast_topology should create a topology with no edges."""
    from src.orchestrator import Orchestrator
    from src.agents import Agent

    mock_client = AsyncMock()
    workers = [
        Agent(id="arch_01", caste="architect", system_prompt="", model_client=mock_client, model_name="m"),
        Agent(id="coder_01", caste="coder", system_prompt="", model_client=mock_client, model_name="m"),
    ]

    topo = Orchestrator._broadcast_topology(workers)

    assert len(topo.edges) == 0
    assert set(topo.execution_order) == {"arch_01", "coder_01"}
    assert topo.density == 0.0


# ═══════════════════════════════════════════════════════════════════════════
# 30. Intent generation produces role-enriched descriptors
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_generate_intent_role_enriched():
    """generate_intent() should produce role-enriched key/query descriptors."""
    from src.agents import Agent

    mock_client = AsyncMock()
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = json.dumps({
        "key": "Python snake_game.py with Game class",
        "query": "Architecture design with class hierarchy",
    })
    mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

    agent = Agent(
        id="coder_01",
        caste="coder",
        system_prompt="You are a coder.",
        model_client=mock_client,
        model_name="test-model",
    )

    intent = await agent.generate_intent("Make a snake game")

    # Should be role-enriched
    assert intent["key"].startswith("As a coder:")
    assert "snake_game.py" in intent["key"]
    assert intent["query"].startswith("As a coder:")
    assert "class hierarchy" in intent["query"]


# ═══════════════════════════════════════════════════════════════════════════
# 31. Worker execution produces plain text output
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_worker_execute_plain_text_output():
    """Workers should accept plain text output, not require JSON wrapping."""
    from src.agents import Agent

    mock_client = AsyncMock()

    # Simulate streaming response with plain text (no JSON)
    plain_code = "def snake_game():\n    print('Hello snake!')\n\nsnake_game()"

    async def mock_stream(*args, **kwargs):
        class MockChunk:
            def __init__(self, content=None, finish=None):
                self.choices = [MagicMock()]
                self.choices[0].delta = MagicMock()
                self.choices[0].delta.content = content
                self.choices[0].delta.tool_calls = None
                self.choices[0].finish_reason = finish
                self.usage = None

        class MockStream:
            def __init__(self):
                self.chunks = [
                    MockChunk(content=plain_code),
                    MockChunk(finish="stop"),
                ]
                self.idx = 0

            def __aiter__(self):
                return self

            async def __anext__(self):
                if self.idx >= len(self.chunks):
                    raise StopAsyncIteration
                chunk = self.chunks[self.idx]
                self.idx += 1
                return chunk

        return MockStream()

    mock_client.chat.completions.create = mock_stream

    agent = Agent(
        id="coder_01",
        caste="coder",
        system_prompt="You are a coder.",
        model_client=mock_client,
        model_name="test-model",
    )

    output = await agent.execute(
        context="Project context",
        round_goal="Write a snake game",
    )

    # Plain text output should be captured directly
    assert "snake_game" in output.output
    assert "Hello snake" in output.output


# ═══════════════════════════════════════════════════════════════════════════
# 32. Fallback final answer extraction
# ═══════════════════════════════════════════════════════════════════════════


def test_chain_topology_creates_edges():
    """_chain_topology should create linear chain edges."""
    from src.orchestrator import Orchestrator

    topo = Orchestrator._chain_topology(["arch_01", "coder_01", "reviewer_01"])

    assert len(topo.edges) == 2
    assert topo.edges[0].sender == "arch_01"
    assert topo.edges[0].receiver == "coder_01"
    assert topo.edges[1].sender == "coder_01"
    assert topo.edges[1].receiver == "reviewer_01"
    assert topo.execution_order == ["arch_01", "coder_01", "reviewer_01"]
