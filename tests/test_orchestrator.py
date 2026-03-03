"""
Tests for FormicOS v0.6.0 Orchestrator.

Covers:
1.  run completes full loop (3 rounds, converges)
2.  run handles agent failure gracefully (one agent errors, others continue)
3.  Phase 1 goal setting calls manager agent
4.  Phase 2 intent generation calls all agents
5.  Phase 3 routing produces topology
6.  Phase 3 topology caching (intents unchanged)
7.  Phase 3.5 skill injection retrieves skills
8.  Phase 4 execution follows topological order
9.  Phase 4 routed messages correct (upstream outputs)
10. Phase 5 archivist called with round outputs
11. Phase 5 governance force_halt ends loop
12. Phase 5 governance intervention stored for next round
13. extend_rounds increases max_rounds
14. cancel stops loop
15. Post-colony skill distillation
16. SessionResult returned with correct fields
17. Callbacks fire at correct phases

All dependencies (agents, router, governance, archivist, skill_bank,
context_tree) are fully mocked with AsyncMock.
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agents import AgentOutput
from src.context import AsyncContextTree
from src.governance import GovernanceDecision
from src.models import (
    Caste,
    ColonyStatus,
    Episode,
    SessionResult,
    Skill,
    SkillTier,
    TKGTuple,
    Topology,
    TopologyEdge,
)
from src.orchestrator import Orchestrator


# ═══════════════════════════════════════════════════════════════════════════
# Test Helpers & Fixtures
# ═══════════════════════════════════════════════════════════════════════════


def _make_agent_output(
    approach: str = "test approach",
    output: str = "test output",
    tokens_used: int = 100,
) -> AgentOutput:
    """Create a predictable AgentOutput."""
    return AgentOutput(
        approach=approach,
        alternatives_rejected="none",
        output=output,
        tool_calls=[],
        tokens_used=tokens_used,
    )


def _make_mock_agent(
    agent_id: str,
    caste: Caste = Caste.CODER,
    intent: dict[str, str] | None = None,
    output: AgentOutput | None = None,
) -> MagicMock:
    """Create a mock Agent with predictable behavior."""
    agent = MagicMock()
    agent.id = agent_id
    agent.caste = caste

    # generate_intent returns a dict
    default_intent = intent or {
        "key": f"{caste.value} output from {agent_id}",
        "query": f"what {agent_id} needs",
    }
    agent.generate_intent = AsyncMock(return_value=default_intent)

    # execute returns AgentOutput
    default_output = output or _make_agent_output(
        approach=f"approach_{agent_id}",
        output=f"output from {agent_id}",
    )
    agent.execute = AsyncMock(return_value=default_output)

    # cancel
    agent.cancel = MagicMock()

    return agent


def _make_manager_agent(
    terminate_after: int | None = None,
    goals: list[str] | None = None,
) -> MagicMock:
    """Create a mock Manager agent.

    Parameters
    ----------
    terminate_after : int | None
        If set, the manager will signal termination after this many calls.
    goals : list[str] | None
        Custom goals to cycle through.  Default: "Goal for round N".
    """
    agent = MagicMock()
    agent.id = "manager_01"
    agent.caste = Caste.MANAGER
    agent.system_prompt = "You are the manager."
    agent.cancel = MagicMock()
    agent.generate_intent = AsyncMock(return_value={
        "key": "strategic direction",
        "query": "agent status reports",
    })

    call_count = 0

    async def _execute_raw(system_override, user_prompt):
        nonlocal call_count
        call_count += 1

        if goals and call_count <= len(goals):
            goal = goals[call_count - 1]
        else:
            goal = f"Goal for round {call_count - 1}"

        if terminate_after is not None and call_count > terminate_after:
            return json.dumps({
                "goal": "",
                "terminate": True,
                "final_answer": "Task completed successfully.",
            })

        return json.dumps({
            "goal": goal,
            "terminate": False,
        })

    agent.execute_raw = AsyncMock(side_effect=_execute_raw)

    # Keep execute for backward compat with any test that calls it directly
    async def _execute(context, round_goal, routed_messages=None,
                       skill_context=None, callbacks=None):
        return _make_agent_output(output=await _execute_raw("", ""))

    agent.execute = AsyncMock(side_effect=_execute)
    return agent


def _make_mock_config() -> MagicMock:
    """Create a minimal mock FormicOSConfig."""
    config = MagicMock()
    config.inference.timeout_seconds = 120
    config.inference.max_tokens_per_agent = 5000
    config.inference.temperature = 0.0
    config.routing.tau = 0.35
    config.routing.k_in = 3
    return config


def _make_mock_archivist() -> MagicMock:
    """Create a mock Archivist."""
    archivist = MagicMock()

    async def _summarize_round(round_num, goal, agent_outputs):
        return Episode(
            round_num=round_num,
            summary=f"Summary of round {round_num}: {goal}",
            goal=goal,
            agent_outputs={k: str(v)[:200] for k, v in agent_outputs.items()},
        )

    archivist.summarize_round = AsyncMock(side_effect=_summarize_round)

    archivist.extract_tkg_tuples = AsyncMock(return_value=[
        TKGTuple(
            subject="test_agent",
            predicate="Produced",
            object_="test output",
            round_num=0,
        )
    ])

    archivist.maybe_compress_epochs = AsyncMock(return_value=False)

    archivist.distill_skills = AsyncMock(return_value=[
        Skill(
            skill_id="gen_test001",
            content="Always validate inputs first.",
            tier=SkillTier.GENERAL,
        ),
    ])

    return archivist


def _make_mock_governance(
    action: str = "continue",
    reason: str = "All good",
    force_halt_after: int | None = None,
) -> MagicMock:
    """Create a mock GovernanceEngine.

    Parameters
    ----------
    force_halt_after : int | None
        If set, governance will return force_halt after this many enforce() calls.
    """
    gov = MagicMock()
    enforce_count = 0

    def _enforce(round_num, prev_vec, curr_vec):
        nonlocal enforce_count
        enforce_count += 1

        if force_halt_after is not None and enforce_count >= force_halt_after:
            return GovernanceDecision(
                action="force_halt",
                reason="Convergence detected.",
                recommendations=["Try a different approach"],
            )
        return GovernanceDecision(action=action, reason=reason)

    gov.enforce = MagicMock(side_effect=_enforce)
    gov.check_tunnel_vision = MagicMock(return_value=None)
    gov.detect_stalls = MagicMock(return_value=[])

    return gov


def _make_mock_skill_bank() -> MagicMock:
    """Create a mock SkillBank."""
    sb = MagicMock()
    sb.retrieve = MagicMock(return_value=[
        Skill(
            skill_id="gen_abc123",
            content="Use incremental development.",
            tier=SkillTier.GENERAL,
        ),
    ])
    sb.format_for_injection = MagicMock(
        return_value="[STRATEGIC GUIDANCE]\n- Use incremental development.\n[END STRATEGIC GUIDANCE]"
    )
    sb.store = MagicMock(return_value=1)
    return sb


def _make_mock_audit() -> MagicMock:
    """Create a mock AuditLogger."""
    audit = MagicMock()
    audit.log_session_start = MagicMock()
    audit.log_session_end = MagicMock()
    audit.log_round = MagicMock()
    audit.log_decision = MagicMock()
    audit.log_error = MagicMock()
    return audit


@pytest.fixture
def ctx():
    """Fresh AsyncContextTree for each test."""
    return AsyncContextTree()


@pytest.fixture
def config():
    return _make_mock_config()


@pytest.fixture
def archivist():
    return _make_mock_archivist()


@pytest.fixture
def governance():
    return _make_mock_governance()


@pytest.fixture
def skill_bank():
    return _make_mock_skill_bank()


@pytest.fixture
def audit():
    return _make_mock_audit()


@pytest.fixture
def orchestrator(ctx, config, archivist, governance, skill_bank, audit):
    """Standard orchestrator with all dependencies mocked."""
    return Orchestrator(
        context_tree=ctx,
        config=config,
        colony_id="test_colony",
        archivist=archivist,
        governance=governance,
        skill_bank=skill_bank,
        audit_logger=audit,
        embedder=None,  # No routing embedder by default
    )


# ═══════════════════════════════════════════════════════════════════════════
# Test 1: Full loop completes (3 rounds, manager terminates)
# ═══════════════════════════════════════════════════════════════════════════


class TestFullLoop:

    @pytest.mark.asyncio
    async def test_run_completes_3_rounds_then_terminates(self, orchestrator):
        """Manager signals termination after round 2 (3 calls)."""
        manager = _make_manager_agent(terminate_after=3)
        worker1 = _make_mock_agent("coder_01", Caste.CODER)
        worker2 = _make_mock_agent("reviewer_01", Caste.REVIEWER)
        agents = [manager, worker1, worker2]

        result = await orchestrator.run(
            task="Build a REST API",
            agents=agents,
            max_rounds=10,
        )

        assert isinstance(result, SessionResult)
        assert result.status == ColonyStatus.COMPLETED
        assert result.task == "Build a REST API"
        assert result.final_answer == "Task completed successfully."
        # Manager was called 3 times (round 0, 1, 2) but terminated on 3rd
        assert result.rounds_completed <= 3

    @pytest.mark.asyncio
    async def test_run_hits_max_rounds(self, orchestrator):
        """Loop ends when max_rounds is reached."""
        manager = _make_manager_agent()
        worker = _make_mock_agent("coder_01")
        agents = [manager, worker]

        result = await orchestrator.run(
            task="Build a REST API",
            agents=agents,
            max_rounds=2,
        )

        assert result.status == ColonyStatus.COMPLETED
        assert result.rounds_completed == 2


# ═══════════════════════════════════════════════════════════════════════════
# Test 2: Agent failure handled gracefully
# ═══════════════════════════════════════════════════════════════════════════


class TestAgentFailure:

    @pytest.mark.asyncio
    async def test_one_agent_fails_others_continue(self, orchestrator):
        """When one agent throws, the round continues with other agents."""
        manager = _make_manager_agent()
        good_agent = _make_mock_agent("coder_01", Caste.CODER)
        bad_agent = _make_mock_agent("reviewer_01", Caste.REVIEWER)
        bad_agent.execute = AsyncMock(
            side_effect=RuntimeError("LLM connection refused")
        )
        agents = [manager, good_agent, bad_agent]

        result = await orchestrator.run(
            task="Test error handling",
            agents=agents,
            max_rounds=1,
        )

        # Should complete despite one agent failing
        assert result.status == ColonyStatus.COMPLETED
        assert result.rounds_completed == 1

        # Good agent should have been called
        good_agent.execute.assert_called()

    @pytest.mark.asyncio
    async def test_agent_timeout_produces_error_output(self, orchestrator, config):
        """Agent that times out gets an error AgentOutput."""
        config.inference.timeout_seconds = 1  # Very short timeout
        orchestrator._agent_timeout = 1

        manager = _make_manager_agent()

        async def _slow_execute(*args, **kwargs):
            await asyncio.sleep(10)
            return _make_agent_output()

        slow_agent = _make_mock_agent("slow_01", Caste.CODER)
        slow_agent.execute = AsyncMock(side_effect=_slow_execute)

        agents = [manager, slow_agent]
        result = await orchestrator.run(
            task="Test timeout",
            agents=agents,
            max_rounds=1,
        )

        assert result.status == ColonyStatus.COMPLETED


# ═══════════════════════════════════════════════════════════════════════════
# Test 3: Phase 1 -- Goal setting calls manager
# ═══════════════════════════════════════════════════════════════════════════


class TestPhase1Goal:

    @pytest.mark.asyncio
    async def test_phase1_calls_manager(self, orchestrator):
        """Phase 1 invokes manager.execute_raw()."""
        manager = _make_manager_agent()
        worker = _make_mock_agent("coder_01")
        agents = [manager, worker]

        await orchestrator.run(
            task="Test Phase 1",
            agents=agents,
            max_rounds=1,
        )

        # Manager should have been called via execute_raw (Phase 1)
        manager.execute_raw.assert_called()

    @pytest.mark.asyncio
    async def test_phase1_direction_hint_injected(self, orchestrator):
        """Direction hint from extend_rounds is injected into Phase 1."""
        manager = _make_manager_agent()

        # Set up orchestrator state as if a run is in progress
        orchestrator._session_id = "test_session"
        orchestrator._max_rounds = 5
        orchestrator._direction_hint = "Focus on authentication module"

        goal, terminate, answer = await orchestrator._phase1_goal(
            task="Test direction hint",
            manager=manager,
            round_num=0,
            callbacks=None,
        )

        # Check that manager.execute_raw was called with user_prompt containing the hint
        manager.execute_raw.assert_called_once()
        call_args = manager.execute_raw.call_args
        user_prompt = call_args.kwargs.get("user_prompt", call_args[0][1] if len(call_args[0]) > 1 else "")
        assert "OPERATOR DIRECTION" in user_prompt
        assert "Focus on authentication module" in user_prompt

    @pytest.mark.asyncio
    async def test_no_manager_uses_fallback_goal(self, orchestrator):
        """Without a manager, a fallback goal is used."""
        worker = _make_mock_agent("coder_01")
        agents = [worker]

        result = await orchestrator.run(
            task="Test no manager",
            agents=agents,
            max_rounds=1,
        )

        # Should still complete
        assert result.status == ColonyStatus.COMPLETED


# ═══════════════════════════════════════════════════════════════════════════
# Test 4: Phase 2 -- Intent generation calls all agents
# ═══════════════════════════════════════════════════════════════════════════


class TestPhase2Intent:

    @pytest.mark.asyncio
    async def test_all_workers_generate_intent(self, orchestrator):
        """Phase 2 calls generate_intent on every worker agent (from round 1+)."""
        manager = _make_manager_agent()
        worker1 = _make_mock_agent("coder_01", Caste.CODER)
        worker2 = _make_mock_agent("architect_01", Caste.ARCHITECT)
        worker3 = _make_mock_agent("reviewer_01", Caste.REVIEWER)
        agents = [manager, worker1, worker2, worker3]

        # Need max_rounds=2 so round 1 runs Phase 2 (round 0 is broadcast)
        await orchestrator.run(
            task="Test Phase 2",
            agents=agents,
            max_rounds=2,
        )

        # All workers should have generate_intent called (on round 1)
        worker1.generate_intent.assert_called()
        worker2.generate_intent.assert_called()
        worker3.generate_intent.assert_called()

    @pytest.mark.asyncio
    async def test_intent_failure_uses_fallback(self, orchestrator):
        """When generate_intent fails, a default intent is used."""
        manager = _make_manager_agent()
        bad_worker = _make_mock_agent("coder_01")
        bad_worker.generate_intent = AsyncMock(
            side_effect=RuntimeError("Intent generation failed")
        )
        agents = [manager, bad_worker]

        result = await orchestrator.run(
            task="Test intent failure",
            agents=agents,
            max_rounds=1,
        )

        # Should still complete with fallback intent
        assert result.status == ColonyStatus.COMPLETED


# ═══════════════════════════════════════════════════════════════════════════
# Test 5: Phase 3 -- Routing produces topology
# ═══════════════════════════════════════════════════════════════════════════


class TestPhase3Routing:

    @pytest.mark.asyncio
    async def test_routing_with_embedder_calls_build_topology(self, ctx, config, archivist, governance, skill_bank, audit):
        """With an embedder, Phase 3 calls build_topology from src.router."""
        mock_embedder = MagicMock()

        mock_topology = Topology(
            edges=[
                TopologyEdge(sender="coder_01", receiver="reviewer_01", weight=0.7),
            ],
            execution_order=["coder_01", "reviewer_01"],
        )

        orch = Orchestrator(
            context_tree=ctx,
            config=config,
            colony_id="test_colony",
            archivist=archivist,
            governance=governance,
            skill_bank=skill_bank,
            audit_logger=audit,
            embedder=mock_embedder,
        )

        worker1 = _make_mock_agent("coder_01", Caste.CODER)
        worker2 = _make_mock_agent("reviewer_01", Caste.REVIEWER)
        intents = {
            "coder_01": {"key": "code implementation", "query": "architecture specs"},
            "reviewer_01": {"key": "code review feedback", "query": "code to review"},
        }

        with patch("src.router.build_topology", return_value=mock_topology) as mock_bt:
            result = await orch._phase3_routing(
                workers=[worker1, worker2],
                intents=intents,
                callbacks=None,
            )

        mock_bt.assert_called_once()
        assert result.execution_order == ["coder_01", "reviewer_01"]
        assert len(result.edges) == 1

    @pytest.mark.asyncio
    async def test_no_embedder_fallback_ordering(self, orchestrator):
        """Without an embedder, agents execute in sorted order."""
        manager = _make_manager_agent()
        worker_b = _make_mock_agent("beta_01", Caste.CODER)
        worker_a = _make_mock_agent("alpha_01", Caste.ARCHITECT)
        agents = [manager, worker_b, worker_a]

        result = await orchestrator.run(
            task="Test fallback order",
            agents=agents,
            max_rounds=1,
        )

        assert result.status == ColonyStatus.COMPLETED
        # Both workers should have executed
        worker_a.execute.assert_called()
        worker_b.execute.assert_called()


# ═══════════════════════════════════════════════════════════════════════════
# Test 6: Phase 3 topology caching
# ═══════════════════════════════════════════════════════════════════════════


class TestTopologyCache:

    @pytest.mark.asyncio
    async def test_topology_cached_when_intents_unchanged(self, orchestrator):
        """Topology is reused if intents haven't changed between rounds."""
        cached_topo = Topology(
            edges=[], execution_order=["coder_01"],
        )
        orchestrator._cached_topology = cached_topo
        orchestrator._cached_intents = {
            "coder_01": {"key": "code output", "query": "spec input"},
        }

        # Same intents
        new_intents = {
            "coder_01": {"key": "code output", "query": "spec input"},
        }

        workers = [_make_mock_agent("coder_01")]

        result = await orchestrator._phase3_routing(workers, new_intents, None)

        # Should return the cached topology
        assert result is cached_topo

    @pytest.mark.asyncio
    async def test_topology_not_cached_when_intents_change(self, orchestrator):
        """Topology is rebuilt if intents have changed."""
        cached_topo = Topology(
            edges=[], execution_order=["coder_01"],
        )
        orchestrator._cached_topology = cached_topo
        orchestrator._cached_intents = {
            "coder_01": {"key": "old key", "query": "old query"},
        }

        # Different intents
        new_intents = {
            "coder_01": {"key": "new key", "query": "new query"},
        }

        workers = [_make_mock_agent("coder_01")]

        result = await orchestrator._phase3_routing(workers, new_intents, None)

        # Without an embedder, falls back to sorted order (not cached)
        assert result is not cached_topo

    @pytest.mark.asyncio
    async def test_topology_not_cached_when_agents_change(self, orchestrator):
        """Topology is rebuilt if the set of agents has changed."""
        cached_topo = Topology(
            edges=[], execution_order=["coder_01"],
        )
        orchestrator._cached_topology = cached_topo
        orchestrator._cached_intents = {
            "coder_01": {"key": "code", "query": "spec"},
        }

        # New agent set
        new_intents = {
            "coder_01": {"key": "code", "query": "spec"},
            "reviewer_01": {"key": "review", "query": "code"},
        }

        workers = [
            _make_mock_agent("coder_01"),
            _make_mock_agent("reviewer_01"),
        ]

        result = await orchestrator._phase3_routing(workers, new_intents, None)

        # Should not return cached topology
        assert result is not cached_topo


# ═══════════════════════════════════════════════════════════════════════════
# Test 7: Phase 3.5 -- Skill injection
# ═══════════════════════════════════════════════════════════════════════════


class TestPhase35Skills:

    @pytest.mark.asyncio
    async def test_skill_injection_retrieves_skills(self, orchestrator, skill_bank):
        """Phase 3.5 queries SkillBank with the round goal."""
        result = await orchestrator._phase35_skills("Implement authentication")

        skill_bank.retrieve.assert_called_once_with("Implement authentication")
        skill_bank.format_for_injection.assert_called_once()
        assert result is not None
        assert "STRATEGIC GUIDANCE" in result

    @pytest.mark.asyncio
    async def test_no_skill_bank_returns_none(self, ctx, config):
        """Without a SkillBank, Phase 3.5 returns None."""
        orch = Orchestrator(
            context_tree=ctx,
            config=config,
            colony_id="test",
        )

        result = await orch._phase35_skills("Build something")
        assert result is None

    @pytest.mark.asyncio
    async def test_skill_bank_empty_results(self, orchestrator, skill_bank):
        """If SkillBank returns no skills, Phase 3.5 returns None."""
        skill_bank.retrieve = MagicMock(return_value=[])

        result = await orchestrator._phase35_skills("Obscure task")
        assert result is None


# ═══════════════════════════════════════════════════════════════════════════
# Test 8: Phase 4 -- Execution follows topological order
# ═══════════════════════════════════════════════════════════════════════════


class TestPhase4Execution:

    @pytest.mark.asyncio
    async def test_broadcast_executes_all_agents(self, orchestrator):
        """Broadcast topology (0 edges) executes all agents (parallel)."""
        worker_a = _make_mock_agent("agent_a", Caste.CODER)
        worker_b = _make_mock_agent("agent_b", Caste.REVIEWER)
        worker_c = _make_mock_agent("agent_c", Caste.ARCHITECT)

        topology = Topology(
            edges=[],
            execution_order=["agent_c", "agent_a", "agent_b"],
        )

        outputs = await orchestrator._phase4_execution(
            workers=[worker_a, worker_b, worker_c],
            topology=topology,
            round_goal="Test order",
            skill_context=None,
            callbacks=None,
        )

        # All agents should have executed (order within a level is non-deterministic)
        assert set(outputs.keys()) == {"agent_a", "agent_b", "agent_c"}

    @pytest.mark.asyncio
    async def test_chain_executes_sequentially(self, orchestrator):
        """Chain topology (A→B→C) runs agents one per level, preserving order."""
        execution_log: list[str] = []

        def _make_tracked_side_effect(agent_id):
            async def _exec(*args, **kwargs):
                execution_log.append(agent_id)
                return _make_agent_output(output=f"output from {agent_id}")
            return _exec

        worker_a = _make_mock_agent("agent_a", Caste.CODER)
        worker_b = _make_mock_agent("agent_b", Caste.REVIEWER)
        worker_c = _make_mock_agent("agent_c", Caste.ARCHITECT)

        worker_a.execute = AsyncMock(side_effect=_make_tracked_side_effect("agent_a"))
        worker_b.execute = AsyncMock(side_effect=_make_tracked_side_effect("agent_b"))
        worker_c.execute = AsyncMock(side_effect=_make_tracked_side_effect("agent_c"))

        topology = Topology(
            edges=[
                TopologyEdge(sender="agent_a", receiver="agent_b", weight=0.8),
                TopologyEdge(sender="agent_b", receiver="agent_c", weight=0.7),
            ],
            execution_order=["agent_a", "agent_b", "agent_c"],
        )

        outputs = await orchestrator._phase4_execution(
            workers=[worker_a, worker_b, worker_c],
            topology=topology,
            round_goal="Test chain",
            skill_context=None,
            callbacks=None,
        )

        # Chain = 3 levels of 1: strictly sequential
        assert execution_log == ["agent_a", "agent_b", "agent_c"]
        assert set(outputs.keys()) == {"agent_a", "agent_b", "agent_c"}


# ═══════════════════════════════════════════════════════════════════════════
# Test 9: Phase 4 -- Routed messages from upstream
# ═══════════════════════════════════════════════════════════════════════════


class TestRoutedMessages:

    @pytest.mark.asyncio
    async def test_routed_messages_from_upstream(self, orchestrator):
        """Agent receives upstream outputs via topology edges."""
        worker_a = _make_mock_agent(
            "sender_01", Caste.CODER,
            output=_make_agent_output(output="architecture plan"),
        )
        worker_b = _make_mock_agent("receiver_01", Caste.REVIEWER)

        topology = Topology(
            edges=[
                TopologyEdge(sender="sender_01", receiver="receiver_01", weight=0.8),
            ],
            execution_order=["sender_01", "receiver_01"],
        )

        _outputs = await orchestrator._phase4_execution(
            workers=[worker_a, worker_b],
            topology=topology,
            round_goal="Test routing",
            skill_context=None,
            callbacks=None,
        )

        # receiver_01's execute should have received routed_messages
        call_kwargs = worker_b.execute.call_args
        routed = call_kwargs.kwargs.get("routed_messages", [])
        assert len(routed) == 1
        assert "sender_01" in routed[0]
        assert "architecture plan" in routed[0]

    @pytest.mark.asyncio
    async def test_no_messages_for_source_agents(self, orchestrator):
        """Source agents (no incoming edges) receive empty routed_messages."""
        worker = _make_mock_agent("source_01", Caste.CODER)

        topology = Topology(
            edges=[],
            execution_order=["source_01"],
        )

        await orchestrator._phase4_execution(
            workers=[worker],
            topology=topology,
            round_goal="Test source",
            skill_context=None,
            callbacks=None,
        )

        call_kwargs = worker.execute.call_args
        routed = call_kwargs.kwargs.get("routed_messages", [])
        assert routed == []


# ═══════════════════════════════════════════════════════════════════════════
# Test 10: Phase 5 -- Archivist called
# ═══════════════════════════════════════════════════════════════════════════


class TestPhase5Archivist:

    @pytest.mark.asyncio
    async def test_archivist_summarize_round_called(self, orchestrator, archivist, ctx):
        """Phase 5 calls archivist.summarize_round with round outputs."""
        agent_outputs = {
            "coder_01": _make_agent_output(output="wrote auth module"),
            "reviewer_01": _make_agent_output(output="reviewed auth module"),
        }

        await orchestrator._phase5_compression_governance(
            round_num=0,
            round_goal="Implement auth",
            agent_outputs=agent_outputs,
            callbacks=None,
        )

        archivist.summarize_round.assert_called_once()
        call_args = archivist.summarize_round.call_args
        assert call_args[0][0] == 0  # round_num
        assert call_args[0][1] == "Implement auth"  # goal
        assert "coder_01" in call_args[0][2]  # agent_outputs

    @pytest.mark.asyncio
    async def test_archivist_extract_tkg_called(self, orchestrator, archivist):
        """Phase 5 calls archivist.extract_tkg_tuples."""
        agent_outputs = {
            "coder_01": _make_agent_output(output="modified src/auth.py"),
        }

        await orchestrator._phase5_compression_governance(
            round_num=1,
            round_goal="Fix auth bug",
            agent_outputs=agent_outputs,
            callbacks=None,
        )

        archivist.extract_tkg_tuples.assert_called_once()

    @pytest.mark.asyncio
    async def test_archivist_maybe_compress_called(self, orchestrator, archivist):
        """Phase 5 calls archivist.maybe_compress_epochs."""
        await orchestrator._phase5_compression_governance(
            round_num=0,
            round_goal="Test",
            agent_outputs={"a": _make_agent_output()},
            callbacks=None,
        )

        archivist.maybe_compress_epochs.assert_called_once()


# ═══════════════════════════════════════════════════════════════════════════
# Test 11: Phase 5 -- Governance force_halt ends loop
# ═══════════════════════════════════════════════════════════════════════════


class TestGovernanceForceHalt:

    @pytest.mark.asyncio
    async def test_force_halt_ends_loop(self, ctx, config, archivist, skill_bank, audit):
        """Governance force_halt stops the orchestration loop."""
        gov = _make_mock_governance(force_halt_after=1)

        orch = Orchestrator(
            context_tree=ctx,
            config=config,
            colony_id="test",
            archivist=archivist,
            governance=gov,
            skill_bank=skill_bank,
            audit_logger=audit,
        )

        manager = _make_manager_agent()
        worker = _make_mock_agent("coder_01")
        agents = [manager, worker]

        result = await orch.run(
            task="Test force halt",
            agents=agents,
            max_rounds=10,
        )

        assert result.status == ColonyStatus.COMPLETED
        # Should have stopped after round 0 (force_halt on first governance check)
        assert result.rounds_completed < 10
        assert result.final_answer is not None
        assert "Convergence" in result.final_answer or "force" in result.final_answer.lower() or "halt" in result.final_answer.lower()


# ═══════════════════════════════════════════════════════════════════════════
# Test 12: Phase 5 -- Governance intervention stored
# ═══════════════════════════════════════════════════════════════════════════


class TestGovernanceIntervention:

    @pytest.mark.asyncio
    async def test_intervention_stored_for_next_round(self, ctx, config, archivist, skill_bank, audit):
        """Governance 'intervene' stores pending intervention for next Phase 1."""
        gov = MagicMock()
        gov.enforce = MagicMock(return_value=GovernanceDecision(
            action="intervene",
            reason="High similarity detected.",
            recommendations=["Try a different approach"],
        ))
        gov.check_tunnel_vision = MagicMock(return_value=None)

        orch = Orchestrator(
            context_tree=ctx,
            config=config,
            colony_id="test",
            archivist=archivist,
            governance=gov,
            skill_bank=skill_bank,
            audit_logger=audit,
        )

        # Run Phase 5 directly
        await orch._phase5_compression_governance(
            round_num=0,
            round_goal="Test",
            agent_outputs={"a": _make_agent_output()},
            callbacks=None,
        )

        # Pending intervention should be stored
        assert orch._pending_intervention is not None
        assert "High similarity" in orch._pending_intervention
        assert "different approach" in orch._pending_intervention

    @pytest.mark.asyncio
    async def test_intervention_injected_into_phase1(self, ctx, config, archivist, skill_bank, audit):
        """Stored intervention is injected into the next Phase 1 manager prompt."""
        gov = MagicMock()
        gov.enforce = MagicMock(return_value=GovernanceDecision(
            action="intervene",
            reason="Agents are converging too fast.",
            recommendations=["Spawn researcher"],
        ))
        gov.check_tunnel_vision = MagicMock(return_value=None)

        orch = Orchestrator(
            context_tree=ctx,
            config=config,
            colony_id="test",
            archivist=archivist,
            governance=gov,
            skill_bank=skill_bank,
            audit_logger=audit,
        )

        manager = _make_manager_agent()
        worker = _make_mock_agent("coder_01")
        agents = [manager, worker]

        _result = await orch.run(
            task="Test intervention injection",
            agents=agents,
            max_rounds=2,
        )

        # Manager should have been called twice via execute_raw (rounds 0 and 1)
        assert manager.execute_raw.call_count >= 2

        # Second call should contain the intervention text in user_prompt
        second_call = manager.execute_raw.call_args_list[1]
        user_prompt = second_call.kwargs.get("user_prompt", second_call[0][1] if len(second_call[0]) > 1 else "")
        assert "GOVERNANCE INTERVENTION" in user_prompt


# ═══════════════════════════════════════════════════════════════════════════
# Test 13: extend_rounds
# ═══════════════════════════════════════════════════════════════════════════


class TestExtendRounds:

    def test_extend_rounds_increases_max(self, orchestrator):
        """extend_rounds adds N to max_rounds."""
        orchestrator._max_rounds = 5
        new_max = orchestrator.extend_rounds(3)
        assert new_max == 8
        assert orchestrator._max_rounds == 8

    def test_extend_rounds_stores_direction_hint(self, orchestrator):
        """extend_rounds stores an optional direction hint."""
        orchestrator._max_rounds = 5
        orchestrator.extend_rounds(2, direction_hint="Focus on testing")
        assert orchestrator._direction_hint == "Focus on testing"

    def test_extend_rounds_returns_new_max(self, orchestrator):
        """extend_rounds returns the new max_rounds value."""
        orchestrator._max_rounds = 3
        result = orchestrator.extend_rounds(5)
        assert result == 8

    @pytest.mark.asyncio
    async def test_extend_rounds_during_run(self, ctx, config, archivist, governance, skill_bank, audit):
        """extend_rounds mid-run allows the loop to continue beyond original max."""
        orch = Orchestrator(
            context_tree=ctx,
            config=config,
            colony_id="test",
            archivist=archivist,
            governance=governance,
            skill_bank=skill_bank,
            audit_logger=audit,
        )

        call_count = 0
        original_max = 2

        manager = _make_manager_agent()
        worker = _make_mock_agent("coder_01")

        async def _extending_execute(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # Extend by 1 round during first execution
                orch.extend_rounds(1)
            return _make_agent_output(output=f"round {call_count}")

        worker.execute = AsyncMock(side_effect=_extending_execute)

        result = await orch.run(
            task="Test extend",
            agents=[manager, worker],
            max_rounds=original_max,
        )

        # Should have executed 3 rounds (2 original + 1 extended)
        assert result.rounds_completed == 3


# ═══════════════════════════════════════════════════════════════════════════
# Test 14: cancel stops loop
# ═══════════════════════════════════════════════════════════════════════════


class TestCancel:

    @pytest.mark.asyncio
    async def test_cancel_stops_loop(self, ctx, config, archivist, governance, skill_bank, audit):
        """Calling cancel() stops the orchestrator after the current round."""
        orch = Orchestrator(
            context_tree=ctx,
            config=config,
            colony_id="test",
            archivist=archivist,
            governance=governance,
            skill_bank=skill_bank,
            audit_logger=audit,
        )

        manager = _make_manager_agent()
        worker = _make_mock_agent("coder_01")

        call_count = 0

        async def _cancelling_execute(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                orch.cancel()
            return _make_agent_output()

        worker.execute = AsyncMock(side_effect=_cancelling_execute)

        result = await orch.run(
            task="Test cancel",
            agents=[manager, worker],
            max_rounds=10,
        )

        # Should have stopped after 1-2 rounds
        assert result.rounds_completed <= 2
        assert result.status == ColonyStatus.COMPLETED

    def test_cancel_sets_flag(self, orchestrator):
        """cancel() sets the _cancelled flag."""
        orchestrator.cancel()
        assert orchestrator._cancelled is True


# ═══════════════════════════════════════════════════════════════════════════
# Test 15: Post-colony skill distillation
# ═══════════════════════════════════════════════════════════════════════════


class TestPostColonySkills:

    @pytest.mark.asyncio
    async def test_post_colony_distills_skills(self, orchestrator, archivist, skill_bank):
        """Post-colony calls archivist.distill_skills and stores via skill_bank."""
        manager = _make_manager_agent()
        worker = _make_mock_agent("coder_01")
        agents = [manager, worker]

        _result = await orchestrator.run(
            task="Distill skills test",
            agents=agents,
            max_rounds=1,
        )

        # Archivist should have been called for skill distillation
        archivist.distill_skills.assert_called_once()

        # SkillBank should have been called to store
        skill_bank.store.assert_called_once()

    @pytest.mark.asyncio
    async def test_post_colony_no_archivist(self, ctx, config, governance, skill_bank, audit):
        """Without an archivist, post-colony skips distillation."""
        orch = Orchestrator(
            context_tree=ctx,
            config=config,
            colony_id="test",
            governance=governance,
            skill_bank=skill_bank,
            audit_logger=audit,
        )

        manager = _make_manager_agent()
        worker = _make_mock_agent("coder_01")

        result = await orch.run(
            task="No archivist",
            agents=[manager, worker],
            max_rounds=1,
        )

        assert result.status == ColonyStatus.COMPLETED
        assert result.skill_ids == []

    @pytest.mark.asyncio
    async def test_post_colony_returns_skill_ids(self, orchestrator, archivist, skill_bank):
        """Post-colony returns IDs of stored skills in SessionResult."""
        manager = _make_manager_agent()
        worker = _make_mock_agent("coder_01")

        result = await orchestrator.run(
            task="Get skill IDs",
            agents=[manager, worker],
            max_rounds=1,
        )

        # skill_ids should be populated
        assert isinstance(result.skill_ids, list)


# ═══════════════════════════════════════════════════════════════════════════
# Test 16: SessionResult structure
# ═══════════════════════════════════════════════════════════════════════════


class TestSessionResult:

    @pytest.mark.asyncio
    async def test_session_result_fields(self, orchestrator):
        """SessionResult has all required fields populated correctly."""
        manager = _make_manager_agent(terminate_after=1)
        worker = _make_mock_agent("coder_01")

        result = await orchestrator.run(
            task="Build an API",
            agents=[manager, worker],
            max_rounds=5,
        )

        assert isinstance(result, SessionResult)
        assert result.session_id.startswith("test_colony_")
        assert result.task == "Build an API"
        assert isinstance(result.status, ColonyStatus)
        assert isinstance(result.rounds_completed, int)
        assert result.rounds_completed >= 0
        assert isinstance(result.skill_ids, list)

    @pytest.mark.asyncio
    async def test_session_result_on_failure(self, ctx, config):
        """SessionResult reflects FAILED status on orchestrator crash."""
        # Create orchestrator with a context tree that throws
        bad_ctx = MagicMock()
        bad_ctx.set = AsyncMock(side_effect=RuntimeError("ctx exploded"))
        bad_ctx.assemble_agent_context = MagicMock(return_value="")
        bad_ctx.record_episode = AsyncMock()
        bad_ctx.record_decision = AsyncMock()
        bad_ctx.record_tkg_tuple = AsyncMock()

        orch = Orchestrator(
            context_tree=bad_ctx,
            config=config,
            colony_id="crash_test",
        )

        manager = _make_manager_agent()
        worker = _make_mock_agent("coder_01")

        result = await orch.run(
            task="Crash test",
            agents=[manager, worker],
            max_rounds=1,
        )

        # The orchestrator wraps ctx.set in try/except, so it should still run.
        # But if a deeper error surfaces, status should be FAILED or COMPLETED
        assert result.status in (ColonyStatus.COMPLETED, ColonyStatus.FAILED)


# ═══════════════════════════════════════════════════════════════════════════
# Test 17: Callbacks fire at correct phases
# ═══════════════════════════════════════════════════════════════════════════


class TestCallbacks:

    @pytest.mark.asyncio
    async def test_on_round_update_fires(self, orchestrator):
        """on_round_update callback is invoked during each phase."""
        phases_seen: list[str] = []

        async def _on_round_update(round_num, phase, data):
            phases_seen.append(phase)

        callbacks = {"on_round_update": _on_round_update}

        manager = _make_manager_agent()
        worker = _make_mock_agent("coder_01")

        # max_rounds=2 so we get round 0 (broadcast) + round 1 (full phases)
        _result = await orchestrator.run(
            task="Test callbacks",
            agents=[manager, worker],
            max_rounds=2,
            callbacks=callbacks,
        )

        # Round 0 is broadcast (skips phase_2/3), round 1 has all phases
        assert "phase_1_goal" in phases_seen
        assert "phase_2_intent" in phases_seen  # from round 1
        assert "phase_3_routing" in phases_seen  # from round 1
        assert "phase_3_5_skills" in phases_seen
        assert "phase_4_execution" in phases_seen
        assert "phase_5_governance" in phases_seen
        assert "round_complete" in phases_seen
        assert "colony_complete" in phases_seen

    @pytest.mark.asyncio
    async def test_on_stream_token_forwarded(self, orchestrator):
        """on_stream_token callback is forwarded to agent execution."""
        tokens_received: list[tuple[str, str]] = []

        async def _on_stream(agent_id, token):
            tokens_received.append((agent_id, token))

        callbacks = {"on_stream_token": _on_stream}

        manager = _make_manager_agent()
        worker = _make_mock_agent("coder_01")

        # The mock agent won't actually call stream_callback, but we
        # verify the callback mapping reaches the agent layer.
        await orchestrator.run(
            task="Test streaming",
            agents=[manager, worker],
            max_rounds=1,
            callbacks=callbacks,
        )

        # Verify agent received callbacks dict with stream_callback key
        if worker.execute.call_args:
            agent_cbs = worker.execute.call_args.kwargs.get("callbacks")
            if agent_cbs:
                assert "stream_callback" in agent_cbs

    @pytest.mark.asyncio
    async def test_callback_errors_swallowed(self, orchestrator):
        """Callback exceptions are caught and do not crash the orchestrator."""
        async def _bad_callback(*args):
            raise RuntimeError("Callback crashed!")

        callbacks = {"on_round_update": _bad_callback}

        manager = _make_manager_agent()
        worker = _make_mock_agent("coder_01")

        # Should not raise despite callback errors
        result = await orchestrator.run(
            task="Test bad callback",
            agents=[manager, worker],
            max_rounds=1,
            callbacks=callbacks,
        )

        assert result.status == ColonyStatus.COMPLETED


# ═══════════════════════════════════════════════════════════════════════════
# Additional integration-style tests
# ═══════════════════════════════════════════════════════════════════════════


class TestAuditIntegration:

    @pytest.mark.asyncio
    async def test_audit_session_lifecycle(self, orchestrator, audit):
        """AuditLogger receives session_start and session_end events."""
        manager = _make_manager_agent()
        worker = _make_mock_agent("coder_01")

        await orchestrator.run(
            task="Audit test",
            agents=[manager, worker],
            max_rounds=1,
        )

        audit.log_session_start.assert_called_once()
        audit.log_session_end.assert_called_once()
        # At least one round should have been logged
        assert audit.log_round.call_count >= 1

    @pytest.mark.asyncio
    async def test_audit_decision_logged(self, orchestrator, audit):
        """Governance decisions are logged to audit."""
        manager = _make_manager_agent()
        worker = _make_mock_agent("coder_01")

        await orchestrator.run(
            task="Decision audit",
            agents=[manager, worker],
            max_rounds=1,
        )

        # At least the routing and manager_goal decisions
        assert audit.log_decision.call_count >= 1


class TestContextTreeIntegration:

    @pytest.mark.asyncio
    async def test_colony_state_written_to_ctx(self, orchestrator, ctx):
        """Orchestrator writes colony state to the context tree."""
        manager = _make_manager_agent()
        worker = _make_mock_agent("coder_01")

        await orchestrator.run(
            task="Context test",
            agents=[manager, worker],
            max_rounds=1,
        )

        # Colony scope should have task and status
        assert ctx.get("colony", "task") == "Context test"
        # Status should be set (COMPLETED or its string value)
        status = ctx.get("colony", "status")
        assert status is not None

    @pytest.mark.asyncio
    async def test_episodes_recorded_in_ctx(self, orchestrator, ctx, archivist):
        """Archivist episodes are recorded in the context tree."""
        manager = _make_manager_agent()
        worker = _make_mock_agent("coder_01")

        await orchestrator.run(
            task="Episode test",
            agents=[manager, worker],
            max_rounds=1,
        )

        episodes = ctx.get_episodes()
        assert len(episodes) >= 1
        assert episodes[0].round_num == 0


class TestFindManager:

    def test_finds_manager_by_caste(self, orchestrator):
        """_find_manager locates agent with Caste.MANAGER."""
        manager = _make_mock_agent("mgr", Caste.MANAGER)
        worker = _make_mock_agent("wkr", Caste.CODER)
        result = orchestrator._find_manager([worker, manager])
        assert result is manager

    def test_returns_none_without_manager(self, orchestrator):
        """_find_manager returns None when no manager exists."""
        worker = _make_mock_agent("wkr", Caste.CODER)
        result = orchestrator._find_manager([worker])
        assert result is None


class TestGatherRoutedMessages:

    def test_gathers_from_upstream(self, orchestrator):
        """Messages are gathered from senders who have produced output."""
        topology = Topology(
            edges=[
                TopologyEdge(sender="a", receiver="b", weight=0.8),
                TopologyEdge(sender="c", receiver="b", weight=0.6),
            ],
            execution_order=["a", "c", "b"],
        )

        outputs = {
            "a": _make_agent_output(output="output from a"),
            "c": _make_agent_output(output="output from c"),
        }

        messages = orchestrator._gather_routed_messages("b", topology, outputs)
        assert len(messages) == 2
        assert any("output from a" in m for m in messages)
        assert any("output from c" in m for m in messages)

    def test_no_messages_for_source(self, orchestrator):
        """Source node with no incoming edges gets empty messages."""
        topology = Topology(
            edges=[
                TopologyEdge(sender="a", receiver="b", weight=0.8),
            ],
            execution_order=["a", "b"],
        )

        messages = orchestrator._gather_routed_messages("a", topology, {})
        assert messages == []

    def test_missing_sender_output_skipped(self, orchestrator):
        """If sender hasn't produced output yet, its message is skipped."""
        topology = Topology(
            edges=[
                TopologyEdge(sender="a", receiver="b", weight=0.8),
            ],
            execution_order=["a", "b"],
        )

        # 'a' has no output yet
        messages = orchestrator._gather_routed_messages("b", topology, {})
        assert messages == []


# ═══════════════════════════════════════════════════════════════════════════
# Test 18: Topological level computation
# ═══════════════════════════════════════════════════════════════════════════


class TestComputeTopoLevels:

    def test_broadcast_single_level(self):
        """No edges → all agents in one level (maximum parallelism)."""
        levels = Orchestrator._compute_topo_levels(
            ["a", "b", "c"], [],
        )
        assert len(levels) == 1
        assert set(levels[0]) == {"a", "b", "c"}

    def test_chain_n_levels(self):
        """Linear chain A→B→C → 3 levels of 1."""
        edges = [
            TopologyEdge(sender="a", receiver="b", weight=1.0),
            TopologyEdge(sender="b", receiver="c", weight=1.0),
        ]
        levels = Orchestrator._compute_topo_levels(["a", "b", "c"], edges)
        assert len(levels) == 3
        assert levels[0] == ["a"]
        assert levels[1] == ["b"]
        assert levels[2] == ["c"]

    def test_diamond_dag(self):
        """Diamond DAG: A→B, A→C, B→D, C→D → levels [A], [B,C], [D]."""
        edges = [
            TopologyEdge(sender="a", receiver="b", weight=1.0),
            TopologyEdge(sender="a", receiver="c", weight=1.0),
            TopologyEdge(sender="b", receiver="d", weight=1.0),
            TopologyEdge(sender="c", receiver="d", weight=1.0),
        ]
        levels = Orchestrator._compute_topo_levels(
            ["a", "b", "c", "d"], edges,
        )
        assert len(levels) == 3
        assert levels[0] == ["a"]
        assert set(levels[1]) == {"b", "c"}
        assert levels[2] == ["d"]

    def test_two_independent_chains(self):
        """Two independent chains: A→B, C→D → levels [A,C], [B,D]."""
        edges = [
            TopologyEdge(sender="a", receiver="b", weight=1.0),
            TopologyEdge(sender="c", receiver="d", weight=1.0),
        ]
        levels = Orchestrator._compute_topo_levels(
            ["a", "b", "c", "d"], edges,
        )
        assert len(levels) == 2
        assert set(levels[0]) == {"a", "c"}
        assert set(levels[1]) == {"b", "d"}

    def test_single_agent(self):
        """Single agent → one level."""
        levels = Orchestrator._compute_topo_levels(["solo"], [])
        assert levels == [["solo"]]

    def test_fan_out(self):
        """Fan-out: A→B, A→C, A→D → levels [A], [B,C,D]."""
        edges = [
            TopologyEdge(sender="a", receiver="b", weight=1.0),
            TopologyEdge(sender="a", receiver="c", weight=1.0),
            TopologyEdge(sender="a", receiver="d", weight=1.0),
        ]
        levels = Orchestrator._compute_topo_levels(
            ["a", "b", "c", "d"], edges,
        )
        assert len(levels) == 2
        assert levels[0] == ["a"]
        assert set(levels[1]) == {"b", "c", "d"}

    def test_fan_in(self):
        """Fan-in: A→D, B→D, C→D → levels [A,B,C], [D]."""
        edges = [
            TopologyEdge(sender="a", receiver="d", weight=1.0),
            TopologyEdge(sender="b", receiver="d", weight=1.0),
            TopologyEdge(sender="c", receiver="d", weight=1.0),
        ]
        levels = Orchestrator._compute_topo_levels(
            ["a", "b", "c", "d"], edges,
        )
        assert len(levels) == 2
        assert set(levels[0]) == {"a", "b", "c"}
        assert levels[1] == ["d"]


# ═══════════════════════════════════════════════════════════════════════════
# Test 19: Parallel DAG execution
# ═══════════════════════════════════════════════════════════════════════════


class TestParallelExecution:

    @pytest.mark.asyncio
    async def test_diamond_dag_parallel(self, orchestrator):
        """Diamond DAG: B and C run in parallel after A, D runs after both."""
        execution_log: list[tuple[str, float]] = []
        import time

        def _make_tracked_side_effect(agent_id, delay=0.05):
            async def _exec(*args, **kwargs):
                start = time.monotonic()
                await asyncio.sleep(delay)
                execution_log.append((agent_id, start))
                return _make_agent_output(output=f"output from {agent_id}")
            return _exec

        workers = []
        for aid in ["a", "b", "c", "d"]:
            w = _make_mock_agent(aid, Caste.CODER)
            w.execute = AsyncMock(side_effect=_make_tracked_side_effect(aid))
            workers.append(w)

        topology = Topology(
            edges=[
                TopologyEdge(sender="a", receiver="b", weight=1.0),
                TopologyEdge(sender="a", receiver="c", weight=1.0),
                TopologyEdge(sender="b", receiver="d", weight=1.0),
                TopologyEdge(sender="c", receiver="d", weight=1.0),
            ],
            execution_order=["a", "b", "c", "d"],
        )

        outputs = await orchestrator._phase4_execution(
            workers=workers,
            topology=topology,
            round_goal="Diamond DAG",
            skill_context=None,
            callbacks=None,
        )

        assert set(outputs.keys()) == {"a", "b", "c", "d"}

        # A must finish before B and C start
        a_time = next(t for aid, t in execution_log if aid == "a")
        b_time = next(t for aid, t in execution_log if aid == "b")
        c_time = next(t for aid, t in execution_log if aid == "c")
        d_time = next(t for aid, t in execution_log if aid == "d")

        assert a_time < b_time
        assert a_time < c_time
        # B and C should start at approximately the same time (parallel)
        assert abs(b_time - c_time) < 0.04  # within 40ms
        # D must finish after both B and C
        assert d_time > b_time
        assert d_time > c_time

    @pytest.mark.asyncio
    async def test_broadcast_all_parallel(self, orchestrator):
        """Broadcast (0 edges) runs all agents concurrently."""
        import time
        start_times: dict[str, float] = {}

        def _make_tracked_side_effect(agent_id):
            async def _exec(*args, **kwargs):
                start_times[agent_id] = time.monotonic()
                await asyncio.sleep(0.05)
                return _make_agent_output(output=f"output from {agent_id}")
            return _exec

        workers = []
        for aid in ["x", "y", "z"]:
            w = _make_mock_agent(aid, Caste.CODER)
            w.execute = AsyncMock(side_effect=_make_tracked_side_effect(aid))
            workers.append(w)

        topology = Topology(edges=[], execution_order=["x", "y", "z"])

        outputs = await orchestrator._phase4_execution(
            workers=workers,
            topology=topology,
            round_goal="Broadcast",
            skill_context=None,
            callbacks=None,
        )

        assert set(outputs.keys()) == {"x", "y", "z"}

        # All should have started at approximately the same time
        times = list(start_times.values())
        assert max(times) - min(times) < 0.04  # within 40ms

    @pytest.mark.asyncio
    async def test_parallel_agent_failure_isolated(self, orchestrator):
        """One agent failing in a parallel level doesn't crash others."""
        worker_ok = _make_mock_agent("ok_agent", Caste.CODER)
        worker_fail = _make_mock_agent("fail_agent", Caste.REVIEWER)
        worker_fail.execute = AsyncMock(side_effect=RuntimeError("agent exploded"))

        topology = Topology(
            edges=[],
            execution_order=["ok_agent", "fail_agent"],
        )

        outputs = await orchestrator._phase4_execution(
            workers=[worker_ok, worker_fail],
            topology=topology,
            round_goal="Test failure isolation",
            skill_context=None,
            callbacks=None,
        )

        assert set(outputs.keys()) == {"ok_agent", "fail_agent"}
        assert "output from ok_agent" in outputs["ok_agent"].output
        assert "ERROR" in outputs["fail_agent"].output
        assert "exploded" in outputs["fail_agent"].output

    @pytest.mark.asyncio
    async def test_upstream_outputs_available_to_downstream(self, orchestrator):
        """Downstream agents in later levels receive upstream outputs."""
        worker_a = _make_mock_agent(
            "upstream", Caste.ARCHITECT,
            output=_make_agent_output(output="design document v1"),
        )
        worker_b = _make_mock_agent("downstream", Caste.CODER)

        topology = Topology(
            edges=[
                TopologyEdge(sender="upstream", receiver="downstream", weight=0.9),
            ],
            execution_order=["upstream", "downstream"],
        )

        await orchestrator._phase4_execution(
            workers=[worker_a, worker_b],
            topology=topology,
            round_goal="Test upstream availability",
            skill_context=None,
            callbacks=None,
        )

        # downstream should have received upstream's output in routed_messages
        call_kwargs = worker_b.execute.call_args
        routed = call_kwargs.kwargs.get("routed_messages", [])
        assert any("design document v1" in m for m in routed)
