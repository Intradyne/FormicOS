"""
Tests for FormicOS v0.7.7 AgentOS Paradigm.

Covers:
- SemanticMMU: page_in_context (greedy packing, budget, no results)
- MCPHardwareInterrupt: exception attrs, call_tool timing, raise_on_interrupt
- TopologyJanitor: penalty, reward, no reward on intervention, floor, cap, history
- Router pheromone: build_topology with pheromone_weights
- Timeline: _record_span, TimelineSpan model
- ConvergenceMetrics model
- Skill attribution: author_client_id on Skill, SkillCreateRequest
- Version bump to 0.7.7
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.models import ConvergenceMetrics, TimelineSpan, Topology, TopologyEdge


# ── SemanticMMU ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_page_in_context_no_qdrant():
    """Without qdrant, page_in_context returns empty."""
    from src.rag import RAGEngine

    with patch("src.rag.QDRANT_AVAILABLE", False):
        engine = RAGEngine.__new__(RAGEngine)
        engine._qdrant = None
        engine._embedding_config = MagicMock(dimensions=1024)
        engine._http = MagicMock()
        engine._local_embedder = None
        engine._using_fallback = False

        result = await engine.page_in_context("test query", "test_col")
        assert result["pages"] == []
        assert result["total_tokens"] == 0
        assert result["pages_loaded"] == 0
        assert result["pages_skipped"] == 0


@pytest.mark.asyncio
async def test_page_in_context_no_budget():
    """When token budget is exhausted, returns empty."""
    from src.rag import RAGEngine

    engine = RAGEngine.__new__(RAGEngine)

    result = await engine.page_in_context(
        "query", "col", current_token_count=4000, max_context_tokens=4000,
    )
    assert result["pages_loaded"] == 0
    assert result["total_tokens"] == 0


@pytest.mark.asyncio
async def test_page_in_context_greedy_packing():
    """Packs results within budget, skips overflow chunks."""
    from src.rag import RAGEngine, SearchResult

    engine = RAGEngine.__new__(RAGEngine)

    # Mock search to return 3 results of varying sizes
    mock_results = [
        SearchResult(score=0.9, content="A" * 400, metadata={"source": "a.md", "chunk_index": 0}),
        SearchResult(score=0.8, content="B" * 400, metadata={"source": "b.md", "chunk_index": 1}),
        SearchResult(score=0.7, content="C" * 400, metadata={"source": "c.md", "chunk_index": 2}),
    ]

    with patch.object(engine, "search", new_callable=AsyncMock, return_value=mock_results):
        # Budget: 250 tokens = 1000 chars. Each chunk is 400 chars = 100 tokens.
        # Should fit 2 chunks (200 tokens), skip 1.
        result = await engine.page_in_context(
            "query", "col", current_token_count=0, max_context_tokens=250,
        )

        assert result["pages_loaded"] == 2
        assert result["pages_skipped"] == 1
        assert result["total_tokens"] == 200
        assert result["pages"][0]["source"] == "a.md"
        assert result["pages"][1]["source"] == "b.md"


@pytest.mark.asyncio
async def test_page_in_context_empty_results():
    """Empty search results return empty pages."""
    from src.rag import RAGEngine

    engine = RAGEngine.__new__(RAGEngine)

    with patch.object(engine, "search", new_callable=AsyncMock, return_value=[]):
        result = await engine.page_in_context("query", "col")
        assert result["pages"] == []
        assert result["pages_loaded"] == 0


# ── MCPHardwareInterrupt ──────────────────────────────────────────────


def test_hardware_interrupt_exception_attrs():
    """MCPHardwareInterrupt stores tool_name, tool_args, duration_ms, interrupt_type."""
    from src.mcp_client import MCPHardwareInterrupt

    exc = MCPHardwareInterrupt(
        "timeout",
        tool_name="file_read",
        tool_args={"path": "/tmp/test"},
        duration_ms=30500.0,
        interrupt_type="timeout",
    )
    assert str(exc) == "timeout"
    assert exc.tool_name == "file_read"
    assert exc.tool_args == {"path": "/tmp/test"}
    assert exc.duration_ms == 30500.0
    assert exc.interrupt_type == "timeout"


def test_hardware_interrupt_defaults():
    """MCPHardwareInterrupt has sensible defaults."""
    from src.mcp_client import MCPHardwareInterrupt

    exc = MCPHardwareInterrupt("error happened")
    assert exc.tool_name == ""
    assert exc.tool_args == {}
    assert exc.duration_ms == 0.0
    assert exc.interrupt_type == "error"


@pytest.mark.asyncio
async def test_call_tool_timing_capture():
    """call_tool sets _last_call_duration_ms after successful call."""
    from src.mcp_client import MCPGatewayClient

    client = MCPGatewayClient.__new__(MCPGatewayClient)
    client._last_call_duration_ms = 0.0
    client._tool_call_timeout = 30.0

    mock_result = MagicMock()
    mock_block = MagicMock()
    mock_block.text = "output"
    mock_result.content = [mock_block]

    mock_session = AsyncMock()
    mock_session.call_tool = AsyncMock(return_value=mock_result)
    client._session = mock_session

    output = await client.call_tool("test_tool", {"arg": "val"})
    assert output == "output"
    assert client._last_call_duration_ms > 0


@pytest.mark.asyncio
async def test_call_tool_raise_on_interrupt_timeout():
    """call_tool raises MCPHardwareInterrupt on timeout when raise_on_interrupt=True."""
    from src.mcp_client import MCPGatewayClient, MCPHardwareInterrupt

    client = MCPGatewayClient.__new__(MCPGatewayClient)
    client._last_call_duration_ms = 0.0
    client._tool_call_timeout = 0.001  # Very short timeout

    mock_session = AsyncMock()

    async def slow_call(*args, **kwargs):
        await asyncio.sleep(1)

    mock_session.call_tool = slow_call
    client._session = mock_session

    with pytest.raises(MCPHardwareInterrupt) as exc_info:
        await client.call_tool("slow_tool", raise_on_interrupt=True)

    assert exc_info.value.tool_name == "slow_tool"
    assert exc_info.value.interrupt_type == "timeout"
    assert exc_info.value.duration_ms > 0


@pytest.mark.asyncio
async def test_call_tool_raise_on_interrupt_error():
    """call_tool raises MCPHardwareInterrupt on error when raise_on_interrupt=True."""
    from src.mcp_client import MCPGatewayClient, MCPHardwareInterrupt

    client = MCPGatewayClient.__new__(MCPGatewayClient)
    client._last_call_duration_ms = 0.0
    client._tool_call_timeout = 30.0

    mock_session = AsyncMock()
    mock_session.call_tool = AsyncMock(side_effect=RuntimeError("boom"))
    client._session = mock_session

    with pytest.raises(MCPHardwareInterrupt) as exc_info:
        await client.call_tool("bad_tool", {"x": 1}, raise_on_interrupt=True)

    assert exc_info.value.tool_name == "bad_tool"
    assert exc_info.value.interrupt_type == "error"
    assert "boom" in str(exc_info.value)


@pytest.mark.asyncio
async def test_call_tool_backward_compat():
    """Default behavior: returns error string, no exception."""
    from src.mcp_client import MCPGatewayClient

    client = MCPGatewayClient.__new__(MCPGatewayClient)
    client._last_call_duration_ms = 0.0
    client._tool_call_timeout = 30.0

    mock_session = AsyncMock()
    mock_session.call_tool = AsyncMock(side_effect=RuntimeError("crash"))
    client._session = mock_session

    # Should NOT raise
    result = await client.call_tool("tool")
    assert "ERROR" in result
    assert "crash" in result


@pytest.mark.asyncio
async def test_call_tool_not_connected_raise():
    """call_tool raises MCPHardwareInterrupt when not connected and raise_on_interrupt=True."""
    from src.mcp_client import MCPGatewayClient, MCPHardwareInterrupt

    client = MCPGatewayClient.__new__(MCPGatewayClient)
    client._last_call_duration_ms = 0.0
    client._session = None

    with pytest.raises(MCPHardwareInterrupt) as exc_info:
        await client.call_tool("tool", raise_on_interrupt=True)

    assert exc_info.value.interrupt_type == "error"


# ── TopologyJanitor ───────────────────────────────────────────────────


def test_janitor_penalty_slow_round():
    """Penalizes edges when round wall-clock > 1.5x baseline."""
    from src.orchestrator import TopologyJanitor

    janitor = TopologyJanitor(baseline_ms=10000.0, penalty_weight=-0.8)
    topology = Topology(
        edges=[TopologyEdge(sender="a", receiver="b", weight=0.9)],
        execution_order=["a", "b"],
    )

    metrics = janitor.evaluate(0, 20000.0, topology)  # 2x baseline > 1.5x

    assert metrics.penalty_applied == -0.8
    assert metrics.reward_applied == 0.0
    assert len(metrics.route_adjustments) == 1
    assert metrics.route_adjustments[0]["reason"] == "slow_round"

    # Weight should be 1.0 * (1.0 + (-0.8)) = 0.2
    assert janitor.pheromone_weights[("a", "b")] == pytest.approx(0.2)


def test_janitor_reward_good_round():
    """Rewards edges when round <= baseline and no governance intervention."""
    from src.orchestrator import TopologyJanitor

    janitor = TopologyJanitor(baseline_ms=10000.0, reward_weight=0.2)
    topology = Topology(
        edges=[TopologyEdge(sender="a", receiver="b", weight=0.9)],
        execution_order=["a", "b"],
    )

    metrics = janitor.evaluate(0, 8000.0, topology)  # Under baseline

    assert metrics.reward_applied == 0.2
    assert metrics.penalty_applied == 0.0
    assert metrics.route_adjustments[0]["reason"] == "good_round"

    # Weight should be 1.0 * (1.0 + 0.2) = 1.2
    assert janitor.pheromone_weights[("a", "b")] == pytest.approx(1.2)


def test_janitor_no_reward_on_intervention():
    """No reward when governance intervened."""
    from src.orchestrator import TopologyJanitor

    janitor = TopologyJanitor(baseline_ms=10000.0, reward_weight=0.2)
    topology = Topology(
        edges=[TopologyEdge(sender="a", receiver="b", weight=0.9)],
        execution_order=["a", "b"],
    )

    metrics = janitor.evaluate(0, 8000.0, topology, governance_intervened=True)

    assert metrics.reward_applied == 0.0
    assert metrics.penalty_applied == 0.0
    assert len(metrics.route_adjustments) == 0


def test_janitor_pheromone_floor():
    """Pheromone weight never goes below 0.1."""
    from src.orchestrator import TopologyJanitor

    janitor = TopologyJanitor(baseline_ms=1000.0, penalty_weight=-0.95)
    topology = Topology(
        edges=[TopologyEdge(sender="a", receiver="b", weight=0.5)],
        execution_order=["a", "b"],
    )

    # Apply many penalties
    for i in range(10):
        janitor.evaluate(i, 5000.0, topology)

    assert janitor.pheromone_weights[("a", "b")] >= 0.1


def test_janitor_pheromone_cap():
    """Pheromone weight never exceeds 2.0."""
    from src.orchestrator import TopologyJanitor

    janitor = TopologyJanitor(baseline_ms=100000.0, reward_weight=0.5)
    topology = Topology(
        edges=[TopologyEdge(sender="a", receiver="b", weight=0.5)],
        execution_order=["a", "b"],
    )

    # Apply many rewards
    for i in range(20):
        janitor.evaluate(i, 1000.0, topology)

    assert janitor.pheromone_weights[("a", "b")] <= 2.0


def test_janitor_history():
    """History accumulates one entry per evaluate() call."""
    from src.orchestrator import TopologyJanitor

    janitor = TopologyJanitor()
    topology = Topology(edges=[], execution_order=[])

    janitor.evaluate(0, 1000.0, topology)
    janitor.evaluate(1, 2000.0, topology)

    assert len(janitor.history) == 2
    assert janitor.history[0].round_num == 0
    assert janitor.history[1].round_num == 1


# ── Router pheromone weights ─────────────────────────────────────────


def test_build_topology_with_pheromone_weights():
    """Pheromone weights modify edge weights in build_topology."""
    from src.router import build_topology

    mock_embedder = MagicMock()
    # 2 agents: need 2 key vectors + 2 query vectors
    import numpy as np
    mock_embedder.encode = MagicMock(return_value=np.array([
        [1.0, 0.0],
        [0.8, 0.6],
    ]))

    descriptors = {
        "a1": {"key": "coder tasks", "query": "need review"},
        "a2": {"key": "reviewer tasks", "query": "need code"},
    }

    # Without pheromone
    topo_base = build_topology(
        ["a1", "a2"], descriptors, mock_embedder, tau=0.0, k_in=3,
    )

    # With pheromone that halves one edge
    pheromone = {("a1", "a2"): 0.5, ("a2", "a1"): 1.5}
    topo_phero = build_topology(
        ["a1", "a2"], descriptors, mock_embedder, tau=0.0, k_in=3,
        pheromone_weights=pheromone,
    )

    # Find matching edges and compare
    if topo_base.edges and topo_phero.edges:
        for base_edge in topo_base.edges:
            for phero_edge in topo_phero.edges:
                if base_edge.sender == phero_edge.sender and base_edge.receiver == phero_edge.receiver:
                    key = (phero_edge.sender, phero_edge.receiver)
                    if key in pheromone:
                        expected = base_edge.weight * pheromone[key]
                        assert phero_edge.weight == pytest.approx(expected, abs=0.01)


def test_build_topology_no_pheromone_default():
    """Without pheromone_weights, behavior is unchanged."""
    from src.router import build_topology

    mock_embedder = MagicMock()
    import numpy as np
    mock_embedder.encode = MagicMock(return_value=np.array([
        [1.0, 0.0],
        [0.8, 0.6],
    ]))

    descriptors = {
        "a1": {"key": "coder", "query": "review"},
        "a2": {"key": "reviewer", "query": "code"},
    }

    topo1 = build_topology(["a1", "a2"], descriptors, mock_embedder, tau=0.0, k_in=3)
    topo2 = build_topology(
        ["a1", "a2"], descriptors, mock_embedder, tau=0.0, k_in=3,
        pheromone_weights=None,
    )

    assert len(topo1.edges) == len(topo2.edges)
    for e1, e2 in zip(topo1.edges, topo2.edges):
        assert e1.weight == e2.weight


# ── Timeline & ConvergenceMetrics models ──────────────────────────────


def test_timeline_span_model():
    """TimelineSpan model validates correctly."""
    span = TimelineSpan(
        span_id="test_r0_round_abc123",
        round_num=0,
        agent_id="coder-1",
        agent_role="coder",
        activity_type="inference",
        start_ms=0.0,
        duration_ms=1500.0,
        is_critical_path=True,
        metadata={"tokens": 500},
    )
    assert span.span_id == "test_r0_round_abc123"
    assert span.is_critical_path is True
    assert span.metadata["tokens"] == 500


def test_timeline_span_defaults():
    """TimelineSpan defaults are sensible."""
    span = TimelineSpan(
        span_id="s1",
        round_num=0,
        activity_type="routing",
        start_ms=0.0,
        duration_ms=100.0,
    )
    assert span.agent_id is None
    assert span.agent_role is None
    assert span.is_critical_path is False
    assert span.metadata == {}


def test_convergence_metrics_model():
    """ConvergenceMetrics model validates correctly."""
    cm = ConvergenceMetrics(
        round_num=3,
        wall_clock_ms=55000.0,
        qa_score=0.85,
        baseline_ms=45000.0,
        penalty_applied=-0.8,
        reward_applied=0.0,
        route_adjustments=[{"sender": "a", "receiver": "b", "reason": "slow"}],
    )
    assert cm.round_num == 3
    assert cm.wall_clock_ms == 55000.0
    assert cm.penalty_applied == -0.8
    assert len(cm.route_adjustments) == 1


def test_convergence_metrics_defaults():
    """ConvergenceMetrics defaults work."""
    cm = ConvergenceMetrics(round_num=0, wall_clock_ms=1000.0)
    assert cm.qa_score == 0.0
    assert cm.baseline_ms == 45000.0
    assert cm.penalty_applied == 0.0
    assert cm.reward_applied == 0.0
    assert cm.route_adjustments == []


# ── Orchestrator _record_span ─────────────────────────────────────────


def test_record_span():
    """_record_span appends a TimelineSpan to the orchestrator's list."""
    from src.orchestrator import Orchestrator

    orch = Orchestrator.__new__(Orchestrator)
    orch.colony_id = "test-colony"
    orch._timeline_spans = []

    orch._record_span(
        round_num=0,
        activity_type="round",
        start_ms=0.0,
        duration_ms=5000.0,
        agent_id="coder-1",
        is_critical_path=True,
    )

    assert len(orch._timeline_spans) == 1
    span = orch._timeline_spans[0]
    assert span.round_num == 0
    assert span.activity_type == "round"
    assert span.duration_ms == 5000.0
    assert span.is_critical_path is True
    assert span.span_id.startswith("test-colony_r0_round_")


def test_record_span_metadata():
    """_record_span passes kwargs as metadata."""
    from src.orchestrator import Orchestrator

    orch = Orchestrator.__new__(Orchestrator)
    orch.colony_id = "c1"
    orch._timeline_spans = []

    orch._record_span(0, "execution", 100.0, 500.0, agents=["a1", "a2"])

    span = orch._timeline_spans[0]
    assert span.metadata["agents"] == ["a1", "a2"]


# ── Skill attribution ─────────────────────────────────────────────────


def test_skill_author_client_id():
    """Skill model accepts author_client_id."""
    from src.models import Skill, SkillTier

    skill = Skill(
        skill_id="s1",
        content="test",
        tier=SkillTier.GENERAL,
        author_client_id="ext-agent-1",
    )
    assert skill.author_client_id == "ext-agent-1"


def test_skill_author_client_id_default_none():
    """Skill.author_client_id defaults to None."""
    from src.models import Skill, SkillTier

    skill = Skill(skill_id="s2", content="test", tier=SkillTier.GENERAL)
    assert skill.author_client_id is None


def test_skill_create_request_author():
    """SkillCreateRequest accepts author_client_id and colony_id."""
    from src.server import SkillCreateRequest

    req = SkillCreateRequest(
        content="skill content",
        author_client_id="my-agent",
        colony_id="c1",
    )
    assert req.author_client_id == "my-agent"
    assert req.colony_id == "c1"


def test_skill_create_request_defaults():
    """SkillCreateRequest author fields default to None."""
    from src.server import SkillCreateRequest

    req = SkillCreateRequest(content="test")
    assert req.author_client_id is None
    assert req.colony_id is None


# ── Version bump ──────────────────────────────────────────────────────


def test_version_server():
    from src.server import VERSION
    assert VERSION == "0.9.0"


def test_version_init():
    from src import __version__
    assert __version__ == "0.9.0"
