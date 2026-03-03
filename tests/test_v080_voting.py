"""
Tests for FormicOS v0.8.0 Voting Parallelism.

Covers:
  - VotingNodeConfig and VotingGroupResult model validation
  - ColonyConfig.voting_nodes field (default empty, populated)
  - ColonyCreateRequest.voting_nodes field
  - 3-replica parallel execution + output collection
  - Replica fault isolation (1 fails, 2 succeed)
  - Workspace subdirectory creation + isolation
  - Seed divergence (42, 43, 44)
  - Synthetic edges injected for reviewer
  - Voting disabled by default (empty voting_nodes)
  - configure_voting_nodes() method
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agents import AgentOutput
from src.context import AsyncContextTree
from src.models import (
    ColonyConfig,
    ColonyCreateRequest,
    Topology,
    VotingGroupResult,
    VotingNodeConfig,
)


# ── Model Validation ─────────────────────────────────────────────────────


class TestVotingNodeConfigModel:
    """VotingNodeConfig Pydantic model tests."""

    def test_voting_node_config_defaults(self):
        """Minimal config with defaults."""
        cfg = VotingNodeConfig(
            node_id="coder_01",
            reviewer_agent_id="reviewer_01",
        )
        assert cfg.node_id == "coder_01"
        assert cfg.caste == "coder"
        assert cfg.replicas == 3
        assert cfg.reviewer_agent_id == "reviewer_01"
        assert cfg.workspace_strategy == "subdirectory"
        assert cfg.test_command is None
        assert cfg.merge_strategy == "reviewer_pick"

    def test_voting_node_config_custom(self):
        """All fields customized."""
        cfg = VotingNodeConfig(
            node_id="solver",
            caste="architect",
            replicas=5,
            reviewer_agent_id="judge",
            workspace_strategy="git_worktree",
            test_command="pytest -x",
            merge_strategy="first_passing",
        )
        assert cfg.replicas == 5
        assert cfg.test_command == "pytest -x"

    def test_voting_node_config_replicas_bounds(self):
        """Replicas must be between 2 and 7."""
        with pytest.raises(Exception):  # ValidationError
            VotingNodeConfig(
                node_id="n", reviewer_agent_id="r", replicas=1,
            )
        with pytest.raises(Exception):
            VotingNodeConfig(
                node_id="n", reviewer_agent_id="r", replicas=8,
            )

    def test_voting_node_config_empty_node_id_rejected(self):
        """node_id cannot be empty."""
        with pytest.raises(Exception):
            VotingNodeConfig(node_id="", reviewer_agent_id="r")
        with pytest.raises(Exception):
            VotingNodeConfig(node_id="   ", reviewer_agent_id="r")


class TestVotingGroupResultModel:
    """VotingGroupResult Pydantic model tests."""

    def test_voting_group_result_defaults(self):
        """Minimal result with defaults."""
        result = VotingGroupResult(node_id="coder_01")
        assert result.replica_outputs == {}
        assert result.test_results == {}
        assert result.selected_replica is None
        assert result.reviewer_rationale == ""

    def test_voting_group_result_populated(self):
        """Full result with data."""
        result = VotingGroupResult(
            node_id="coder_01",
            replica_outputs={
                "coder_01_replica_0": "solution A",
                "coder_01_replica_1": "solution B",
            },
            test_results={
                "coder_01_replica_0": "PASS",
                "coder_01_replica_1": "FAIL",
            },
            selected_replica="coder_01_replica_0",
            reviewer_rationale="Replica 0 passed all tests.",
        )
        assert len(result.replica_outputs) == 2
        assert result.selected_replica == "coder_01_replica_0"


class TestColonyConfigVotingNodes:
    """ColonyConfig.voting_nodes field tests."""

    def test_colony_config_voting_nodes_default_empty(self):
        """voting_nodes defaults to empty list (backward compat)."""
        cfg = ColonyConfig(colony_id="c1", task="test")
        assert cfg.voting_nodes == []

    def test_colony_config_with_voting_nodes(self):
        """voting_nodes can be populated."""
        vn = VotingNodeConfig(
            node_id="coder_01",
            reviewer_agent_id="reviewer_01",
        )
        cfg = ColonyConfig(colony_id="c1", task="test", voting_nodes=[vn])
        assert len(cfg.voting_nodes) == 1
        assert cfg.voting_nodes[0].node_id == "coder_01"

    def test_colony_create_request_voting_nodes(self):
        """ColonyCreateRequest also accepts voting_nodes."""
        vn = VotingNodeConfig(
            node_id="coder_01",
            reviewer_agent_id="reviewer_01",
        )
        req = ColonyCreateRequest(
            name="Test",
            task="Build",
            voting_nodes=[vn],
        )
        assert len(req.voting_nodes) == 1


# ── Orchestrator Voting ──────────────────────────────────────────────────


def _make_mock_config():
    """Create a minimal mock config for orchestrator tests."""
    config = MagicMock()
    config.inference = MagicMock()
    config.inference.model = "test-model"
    config.inference.timeout_seconds = 60
    config.convergence = MagicMock()
    config.convergence.similarity_threshold = 0.95
    config.convergence.rounds_before_force_halt = 2
    config.routing = MagicMock()
    config.routing.tau = 0.35
    config.routing.k_in = 3
    config.routing.broadcast_fallback = True
    return config


def _make_mock_agent(agent_id, caste="coder", output_text=None):
    """Create a mock Agent for voting tests."""
    agent = MagicMock()
    agent.id = agent_id
    agent.caste = caste
    agent.system_prompt = "You are a coder."
    agent.model_client = MagicMock()
    agent.model_name = "test-model"
    agent.tools = []
    agent.config = {"workspace_root": "./workspace", "seed": 42}
    agent.seed = 42
    agent.workspace_root = "./workspace"

    out = AgentOutput(output=output_text or f"output from {agent_id}")
    agent.execute = AsyncMock(return_value=out)
    agent.generate_intent = AsyncMock(return_value={"key": "test", "query": "test"})
    agent.cancel = MagicMock()

    return agent


class TestConfigureVotingNodes:
    """Test configure_voting_nodes() method."""

    def test_configure_voting_nodes_populates_dict(self):
        """configure_voting_nodes() populates _voting_configs."""
        from src.orchestrator import Orchestrator

        ctx = AsyncContextTree()
        config = _make_mock_config()
        orch = Orchestrator(context_tree=ctx, config=config, colony_id="c1")

        vn1 = VotingNodeConfig(node_id="coder_01", reviewer_agent_id="reviewer_01")
        vn2 = VotingNodeConfig(node_id="coder_02", reviewer_agent_id="reviewer_01")

        orch.configure_voting_nodes([vn1, vn2])

        assert "coder_01" in orch._voting_configs
        assert "coder_02" in orch._voting_configs
        assert orch._voting_configs["coder_01"].replicas == 3

    def test_voting_disabled_by_default(self):
        """Without configure_voting_nodes, _voting_configs is empty."""
        from src.orchestrator import Orchestrator

        ctx = AsyncContextTree()
        config = _make_mock_config()
        orch = Orchestrator(context_tree=ctx, config=config, colony_id="c1")

        assert orch._voting_configs == {}


class TestExecuteVotingGroup:
    """Test _execute_voting_group() method."""

    @pytest.mark.asyncio
    async def test_voting_group_3_replicas_succeed(self, tmp_path):
        """3 replicas all succeed — outputs stored, edges injected."""
        from src.orchestrator import Orchestrator

        ctx = AsyncContextTree()
        config = _make_mock_config()
        orch = Orchestrator(context_tree=ctx, config=config, colony_id="c1")

        vn = VotingNodeConfig(node_id="coder_01", reviewer_agent_id="reviewer_01")
        orch.configure_voting_nodes([vn])

        # Create mock agent with tmp workspace
        agent = _make_mock_agent("coder_01")
        agent.workspace_root = str(tmp_path / "workspace")
        agent.config["workspace_root"] = str(tmp_path / "workspace")

        topology = Topology(
            edges=[],
            execution_order=["coder_01", "reviewer_01"],
            density=0.0,
            isolated_agents=[],
        )
        agent_outputs = {}

        # Mock Agent constructor to return mock agents
        mock_replica_output = AgentOutput(output="replica solution")
        with patch("src.orchestrator.Agent") as MockAgent:
            mock_instance = MagicMock()
            mock_instance.execute = AsyncMock(return_value=mock_replica_output)
            MockAgent.return_value = mock_instance

            node_id, result = await orch._execute_voting_group(
                agent, topology, agent_outputs,
                "Solve the problem", None, None,
            )

        assert node_id == "coder_01"
        assert result.output == "replica solution"

        # All 3 replica outputs should be in agent_outputs
        assert "coder_01_replica_0" in agent_outputs
        assert "coder_01_replica_1" in agent_outputs
        assert "coder_01_replica_2" in agent_outputs

        # Synthetic edges injected to reviewer
        reviewer_edges = [
            e for e in topology.edges
            if e.receiver == "reviewer_01"
        ]
        assert len(reviewer_edges) == 3

    @pytest.mark.asyncio
    async def test_voting_group_partial_failure(self, tmp_path):
        """1 replica fails, 2 succeed — fault isolation works."""
        from src.orchestrator import Orchestrator

        ctx = AsyncContextTree()
        config = _make_mock_config()
        orch = Orchestrator(context_tree=ctx, config=config, colony_id="c1")

        vn = VotingNodeConfig(
            node_id="coder_01",
            reviewer_agent_id="reviewer_01",
            replicas=3,
        )
        orch.configure_voting_nodes([vn])

        agent = _make_mock_agent("coder_01")
        agent.workspace_root = str(tmp_path / "workspace")
        agent.config["workspace_root"] = str(tmp_path / "workspace")

        topology = Topology(
            edges=[], execution_order=["coder_01"], density=0.0, isolated_agents=[],
        )
        agent_outputs = {}

        call_count = 0

        async def _side_effect(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise RuntimeError("LLM timeout")
            return AgentOutput(output=f"solution {call_count}")

        with patch("src.orchestrator.Agent") as MockAgent:
            mock_instance = MagicMock()
            mock_instance.execute = AsyncMock(side_effect=_side_effect)
            MockAgent.return_value = mock_instance

            node_id, result = await orch._execute_voting_group(
                agent, topology, agent_outputs,
                "Solve the problem", None, None,
            )

        # Should still succeed (2 of 3 passed)
        assert node_id == "coder_01"
        # The first successful replica's output is returned
        assert "ERROR" not in result.output or "solution" in result.output

        # All 3 replicas should have entries in agent_outputs
        assert len([k for k in agent_outputs if k.startswith("coder_01_replica_")]) == 3

    @pytest.mark.asyncio
    async def test_voting_group_workspace_isolation(self, tmp_path):
        """Each replica gets its own subdirectory."""
        from src.orchestrator import Orchestrator

        ctx = AsyncContextTree()
        config = _make_mock_config()
        orch = Orchestrator(context_tree=ctx, config=config, colony_id="c1")

        vn = VotingNodeConfig(node_id="coder_01", reviewer_agent_id="reviewer_01")
        orch.configure_voting_nodes([vn])

        agent = _make_mock_agent("coder_01")
        workspace = tmp_path / "workspace"
        agent.workspace_root = str(workspace)
        agent.config["workspace_root"] = str(workspace)

        topology = Topology(
            edges=[], execution_order=["coder_01"], density=0.0, isolated_agents=[],
        )

        with patch("src.orchestrator.Agent") as MockAgent:
            mock_instance = MagicMock()
            mock_instance.execute = AsyncMock(
                return_value=AgentOutput(output="ok"),
            )
            MockAgent.return_value = mock_instance

            await orch._execute_voting_group(
                agent, topology, {}, "task", None, None,
            )

        # Check workspace subdirectories were created
        voting_dir = workspace / "_voting" / "coder_01"
        assert (voting_dir / "0").exists()
        assert (voting_dir / "1").exists()
        assert (voting_dir / "2").exists()

    @pytest.mark.asyncio
    async def test_voting_group_seed_divergence(self, tmp_path):
        """Each replica gets a different seed (base + i)."""
        from src.orchestrator import Orchestrator

        ctx = AsyncContextTree()
        config = _make_mock_config()
        orch = Orchestrator(context_tree=ctx, config=config, colony_id="c1")

        vn = VotingNodeConfig(node_id="coder_01", reviewer_agent_id="reviewer_01")
        orch.configure_voting_nodes([vn])

        agent = _make_mock_agent("coder_01")
        agent.seed = 42
        agent.workspace_root = str(tmp_path / "workspace")
        agent.config["workspace_root"] = str(tmp_path / "workspace")
        agent.config["seed"] = 42

        topology = Topology(
            edges=[], execution_order=["coder_01"], density=0.0, isolated_agents=[],
        )

        constructed_configs = []

        def capture_agent(*args, **kwargs):
            mock_agent = MagicMock()
            mock_agent.execute = AsyncMock(
                return_value=AgentOutput(output="ok"),
            )
            constructed_configs.append(kwargs.get("config", args[6] if len(args) > 6 else {}))
            return mock_agent

        with patch("src.orchestrator.Agent", side_effect=capture_agent):
            await orch._execute_voting_group(
                agent, topology, {}, "task", None, None,
            )

        # 3 replicas should have been created with seeds 42, 43, 44
        assert len(constructed_configs) == 3
        seeds = [c.get("seed") for c in constructed_configs]
        assert seeds == [42, 43, 44]


class TestPhase4VotingIntegration:
    """Test _phase4_execution() with voting nodes mixed with regular agents."""

    @pytest.mark.asyncio
    async def test_phase4_separates_regular_and_voting(self, tmp_path):
        """Phase 4 correctly separates regular agents from voting agents."""
        from src.orchestrator import Orchestrator

        ctx = AsyncContextTree()
        config = _make_mock_config()
        orch = Orchestrator(context_tree=ctx, config=config, colony_id="c1")

        vn = VotingNodeConfig(node_id="coder_01", reviewer_agent_id="reviewer_01")
        orch.configure_voting_nodes([vn])

        # Regular agent
        regular = _make_mock_agent("reviewer_01")
        # Voting agent
        voting = _make_mock_agent("coder_01")
        voting.workspace_root = str(tmp_path / "workspace")
        voting.config["workspace_root"] = str(tmp_path / "workspace")

        topology = Topology(
            edges=[],
            execution_order=["coder_01", "reviewer_01"],
            density=0.0,
            isolated_agents=[],
        )

        with patch("src.orchestrator.Agent") as MockAgent:
            mock_inst = MagicMock()
            mock_inst.execute = AsyncMock(
                return_value=AgentOutput(output="replica out"),
            )
            MockAgent.return_value = mock_inst

            outputs = await orch._phase4_execution(
                workers=[voting, regular],
                topology=topology,
                round_goal="Build it",
                skill_context=None,
                callbacks=None,
            )

        # Both agents should have outputs
        assert "coder_01" in outputs
        assert "reviewer_01" in outputs


class TestAllReplicasFail:
    """Edge case: all replicas fail."""

    @pytest.mark.asyncio
    async def test_all_replicas_fail_returns_error(self, tmp_path):
        """When all replicas fail, error output is returned."""
        from src.orchestrator import Orchestrator

        ctx = AsyncContextTree()
        config = _make_mock_config()
        orch = Orchestrator(context_tree=ctx, config=config, colony_id="c1")

        vn = VotingNodeConfig(node_id="coder_01", reviewer_agent_id="reviewer_01")
        orch.configure_voting_nodes([vn])

        agent = _make_mock_agent("coder_01")
        agent.workspace_root = str(tmp_path / "workspace")
        agent.config["workspace_root"] = str(tmp_path / "workspace")

        topology = Topology(
            edges=[], execution_order=["coder_01"], density=0.0, isolated_agents=[],
        )

        with patch("src.orchestrator.Agent") as MockAgent:
            mock_inst = MagicMock()
            mock_inst.execute = AsyncMock(
                side_effect=RuntimeError("all fail"),
            )
            MockAgent.return_value = mock_inst

            node_id, result = await orch._execute_voting_group(
                agent, topology, {}, "task", None, None,
            )

        assert "ERROR" in result.output
        assert "All 3 voting replicas failed" in result.output
