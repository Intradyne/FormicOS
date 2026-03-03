"""
FormicOS v0.6.0 -- Integration Tests

Cross-component workflow tests exercising multiple real modules together.
All external dependencies (LLM, Qdrant, MCP, SentenceTransformer) are mocked.
No Docker services required.

Scenarios:
  1. Context tree + episodic memory round-trip
  2. Governance convergence detection pipeline
  3. Governance path diversity + tunnel vision
  4. SkillBank store-retrieve-evolve cycle
  5. Router topology from pre-computed matrix
  6. Archivist summarization + TKG extraction
  7. Session manager save/restore lifecycle
  8. Agent context assembly with full state
  9. Approval gate request/respond flow
  10. Audit logger session event capture
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import numpy as np
import pytest

from src.approval import ApprovalGate
from src.archivist import Archivist
from src.audit import AuditLogger
from src.context import AsyncContextTree
from src.governance import GovernanceEngine
from src.models import (
    CasteConfig,
    ConvergenceConfig,
    Decision,
    DecisionType,
    EmbeddingConfig,
    Episode,
    EpochSummary,
    FormicOSConfig,
    HardwareConfig,
    IdentityConfig,
    InferenceConfig,
    MCPGatewayConfig,
    ModelBackendType,
    ModelRegistryEntry,
    PendingApproval,
    PersistenceConfig,
    QdrantConfig,
    RoutingConfig,
    Skill,
    SkillBankConfig,
    SkillTier,
    SubcasteMapEntry,
    SummarizationConfig,
    TeamsConfig,
    TemporalConfig,
    TKGTuple,
    Topology,
)
from src.router import build_topology_from_matrix
from src.session import SessionManager
from src.skill_bank import SkillBank


# ── Helpers ──────────────────────────────────────────────────────────────


def _make_config(**overrides: Any) -> FormicOSConfig:
    """Build a minimal valid FormicOSConfig for tests."""
    defaults = dict(
        schema_version="0.6.0",
        identity=IdentityConfig(name="TestOS", version="0.6.0"),
        hardware=HardwareConfig(gpu="test", vram_gb=24.0),
        inference=InferenceConfig(
            endpoint="http://localhost:8080/v1",
            model="test-model",
            timeout_seconds=10,
        ),
        embedding=EmbeddingConfig(
            model="test-embed",
            endpoint="http://localhost:8081/v1",
        ),
        routing=RoutingConfig(),
        convergence=ConvergenceConfig(
            similarity_threshold=0.95,
            rounds_before_force_halt=2,
        ),
        summarization=SummarizationConfig(),
        temporal=TemporalConfig(stall_repeat_threshold=3),
        castes={
            "manager": CasteConfig(system_prompt_file="manager.md"),
            "coder": CasteConfig(system_prompt_file="coder.md"),
        },
        persistence=PersistenceConfig(session_dir=".formicos/sessions"),
        qdrant=QdrantConfig(),
        mcp_gateway=MCPGatewayConfig(enabled=False),
        model_registry={
            "local/test-model": ModelRegistryEntry(
                model_id="local/test-model",
                backend=ModelBackendType.LLAMA_CPP,
                endpoint="http://localhost:8080/v1",
                context_length=32768,
                vram_gb=10.0,
            ),
        },
        skill_bank=SkillBankConfig(
            storage_file=".formicos/skill_bank.json",
            retrieval_top_k=3,
            dedup_threshold=0.85,
            evolution_interval=5,
            prune_zero_hit_after=10,
        ),
        subcaste_map={
            "heavy": SubcasteMapEntry(primary="local/test-model"),
            "balanced": SubcasteMapEntry(primary="local/test-model"),
            "light": SubcasteMapEntry(primary="local/test-model"),
        },
        teams=TeamsConfig(),
    )
    defaults.update(overrides)
    return FormicOSConfig(**defaults)


def _make_mock_embedder(dim: int = 8) -> MagicMock:
    """Create a mock embedder whose encode() returns distinct normalized vectors.

    Uses a call counter to produce orthogonal-ish vectors — each text gets a
    one-hot-like basis vector so cosine similarity between any two skills
    is guaranteed to be well below the dedup threshold (0.85).
    """
    embedder = MagicMock()
    _counter = [0]

    def _encode(texts, **kwargs):
        vecs = []
        for _ in texts:
            v = np.zeros(dim, dtype=np.float32)
            v[_counter[0] % dim] = 1.0
            # Add small noise so vectors sharing a basis slot are still distinct
            v += np.float32(0.01 * _counter[0])
            _counter[0] += 1
            vecs.append(v / np.linalg.norm(v))
        return np.array(vecs)

    embedder.encode = _encode
    return embedder


# ═══════════════════════════════════════════════════════════════════════════
# 1. Context Tree + Episodic Memory Round-Trip
# ═══════════════════════════════════════════════════════════════════════════


class TestContextTreeRoundTrip:
    """Verifies context tree can store state, episodes, TKG, decisions,
    serialize to disk, and restore identically."""

    @pytest.mark.asyncio
    async def test_full_round_trip(self, tmp_path: Path):
        ctx = AsyncContextTree(episode_window=3)

        # Set scoped state
        await ctx.set("system", "llm_model", "test-model")
        await ctx.set("colony", "task", "Build a web app")
        await ctx.set("colony", "round", 1)

        # Record episode
        ep = Episode(
            round_num=1,
            summary="Completed initial scaffolding",
            goal="Build project skeleton",
            agent_outputs={"coder_01": "Created main.py"},
        )
        await ctx.record_episode(ep)

        # Record TKG tuple
        tkg = TKGTuple(
            subject="coder_01",
            predicate="Modified_File",
            object_="main.py",
            round_num=1,
        )
        await ctx.record_tkg_tuple(tkg)

        # Record decision
        dec = Decision(
            round_num=1,
            decision_type=DecisionType.ROUTING,
            detail="Standard topology applied",
        )
        await ctx.record_decision(dec)

        # Serialize to disk
        save_path = tmp_path / "context.json"
        await ctx.save(save_path)

        # Restore from disk
        restored = await AsyncContextTree.load(save_path)

        # Verify scoped state
        assert restored.get("system", "llm_model") == "test-model"
        assert restored.get("colony", "task") == "Build a web app"
        assert restored.get("colony", "round") == 1

        # Verify episode
        episodes = restored.get_episodes()
        assert len(episodes) == 1
        assert episodes[0].summary == "Completed initial scaffolding"
        assert episodes[0].goal == "Build project skeleton"

        # Verify TKG
        tuples = restored.query_tkg(subject="coder_01")
        assert len(tuples) == 1
        assert tuples[0].predicate == "Modified_File"

        # Verify decision
        decisions = restored.get_decisions()
        assert len(decisions) == 1
        assert decisions[0].decision_type == DecisionType.ROUTING

    @pytest.mark.asyncio
    async def test_clear_colony_resets_state(self):
        ctx = AsyncContextTree()
        await ctx.set("colony", "task", "some task")
        ep = Episode(round_num=0, summary="s", goal="g")
        await ctx.record_episode(ep)

        await ctx.clear_colony()

        assert ctx.get("colony", "task") is None
        assert len(ctx.get_episodes()) == 0
        assert len(ctx.get_decisions()) == 0


# ═══════════════════════════════════════════════════════════════════════════
# 2. Governance Convergence Detection
# ═══════════════════════════════════════════════════════════════════════════


class TestGovernanceConvergence:
    """Verifies GovernanceEngine detects convergence and triggers force_halt."""

    def test_convergence_triggers_force_halt(self):
        config = _make_config(
            convergence=ConvergenceConfig(
                similarity_threshold=0.95,
                rounds_before_force_halt=2,
            ),
        )
        engine = GovernanceEngine(config)

        # Two identical vectors => similarity = 1.0 > 0.95
        vec = [1.0, 0.0, 0.0, 0.0]

        # Round 1: first high-similarity -> intervene (streak=1, below halt=2)
        d1 = engine.enforce(1, vec, vec)
        assert d1.action == "intervene"

        # Round 2: second consecutive -> force_halt (streak=2 >= halt=2)
        d2 = engine.enforce(2, vec, vec)
        assert d2.action == "force_halt"
        assert len(d2.recommendations) > 0

    def test_divergent_vectors_continue(self):
        config = _make_config()
        engine = GovernanceEngine(config)

        v1 = [1.0, 0.0, 0.0, 0.0]
        v2 = [0.0, 1.0, 0.0, 0.0]  # orthogonal => sim = 0.0

        d = engine.enforce(1, v1, v2)
        assert d.action == "continue"

    def test_missing_vectors_continue(self):
        config = _make_config()
        engine = GovernanceEngine(config)

        d = engine.enforce(1, None, None)
        assert d.action == "continue"


# ═══════════════════════════════════════════════════════════════════════════
# 3. Governance Path Diversity + Tunnel Vision
# ═══════════════════════════════════════════════════════════════════════════


class TestGovernancePathDiversity:
    """Verifies path_diversity_score and tunnel vision detection."""

    def test_diverse_approaches_score_correctly(self):
        config = _make_config()
        engine = GovernanceEngine(config)

        history = [
            {"agent_outputs": {"a1": {"approach": "brute force"}, "a2": {"approach": "divide and conquer"}}},
            {"agent_outputs": {"a1": {"approach": "greedy"}}},
        ]

        score = engine.path_diversity_score(history)
        assert score == 3  # brute force, divide and conquer, greedy

    def test_tunnel_vision_detected_after_consecutive_low_diversity(self):
        config = _make_config()
        engine = GovernanceEngine(config)

        # Same single approach repeated
        history = [
            {"agent_outputs": {"a1": {"approach": "brute force"}}},
        ]

        # First check: diversity=1, streak=1 -> no warning
        result1 = engine.check_tunnel_vision(history, round_num=3)
        assert result1 is None

        # Second check: diversity=1, streak=2 -> warning
        result2 = engine.check_tunnel_vision(history, round_num=4)
        assert result2 is not None
        assert result2.action == "warn_tunnel_vision"

    def test_empty_history_returns_zero(self):
        config = _make_config()
        engine = GovernanceEngine(config)

        assert engine.path_diversity_score([]) == 0


# ═══════════════════════════════════════════════════════════════════════════
# 4. SkillBank Store-Retrieve-Evolve
# ═══════════════════════════════════════════════════════════════════════════


class TestSkillBankLifecycle:
    """Verifies SkillBank CRUD + evolution pruning."""

    def test_store_and_retrieve_without_embedder(self, tmp_path: Path):
        """Without embedder, store works but retrieve returns empty."""
        sb_config = SkillBankConfig(
            storage_file=str(tmp_path / "skills.json"),
            retrieval_top_k=3,
            dedup_threshold=0.85,
            evolution_interval=2,
            prune_zero_hit_after=5,
        )
        bank = SkillBank(
            storage_path=tmp_path / "skills.json",
            config=sb_config,
            embedder=None,
        )

        skill = Skill(
            skill_id="gen_test01",
            content="Always write tests first",
            tier=SkillTier.GENERAL,
        )
        stored = bank.store([skill])
        assert stored == 1
        assert len(bank.skills) == 1

        # Retrieve returns empty without embedder
        results = bank.retrieve("testing strategy")
        assert results == []

    def test_store_and_retrieve_with_embedder(self, tmp_path: Path):
        """With embedder, store+retrieve works."""
        sb_config = SkillBankConfig(
            storage_file=str(tmp_path / "skills.json"),
            retrieval_top_k=2,
            dedup_threshold=0.85,
            evolution_interval=5,
            prune_zero_hit_after=10,
        )
        embedder = _make_mock_embedder(dim=8)
        bank = SkillBank(
            storage_path=tmp_path / "skills.json",
            config=sb_config,
            embedder=embedder,
        )

        skills = [
            Skill(skill_id="gen_01", content="Write tests before code", tier=SkillTier.GENERAL),
            Skill(skill_id="ts_01", content="Use SQLAlchemy for DB access", tier=SkillTier.TASK_SPECIFIC, category="database"),
            Skill(skill_id="les_01", content="Never hardcode secrets", tier=SkillTier.LESSON),
        ]
        stored = bank.store(skills)
        assert stored == 3

        results = bank.retrieve("testing strategy", top_k=2)
        assert len(results) <= 2
        # retrieval_count incremented
        for r in results:
            assert r.retrieval_count >= 1

    def test_evolution_prunes_zero_hit_skills(self, tmp_path: Path):
        sb_config = SkillBankConfig(
            storage_file=str(tmp_path / "skills.json"),
            retrieval_top_k=3,
            dedup_threshold=0.85,
            evolution_interval=1,  # evolve after every colony
            prune_zero_hit_after=10,
        )
        bank = SkillBank(
            storage_path=tmp_path / "skills.json",
            config=sb_config,
            embedder=None,
        )

        # Store a skill with retrieval_count=0 (will be pruned)
        zero_hit = Skill(skill_id="gen_zero", content="Unused skill", tier=SkillTier.GENERAL)
        bank.store([zero_hit])

        # Store a skill with retrieval_count>0 (will survive)
        used = Skill(skill_id="gen_used", content="Used skill", tier=SkillTier.GENERAL, retrieval_count=5)
        bank.store([used])

        assert len(bank.skills) == 2

        report = bank.evolve()
        assert report.evolved is True
        assert report.pruned == 1  # zero_hit pruned
        assert len(bank.skills) == 1
        assert bank.skills[0].skill_id == "gen_used"

    def test_format_for_injection(self, tmp_path: Path):
        sb_config = SkillBankConfig(storage_file=str(tmp_path / "skills.json"))
        bank = SkillBank(
            storage_path=tmp_path / "skills.json",
            config=sb_config,
            embedder=None,
        )

        skills = [
            Skill(skill_id="gen_01", content="Test first", tier=SkillTier.GENERAL, retrieval_count=3, success_correlation=0.8),
        ]

        formatted = bank.format_for_injection(skills)
        assert "[STRATEGIC GUIDANCE]" in formatted
        assert "Test first" in formatted
        assert "80% success" in formatted


# ═══════════════════════════════════════════════════════════════════════════
# 5. Router Topology from Pre-Computed Matrix
# ═══════════════════════════════════════════════════════════════════════════


class TestRouterTopology:
    """Verifies build_topology_from_matrix produces valid DAG topologies."""

    def test_three_agent_topology(self):
        agent_ids = ["architect_01", "coder_01", "reviewer_01"]

        # Pre-computed similarity: architect->coder strong, coder->reviewer strong
        S = np.array([
            [0.0, 0.8, 0.2],
            [0.8, 0.0, 0.7],
            [0.2, 0.7, 0.0],
        ], dtype=np.float32)

        topo = build_topology_from_matrix(agent_ids, S, tau=0.3, k_in=2)

        assert isinstance(topo, Topology)
        assert len(topo.execution_order) == 3
        # All agents appear exactly once in execution order
        assert set(topo.execution_order) == set(agent_ids)
        assert 0.0 <= topo.density <= 1.0

    def test_single_agent_topology(self):
        topo = build_topology_from_matrix(["solo_agent"], np.zeros((1, 1)), tau=0.35)
        assert topo.execution_order == ["solo_agent"]
        assert len(topo.edges) == 0

    def test_empty_agent_topology(self):
        topo = build_topology_from_matrix([], np.zeros((0, 0)), tau=0.35)
        assert topo.execution_order == []
        assert len(topo.edges) == 0

    def test_high_threshold_isolates_agents(self):
        agent_ids = ["a", "b", "c"]
        S = np.array([
            [0.0, 0.3, 0.2],
            [0.3, 0.0, 0.3],
            [0.2, 0.3, 0.0],
        ], dtype=np.float32)

        # tau=0.9 means no edges survive
        topo = build_topology_from_matrix(agent_ids, S, tau=0.9, k_in=2)
        assert len(topo.edges) == 0
        assert len(topo.execution_order) == 3


# ═══════════════════════════════════════════════════════════════════════════
# 6. Archivist Summarization + TKG Extraction
# ═══════════════════════════════════════════════════════════════════════════


class TestArchivistPipeline:
    """Verifies Archivist summarize_round and extract_tkg_tuples with mocked LLM."""

    @pytest.mark.asyncio
    async def test_summarize_round_returns_episode(self):
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Agents built initial project structure."
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        config = _make_config()
        archivist = Archivist(
            model_client=mock_client,
            model_name="test-model",
            config=config,
        )

        episode = await archivist.summarize_round(
            round_num=1,
            goal="Build project skeleton",
            agent_outputs={
                "coder_01": "Created main.py with FastAPI app",
                "reviewer_01": "LGTM, structure looks good",
            },
        )

        assert isinstance(episode, Episode)
        assert episode.round_num == 1
        assert episode.goal == "Build project skeleton"
        assert "initial project structure" in episode.summary

    @pytest.mark.asyncio
    async def test_extract_tkg_tuples(self):
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps([
            {"subject": "coder_01", "predicate": "Modified_File", "object": "main.py"},
            {"subject": "reviewer_01", "predicate": "Approved", "object": "main.py"},
        ])
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        config = _make_config()
        archivist = Archivist(
            model_client=mock_client,
            model_name="test-model",
            config=config,
        )

        tuples = await archivist.extract_tkg_tuples(
            round_num=1,
            agent_outputs={"coder_01": "Modified main.py", "reviewer_01": "Approved main.py"},
        )

        assert len(tuples) == 2
        assert tuples[0].subject == "coder_01"
        assert tuples[0].predicate == "Modified_File"
        assert tuples[1].subject == "reviewer_01"

    @pytest.mark.asyncio
    async def test_summarize_round_handles_llm_failure(self):
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(
            side_effect=RuntimeError("LLM unavailable")
        )

        config = _make_config()
        archivist = Archivist(
            model_client=mock_client,
            model_name="test-model",
            config=config,
        )

        episode = await archivist.summarize_round(
            round_num=1,
            goal="Test goal",
            agent_outputs={"coder_01": "output"},
        )

        # Should return fallback episode, not crash
        assert isinstance(episode, Episode)
        assert "failed" in episode.summary.lower() or "Summarization failed" in episode.summary

    @pytest.mark.asyncio
    async def test_compress_epoch(self):
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Epoch summary: project built and tested."
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        config = _make_config()
        archivist = Archivist(
            model_client=mock_client,
            model_name="test-model",
            config=config,
        )

        episodes = [
            Episode(round_num=i, summary=f"Round {i} summary", goal=f"Goal {i}")
            for i in range(5)
        ]

        epoch = await archivist.compress_epoch(episodes, epoch_id=1)

        assert isinstance(epoch, EpochSummary)
        assert epoch.epoch_id == 1
        assert epoch.round_range == (0, 4)
        assert "Epoch summary" in epoch.summary


# ═══════════════════════════════════════════════════════════════════════════
# 7. Session Manager Save/Restore Lifecycle
# ═══════════════════════════════════════════════════════════════════════════


class TestSessionManagerLifecycle:
    """Verifies session start, autosave, end, list, and delete operations."""

    @pytest.mark.asyncio
    async def test_start_and_end_session(self, tmp_path: Path):
        sm = SessionManager(
            session_dir=tmp_path,
            config=PersistenceConfig(session_dir=str(tmp_path)),
            autosave_interval=9999.0,  # disable periodic autosave
        )
        ctx = AsyncContextTree()
        await ctx.set("colony", "task", "Test task")

        await sm.start_session("sess-001", ctx, task="Test task")

        # Verify files created
        session_dir = tmp_path / "sess-001"
        assert session_dir.exists()
        assert (session_dir / "meta.json").exists()
        assert (session_dir / "context.json").exists()
        assert (session_dir / "session.lock").exists()

        # End session
        info = await sm.end_session("sess-001", ctx, status="completed")
        assert info.session_id == "sess-001"
        assert info.status == "completed"
        # Lock file removed after end
        assert not (session_dir / "session.lock").exists()

    @pytest.mark.asyncio
    async def test_list_sessions(self, tmp_path: Path):
        sm = SessionManager(session_dir=tmp_path, autosave_interval=9999.0)
        ctx = AsyncContextTree()

        await sm.start_session("s1", ctx, task="Task 1")
        await sm.end_session("s1", ctx, status="completed")

        sessions = await sm.list_sessions()
        assert len(sessions) == 1
        assert sessions[0].session_id == "s1"

    @pytest.mark.asyncio
    async def test_delete_session(self, tmp_path: Path):
        sm = SessionManager(session_dir=tmp_path, autosave_interval=9999.0)
        ctx = AsyncContextTree()

        await sm.start_session("to-delete", ctx, task="Delete me")
        await sm.end_session("to-delete", ctx)

        await sm.delete_session("to-delete")
        assert not (tmp_path / "to-delete").exists()

    @pytest.mark.asyncio
    async def test_delete_nonexistent_raises(self, tmp_path: Path):
        sm = SessionManager(session_dir=tmp_path)
        with pytest.raises(FileNotFoundError):
            await sm.delete_session("nonexistent")


# ═══════════════════════════════════════════════════════════════════════════
# 8. Agent Context Assembly with Full State
# ═══════════════════════════════════════════════════════════════════════════


class TestContextAssembly:
    """Verifies assemble_agent_context correctly builds prioritized context."""

    @pytest.mark.asyncio
    async def test_full_context_assembly(self):
        ctx = AsyncContextTree(episode_window=2)

        # System info
        await ctx.set("system", "llm_model", "Qwen3-30B")
        await ctx.set("system", "llm_endpoint", "http://llm:8080/v1")

        # Project info
        await ctx.set("project", "file_index", "src/main.py, src/utils.py")

        # Colony state
        await ctx.set("colony", "task", "Build REST API")
        await ctx.set("colony", "round", 3)
        await ctx.set("colony", "agents", ["coder_01", "reviewer_01"])
        await ctx.set("colony", "status", "running")

        # Skills
        await ctx.set("colony", "skill_context", "Always write tests before code.")

        # Feedback
        await ctx.set("colony", "agent_feedback", {
            "coder_01": "Good work on auth module, now focus on error handling.",
        })

        # Episodes
        ep1 = Episode(round_num=1, summary="Initial setup done", goal="Setup")
        ep2 = Episode(round_num=2, summary="Auth module complete", goal="Auth")
        await ctx.record_episode(ep1)
        await ctx.record_episode(ep2)

        # Assemble for coder_01
        context = ctx.assemble_agent_context("coder_01", "coder")

        assert "Qwen3-30B" in context
        assert "Build REST API" in context
        assert "Auth module complete" in context
        assert "Always write tests" in context
        assert "focus on error handling" in context

    @pytest.mark.asyncio
    async def test_context_assembly_with_team(self):
        ctx = AsyncContextTree()

        await ctx.set("colony", "task", "Build app")
        await ctx.set("colony", "teams", {
            "team-alpha": {"objective": "Build backend", "members": ["c1", "c2"]},
        })

        context = ctx.assemble_agent_context("c1", "coder", team_id="team-alpha")
        assert "team-alpha" in context

    @pytest.mark.asyncio
    async def test_context_assembly_with_token_budget(self):
        ctx = AsyncContextTree()
        await ctx.set("system", "llm_model", "TestModel")
        await ctx.set("colony", "task", "A" * 10000)

        # Very small budget: 50 tokens ~ 200 chars
        context = ctx.assemble_agent_context("a1", "coder", token_budget=50)
        assert len(context) <= 200


# ═══════════════════════════════════════════════════════════════════════════
# 9. Approval Gate Request/Respond Flow
# ═══════════════════════════════════════════════════════════════════════════


class TestApprovalGateFlow:
    """Verifies ApprovalGate auto-approve, blocking, responding, and timeout."""

    @pytest.mark.asyncio
    async def test_auto_approve_non_required_action(self):
        gate = ApprovalGate(required_actions=["file_delete"], timeout=5.0)

        # "file_read" not in required_actions -> auto-approve
        approved = await gate.request_approval(
            action="file_read",
            detail="Reading config file",
            agent_id="coder_01",
        )
        assert approved is True

    @pytest.mark.asyncio
    async def test_required_action_blocks_then_responds(self):
        gate = ApprovalGate(required_actions=["file_delete"], timeout=5.0)

        handler_called = []

        async def mock_handler(pending: PendingApproval):
            handler_called.append(pending.request_id)
            # Simulate UI responding after a short delay
            await asyncio.sleep(0.05)
            gate.respond(pending.request_id, approved=True)

        gate.set_handler(mock_handler)

        approved = await gate.request_approval(
            action="file_delete",
            detail="Deleting temp files",
            agent_id="coder_01",
        )
        assert approved is True
        assert len(handler_called) == 1
        assert len(gate.get_history()) == 1

    @pytest.mark.asyncio
    async def test_timeout_auto_denies(self):
        gate = ApprovalGate(required_actions=["dangerous_op"], timeout=0.1)

        # No handler responds -> timeout after 0.1s -> auto-deny
        approved = await gate.request_approval(
            action="dangerous_op",
            detail="Something risky",
            agent_id="coder_01",
        )
        assert approved is False

        history = gate.get_history()
        assert len(history) == 1
        assert history[0].approved is False

    @pytest.mark.asyncio
    async def test_pending_list(self):
        gate = ApprovalGate(required_actions=["op"], timeout=10.0)

        # Start request in background (it will block)
        task = asyncio.create_task(
            gate.request_approval(action="op", detail="test", agent_id="a1")
        )

        # Give the event loop time to register the pending request
        await asyncio.sleep(0.05)

        pending = gate.get_pending()
        assert len(pending) == 1
        assert pending[0].tool == "op"

        # Resolve to unblock
        gate.respond(pending[0].request_id, approved=False)
        result = await task
        assert result is False


# ═══════════════════════════════════════════════════════════════════════════
# 10. Audit Logger Session Event Capture
# ═══════════════════════════════════════════════════════════════════════════


class TestAuditLoggerCapture:
    """Verifies AuditLogger writes structured JSONL events per session."""

    @pytest.mark.asyncio
    async def test_log_and_flush(self, tmp_path: Path):
        audit = AuditLogger(session_dir=tmp_path)

        audit.log_session_start("sess-001", task="Test task", config={"model": "test"})
        audit.log_round("sess-001", round_num=1, phase="routing", data={"agents": 3})
        audit.log_decision("sess-001", decision_type="routing", detail="Standard route")
        audit.log_agent_action("sess-001", agent_id="coder_01", action="code", detail="Wrote main.py")
        audit.log_error("sess-001", error_type="timeout", message="Agent timed out")
        audit.log_session_end("sess-001", status="completed", outcome="Success")

        await audit.flush()

        log_path = tmp_path / "sess-001" / "audit.jsonl"
        assert log_path.exists()

        lines = log_path.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 6

        # Verify each line is valid JSON
        events = [json.loads(line) for line in lines]
        event_types = [e["event_type"] for e in events]
        assert event_types == [
            "session_start", "round", "decision",
            "agent_action", "error", "session_end",
        ]

        # Verify structure
        assert events[0]["payload"]["task"] == "Test task"
        assert events[1]["payload"]["round_num"] == 1
        assert events[5]["payload"]["status"] == "completed"

    @pytest.mark.asyncio
    async def test_close_flushes_remaining(self, tmp_path: Path):
        audit = AuditLogger(session_dir=tmp_path)

        audit.log_round("sess-002", round_num=1, phase="execution", data={})
        audit.log_round("sess-002", round_num=2, phase="execution", data={})

        # close() should flush
        await audit.close()

        log_path = tmp_path / "sess-002" / "audit.jsonl"
        assert log_path.exists()
        lines = log_path.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 2

    @pytest.mark.asyncio
    async def test_closed_logger_drops_events(self, tmp_path: Path):
        audit = AuditLogger(session_dir=tmp_path)
        await audit.close()

        # After close, events are silently dropped
        audit.log_round("sess-003", round_num=1, phase="x", data={})
        await audit.flush()

        log_path = tmp_path / "sess-003" / "audit.jsonl"
        assert not log_path.exists()
