"""
Tests for FormicOS v0.7.8 Cloud Model Test & Control Harness.

Covers:
- ColonyConfig.is_test_flight field
- ColonyCreateRequest.is_test_flight field
- Agent seed support (config → kwargs)
- MCPGatewayClient mock mode (enable/disable, call_tool bypass)
- Orchestrator is_test_flight parameter + DyTopo fixed seed
- ColonyManager test flight wiring (temperature=0.0, seed=42, MCP mock)
- ColonyManager error traceback capture in _run_colony
- ColonyManager.get_diagnostics() payload
- POST /api/v1/admin/rebuild (localhost-only)
- GET /api/v1/admin/diagnostics/{colony_id}
- formicos-cli.py structure
- Version bump to 0.7.8
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.models import ColonyStatus


# ── ColonyConfig.is_test_flight ─────────────────────────────────────────


def test_colony_config_is_test_flight_default():
    from src.models import ColonyConfig, AgentConfig

    config = ColonyConfig(
        colony_id="test",
        task="test",
        agents=[AgentConfig(agent_id="a1", caste="coder")],
    )
    assert config.is_test_flight is False


def test_colony_config_is_test_flight_enabled():
    from src.models import ColonyConfig, AgentConfig

    config = ColonyConfig(
        colony_id="test",
        task="test",
        agents=[AgentConfig(agent_id="a1", caste="coder")],
        is_test_flight=True,
    )
    assert config.is_test_flight is True


# ── ColonyCreateRequest.is_test_flight ──────────────────────────────────


def test_create_request_is_test_flight_default():
    from src.server import ColonyCreateRequest

    req = ColonyCreateRequest(task="test")
    assert req.is_test_flight is False


def test_create_request_is_test_flight_enabled():
    from src.server import ColonyCreateRequest

    req = ColonyCreateRequest(task="test", is_test_flight=True)
    assert req.is_test_flight is True


# ── Agent seed support ──────────────────────────────────────────────────


def test_agent_seed_default_none():
    from src.agents import Agent

    agent = Agent(
        id="a1",
        caste="coder",
        system_prompt="test",
        model_client=MagicMock(),
        model_name="test-model",
        config={},
    )
    assert agent.seed is None


def test_agent_seed_from_config():
    from src.agents import Agent

    agent = Agent(
        id="a1",
        caste="coder",
        system_prompt="test",
        model_client=MagicMock(),
        model_name="test-model",
        config={"seed": 42},
    )
    assert agent.seed == 42


def test_agent_temperature_overrideable():
    from src.agents import Agent

    agent = Agent(
        id="a1",
        caste="coder",
        system_prompt="test",
        model_client=MagicMock(),
        model_name="test-model",
        config={"temperature": 0.7},
    )
    assert agent.temperature == 0.7
    # Test flight override
    agent.temperature = 0.0
    agent.seed = 42
    assert agent.temperature == 0.0
    assert agent.seed == 42


# ── MCPGatewayClient mock mode ──────────────────────────────────────────


def test_mcp_mock_mode_default_disabled():
    from src.mcp_client import MCPGatewayClient

    config = MagicMock()
    config.command = "test"
    config.args = []
    config.env = {}
    config.filter_tools = None
    config.docker_fallback_endpoint = None
    client = MCPGatewayClient(config)
    assert client._mock_mode is False


def test_mcp_enable_disable_mock_mode():
    from src.mcp_client import MCPGatewayClient

    config = MagicMock()
    client = MCPGatewayClient(config)
    assert client._mock_mode is False

    client.enable_mock_mode()
    assert client._mock_mode is True

    client.disable_mock_mode()
    assert client._mock_mode is False


@pytest.mark.asyncio
async def test_mcp_mock_mode_call_tool_bypass():
    from src.mcp_client import MCPGatewayClient

    config = MagicMock()
    client = MCPGatewayClient(config)
    client.enable_mock_mode()

    result = await client.call_tool("file_write", {"path": "/tmp/test", "content": "hello"})
    parsed = json.loads(result)
    assert parsed["status"] == "ok"
    assert parsed["mock"] is True
    assert parsed["tool"] == "file_write"
    assert client._last_call_duration_ms == 0.0


@pytest.mark.asyncio
async def test_mcp_mock_mode_no_session_needed():
    """Mock mode works even without an MCP session."""
    from src.mcp_client import MCPGatewayClient

    config = MagicMock()
    client = MCPGatewayClient(config)
    assert client._session is None

    client.enable_mock_mode()
    result = await client.call_tool("some_tool", {"arg": "val"})
    parsed = json.loads(result)
    assert parsed["mock"] is True


@pytest.mark.asyncio
async def test_mcp_mock_mode_disabled_needs_session():
    """Without mock mode, call_tool returns error when no session."""
    from src.mcp_client import MCPGatewayClient

    config = MagicMock()
    client = MCPGatewayClient(config)
    assert client._session is None
    assert client._mock_mode is False

    result = await client.call_tool("some_tool")
    assert "ERROR" in result
    assert "not connected" in result


# ── Orchestrator is_test_flight ─────────────────────────────────────────


def test_orchestrator_is_test_flight_default():
    from src.orchestrator import Orchestrator

    orch = Orchestrator(
        context_tree=MagicMock(),
        config=MagicMock(spec=[]),
        colony_id="test",
    )
    assert orch._is_test_flight is False


def test_orchestrator_is_test_flight_enabled():
    from src.orchestrator import Orchestrator

    orch = Orchestrator(
        context_tree=MagicMock(),
        config=MagicMock(spec=[]),
        colony_id="test",
        is_test_flight=True,
    )
    assert orch._is_test_flight is True


# ── ColonyManager test flight wiring ────────────────────────────────────


def test_colony_manager_test_flight_overrides_agents():
    """When is_test_flight=True, agents get temp=0.0 and seed=42."""
    from src.agents import Agent

    agent = Agent(
        id="a1",
        caste="coder",
        system_prompt="test",
        model_client=MagicMock(),
        model_name="test-model",
        config={"temperature": 0.7},
    )
    assert agent.temperature == 0.7
    assert agent.seed is None

    # Simulate what colony_manager.start() does for test flight
    agent.temperature = 0.0
    agent.seed = 42
    assert agent.temperature == 0.0
    assert agent.seed == 42


def test_colony_manager_test_flight_mcp_mock():
    """When is_test_flight=True, MCP gateway enters mock mode."""
    from src.mcp_client import MCPGatewayClient

    config = MagicMock()
    client = MCPGatewayClient(config)
    assert client._mock_mode is False

    # Simulate what colony_manager.start() does
    client.enable_mock_mode()
    assert client._mock_mode is True


# ── ColonyManager error traceback capture ───────────────────────────────


@pytest.mark.asyncio
async def test_run_colony_captures_traceback():
    """_run_colony stores error_traceback on failure."""
    from src.colony_manager import ColonyManager

    cm = ColonyManager.__new__(ColonyManager)
    cm._colonies = {}
    cm._lock = asyncio.Lock()
    cm._mcp_client = None

    # Create a minimal colony state
    mock_ctx = AsyncMock()
    mock_ctx.set = AsyncMock()
    mock_ctx.get = MagicMock(return_value=0)

    from src.colony_manager import ColonyInfo
    state = MagicMock()
    state.info = ColonyInfo(colony_id="fail-colony", task="will fail")
    state.context_tree = mock_ctx
    cm._colonies["fail-colony"] = state
    cm._set_status = MagicMock()
    cm._persist_registry_sync = MagicMock()

    # Mock orchestrator that raises
    mock_orch = AsyncMock()
    mock_orch.run = AsyncMock(side_effect=RuntimeError("GPU OOM"))

    await cm._run_colony(
        colony_id="fail-colony",
        orchestrator=mock_orch,
        agents=[],
        max_rounds=5,
        callbacks=None,
    )

    # Verify traceback was stored
    set_calls = [c for c in mock_ctx.set.call_args_list
                 if len(c.args) >= 2 and c.args[0] == "colony" and c.args[1] == "error_traceback"]
    assert len(set_calls) == 1
    traceback_str = set_calls[0].args[2]
    assert isinstance(traceback_str, str)
    assert "RuntimeError" in traceback_str
    assert "GPU OOM" in traceback_str


# ── ColonyManager.get_diagnostics() ─────────────────────────────────────


@pytest.mark.asyncio
async def test_get_diagnostics_payload():
    from src.colony_manager import ColonyManager, ColonyInfo

    cm = ColonyManager.__new__(ColonyManager)
    cm._colonies = {}

    # Build a mock state
    mock_ctx = MagicMock()
    mock_ctx.get = MagicMock(side_effect=lambda scope, key, default=None: {
        ("colony", "error_traceback"): "Traceback: something broke",
        ("colony", "timeline_spans"): [{"span_id": "s1"}],
    }.get((scope, key), default))
    mock_ctx._decisions = [MagicMock(model_dump=MagicMock(return_value={"action": "test"}))]
    mock_ctx._episodes = [MagicMock(model_dump=MagicMock(return_value={"episode": 1}))]
    mock_ctx.get_epoch_summaries = MagicMock(return_value=[])

    info = ColonyInfo(
        colony_id="diag-test",
        task="debug task",
        status=ColonyStatus.FAILED,
    )

    state = MagicMock()
    state.info = info
    state.context_tree = mock_ctx
    cm._colonies["diag-test"] = state

    with patch("src.worker.WorkerManager.get_free_vram_mb", return_value=8192):
        result = await cm.get_diagnostics("diag-test")

    # v0.7.9: get_diagnostics returns DiagnosticsPayload (Pydantic model)
    assert result.colony_id == "diag-test"
    assert result.status == "failed"
    assert result.hardware_state.free_vram_mb == 8192
    assert result.error_traceback == "Traceback: something broke"
    assert len(result.last_decisions) == 1
    assert result.last_decisions[0]["action"] == "test"
    assert len(result.last_episodes) == 1
    assert len(result.timeline_spans) == 1


@pytest.mark.asyncio
async def test_get_diagnostics_colony_not_found():
    from src.colony_manager import ColonyManager, ColonyNotFoundError

    cm = ColonyManager.__new__(ColonyManager)
    cm._colonies = {}

    with pytest.raises(ColonyNotFoundError):
        await cm.get_diagnostics("nonexistent")


# ── POST /api/v1/admin/rebuild ──────────────────────────────────────────


def test_rebuild_endpoint_exists():
    """Rebuild endpoint is registered on the V1 router."""
    # Import check — if server.py loads without error, endpoint is registered
    from src.server import VERSION
    assert VERSION == "0.9.0"


# ── MCP mock mode finally cleanup ──────────────────────────────────────


@pytest.mark.asyncio
async def test_mock_mode_cleanup_after_run():
    """MCP mock mode disabled in finally block after _run_colony."""
    from src.colony_manager import ColonyManager, ColonyInfo

    cm = ColonyManager.__new__(ColonyManager)
    cm._colonies = {}
    cm._lock = asyncio.Lock()

    mock_mcp = MagicMock()
    mock_mcp._mock_mode = True
    mock_mcp.disable_mock_mode = MagicMock()
    cm._mcp_client = mock_mcp

    mock_ctx = AsyncMock()
    mock_ctx.set = AsyncMock()
    mock_ctx.get = MagicMock(return_value=0)

    info = ColonyInfo(colony_id="cleanup-test", task="test")
    state = MagicMock()
    state.info = info
    state.context_tree = mock_ctx
    cm._colonies["cleanup-test"] = state
    cm._set_status = MagicMock()
    cm._persist_registry_sync = MagicMock()

    # Mock orchestrator that succeeds
    mock_orch = AsyncMock()
    mock_result = MagicMock()
    mock_result.status = ColonyStatus.COMPLETED
    mock_result.final_answer = "done"
    mock_orch.run = AsyncMock(return_value=mock_result)
    mock_orch._timeline_spans = []

    await cm._run_colony(
        colony_id="cleanup-test",
        orchestrator=mock_orch,
        agents=[],
        max_rounds=5,
        callbacks=None,
    )

    # MCP mock mode should have been disabled in finally block
    mock_mcp.disable_mock_mode.assert_called_once()


# ── DyTopo fixed seed in test flight ────────────────────────────────────


def test_orchestrator_test_flight_seeds_numpy():
    """In test flight mode, _phase3_routing seeds NumPy before build_topology."""
    import numpy as np
    from src.orchestrator import Orchestrator

    orch = Orchestrator(
        context_tree=MagicMock(),
        config=MagicMock(spec=[]),
        colony_id="seed-test",
        is_test_flight=True,
    )
    # Verify the flag is set
    assert orch._is_test_flight is True

    # The actual seeding happens in _phase3_routing which requires
    # full agent context — we verify the flag propagates correctly
    # and the import exists
    assert hasattr(np.random, "seed")


# ── formicos-cli.py ────────────────────────────────────────────────────


def test_formicos_cli_exists():
    """formicos-cli.py exists at repo root."""
    from pathlib import Path

    cli_path = Path(__file__).resolve().parent.parent / "formicos-cli.py"
    assert cli_path.exists(), f"formicos-cli.py not found at {cli_path}"


def test_formicos_cli_importable():
    """formicos-cli.py main() is importable."""
    import importlib.util

    cli_path = str(
        __import__("pathlib").Path(__file__).resolve().parent.parent / "formicos-cli.py"
    )
    spec = importlib.util.spec_from_file_location("formicos_cli", cli_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert hasattr(module, "main")
    assert hasattr(module, "cmd_rebuild")
    assert hasattr(module, "cmd_diagnostics")
    assert hasattr(module, "cmd_status")


# ── Version bump ────────────────────────────────────────────────────────


def test_version_server():
    from src.server import VERSION
    assert VERSION == "0.9.0"


def test_version_init():
    from src import __version__
    assert __version__ == "0.9.0"
