"""
Tests for FormicOS v0.6.0 Pydantic models.

Covers:
- Construction of every model with valid data
- Validation rejection of bad input (wrong enum, missing required field, negative values)
- Serialization round-trip (model_dump -> model_validate)
- load_config() with a minimal valid YAML
- load_config() rejection of YAML with missing required fields
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest
import yaml

from src.models import (
    # Enums
    AgentStatus,
    Caste,
    ColonyStatus,
    DecisionType,
    ModelBackendType,
    SkillTier,
    SubcasteTier,
    # Models
    AgentConfig,
    AgentState,
    CasteConfig,
    CloudBurstConfig,
    ColonyConfig,
    ConvergenceConfig,
    Decision,
    EmbeddingConfig,
    Episode,
    EpochSummary,
    FeedbackRecord,
    FormicOSConfig,
    HardwareConfig,
    IdentityConfig,
    InferenceConfig,
    MCPGatewayConfig,
    ModelRegistryEntry,
    PersistenceConfig,
    QdrantCollectionConfig,
    QdrantConfig,
    RoundRecord,
    RoutingConfig,
    SessionResult,
    Skill,
    SkillBankConfig,
    SubcasteMapEntry,
    SummarizationConfig,
    TeamConfig,
    TeamsConfig,
    TemporalConfig,
    TKGTuple,
    ToolsScope,
    Topology,
    TopologyEdge,
    load_config,
)


# ═══════════════════════════════════════════════════════════════════════════
# Enum Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestEnums:
    """Verify that all enum members resolve correctly."""

    def test_caste_members(self) -> None:
        assert Caste.MANAGER == "manager"
        assert Caste.ARCHITECT == "architect"
        assert Caste.CODER == "coder"
        assert Caste.REVIEWER == "reviewer"
        assert Caste.RESEARCHER == "researcher"
        assert len(Caste) == 6  # includes DYTOPO (v0.6.2)

    def test_agent_status_members(self) -> None:
        assert AgentStatus.IDLE == "idle"
        assert AgentStatus.THINKING == "thinking"
        assert AgentStatus.EXECUTING == "executing"
        assert AgentStatus.WAITING == "waiting"
        assert AgentStatus.ERROR == "error"
        assert len(AgentStatus) == 5

    def test_decision_type_members(self) -> None:
        assert DecisionType.ROUTING == "routing"
        assert DecisionType.TERMINATION == "termination"
        assert DecisionType.ESCALATION == "escalation"
        assert DecisionType.INTERVENTION == "intervention"
        assert DecisionType.STALL == "stall"
        assert DecisionType.MANAGER_GOAL == "manager_goal"
        assert len(DecisionType) == 6

    def test_colony_status_members(self) -> None:
        assert ColonyStatus.CREATED == "created"
        assert ColonyStatus.READY == "ready"
        assert ColonyStatus.RUNNING == "running"
        assert ColonyStatus.PAUSED == "paused"
        assert ColonyStatus.COMPLETED == "completed"
        assert ColonyStatus.FAILED == "failed"
        assert ColonyStatus.HALTED_BUDGET_EXHAUSTED == "halted_budget_exhausted"
        assert ColonyStatus.QUEUED_PENDING_COMPUTE == "queued_pending_compute"
        assert len(ColonyStatus) == 8

    def test_model_backend_type_members(self) -> None:
        assert ModelBackendType.LLAMA_CPP == "llama_cpp"
        assert ModelBackendType.OPENAI_COMPATIBLE == "openai_compatible"
        assert ModelBackendType.OLLAMA == "ollama"
        assert ModelBackendType.ANTHROPIC_API == "anthropic_api"
        assert len(ModelBackendType) == 4

    def test_subcaste_tier_members(self) -> None:
        assert SubcasteTier.HEAVY == "heavy"
        assert SubcasteTier.BALANCED == "balanced"
        assert SubcasteTier.LIGHT == "light"
        assert len(SubcasteTier) == 3

    def test_skill_tier_members(self) -> None:
        assert SkillTier.GENERAL == "general"
        assert SkillTier.TASK_SPECIFIC == "task_specific"
        assert SkillTier.LESSON == "lesson"
        assert len(SkillTier) == 3


# ═══════════════════════════════════════════════════════════════════════════
# Model Construction Tests -- valid data
# ═══════════════════════════════════════════════════════════════════════════


class TestValidConstruction:
    """Every model should construct successfully with valid data."""

    def test_agent_state(self) -> None:
        s = AgentState(agent_id="coder_01", caste=Caste.CODER)
        assert s.agent_id == "coder_01"
        assert s.caste == Caste.CODER
        assert s.status == AgentStatus.IDLE
        assert s.model_id is None
        assert s.subcaste_tier is None
        assert s.team_id is None
        assert s.schema_version == "0.6.0"

    def test_agent_state_full(self) -> None:
        s = AgentState(
            agent_id="arch_01",
            caste=Caste.ARCHITECT,
            status=AgentStatus.THINKING,
            model_id="local/qwen3-30b",
            subcaste_tier=SubcasteTier.HEAVY,
            team_id="team_alpha",
        )
        assert s.status == AgentStatus.THINKING
        assert s.model_id == "local/qwen3-30b"
        assert s.subcaste_tier == SubcasteTier.HEAVY
        assert s.team_id == "team_alpha"

    def test_agent_config(self) -> None:
        c = AgentConfig(
            agent_id="coder_01",
            caste=Caste.CODER,
            tools=["file_read", "file_write"],
        )
        assert c.agent_id == "coder_01"
        assert c.caste == Caste.CODER
        assert c.tools == ["file_read", "file_write"]
        assert c.model_override is None
        assert c.subcaste_tier is None

    def test_caste_config(self) -> None:
        cc = CasteConfig(
            system_prompt_file="coder.md",
            tools=["file_read", "code_execute"],
            model_override=None,
        )
        assert cc.system_prompt_file == "coder.md"
        assert len(cc.tools) == 2

    def test_topology_edge(self) -> None:
        e = TopologyEdge(sender="coder_01", receiver="reviewer_01", weight=0.85)
        assert e.sender == "coder_01"
        assert e.receiver == "reviewer_01"
        assert e.weight == 0.85

    def test_topology(self) -> None:
        edge = TopologyEdge(sender="a", receiver="b", weight=0.5)
        t = Topology(
            edges=[edge],
            execution_order=["a", "b"],
            density=0.5,
            isolated_agents=["c"],
        )
        assert len(t.edges) == 1
        assert t.density == 0.5
        assert t.isolated_agents == ["c"]

    def test_episode(self) -> None:
        ep = Episode(
            round_num=3,
            summary="Completed authentication module.",
            goal="Implement auth",
            agent_outputs={"coder_01": "Wrote login handler"},
        )
        assert ep.round_num == 3
        assert "coder_01" in ep.agent_outputs
        assert ep.timestamp > 0

    def test_epoch_summary(self) -> None:
        es = EpochSummary(
            epoch_id=1,
            summary="Rounds 1-5 established project scaffolding.",
            round_range=(1, 5),
        )
        assert es.epoch_id == 1
        assert es.round_range == (1, 5)

    def test_tkg_tuple(self) -> None:
        t = TKGTuple(
            subject="Coder_01",
            predicate="wrote",
            object_="auth_handler.py",
            round_num=2,
        )
        assert t.subject == "Coder_01"
        assert t.object_ == "auth_handler.py"
        assert t.team_id is None

    def test_tkg_tuple_with_team(self) -> None:
        t = TKGTuple(
            subject="Coder_01",
            predicate="wrote",
            object_="auth_handler.py",
            round_num=2,
            team_id="team_alpha",
        )
        assert t.team_id == "team_alpha"

    def test_decision(self) -> None:
        d = Decision(
            round_num=5,
            decision_type=DecisionType.ROUTING,
            detail="Routed coder output to reviewer.",
            recommendations=["Consider adding unit tests"],
        )
        assert d.round_num == 5
        assert d.decision_type == DecisionType.ROUTING
        assert len(d.recommendations) == 1

    def test_round_record(self) -> None:
        rr = RoundRecord(
            round_num=1,
            goal="Set up project structure",
            agent_outputs={"arch_01": "Created scaffolding"},
        )
        assert rr.round_num == 1
        assert rr.topology is None
        assert rr.episode is None
        assert rr.decisions == []

    def test_round_record_full(self) -> None:
        topo = Topology(density=0.3)
        ep = Episode(round_num=1, summary="s", goal="g")
        dec = Decision(
            round_num=1,
            decision_type=DecisionType.MANAGER_GOAL,
            detail="Set initial goal",
        )
        rr = RoundRecord(
            round_num=1,
            goal="Build it",
            agent_outputs={"a": "done"},
            topology=topo,
            episode=ep,
            decisions=[dec],
        )
        assert rr.topology is not None
        assert rr.episode is not None
        assert len(rr.decisions) == 1

    def test_session_result(self) -> None:
        sr = SessionResult(
            session_id="sess_001",
            task="Build a REST API",
            status=ColonyStatus.COMPLETED,
            rounds_completed=7,
            final_answer="API deployed.",
            skill_ids=["gen_001", "ts_api_002"],
        )
        assert sr.session_id == "sess_001"
        assert sr.status == ColonyStatus.COMPLETED
        assert sr.rounds_completed == 7
        assert len(sr.skill_ids) == 2

    def test_tools_scope(self) -> None:
        ts = ToolsScope(builtin=["file_read"], mcp=["fetch*"])
        assert ts.builtin == ["file_read"]
        assert ts.mcp == ["fetch*"]

    def test_tools_scope_empty(self) -> None:
        ts = ToolsScope()
        assert ts.builtin == []
        assert ts.mcp == []

    def test_team_config(self) -> None:
        tc = TeamConfig(
            team_id="backend",
            name="Backend Team",
            objective="Build API endpoints",
            members=["coder_01", "reviewer_01"],
            max_members=4,
        )
        assert tc.team_id == "backend"
        assert tc.name == "Backend Team"
        assert len(tc.members) == 2
        assert tc.max_members == 4

    def test_colony_config_minimal(self) -> None:
        cc = ColonyConfig(colony_id="test_colony", task="Write tests")
        assert cc.colony_id == "test_colony"
        assert cc.max_rounds == 10
        assert cc.routing_tau == 0.35
        assert cc.routing_k_in == 3
        assert cc.teams is None
        assert cc.manager is None
        assert cc.tools_scope is None
        assert cc.skill_scope is None
        assert cc.max_agents == 10

    def test_colony_config_full(self) -> None:
        agent = AgentConfig(
            agent_id="coder_01", caste=Caste.CODER, tools=["file_write"]
        )
        manager = AgentConfig(
            agent_id="mgr_01", caste=Caste.MANAGER, tools=[]
        )
        team = TeamConfig(
            team_id="t1",
            name="Team One",
            objective="Do stuff",
            members=["coder_01"],
        )
        ts = ToolsScope(builtin=["file_read"], mcp=["fetch*"])
        cc = ColonyConfig(
            colony_id="full_colony",
            task="Build everything",
            agents=[agent],
            max_rounds=20,
            routing_tau=0.5,
            routing_k_in=5,
            teams=[team],
            manager=manager,
            tools_scope=ts,
            skill_scope=["general", "api"],
            max_agents=15,
        )
        assert len(cc.agents) == 1
        assert cc.manager is not None
        assert cc.manager.caste == Caste.MANAGER
        assert len(cc.teams) == 1
        assert cc.tools_scope.builtin == ["file_read"]

    def test_model_registry_entry(self) -> None:
        mre = ModelRegistryEntry(
            model_id="local/qwen3-30b",
            type="autoregressive",
            backend=ModelBackendType.LLAMA_CPP,
            endpoint="http://llm:8080/v1",
            context_length=32768,
            vram_gb=25.6,
        )
        assert mre.model_id == "local/qwen3-30b"
        assert mre.backend == ModelBackendType.LLAMA_CPP
        assert mre.supports_tools is True
        assert mre.requires_approval is False

    def test_skill(self) -> None:
        sk = Skill(
            skill_id="gen_001",
            content="Always validate input before processing.",
            tier=SkillTier.GENERAL,
            created_at=time.time(),
        )
        assert sk.skill_id == "gen_001"
        assert sk.tier == SkillTier.GENERAL
        assert sk.retrieval_count == 0
        assert sk.superseded_by is None
        assert sk.embedding is None

    def test_skill_with_embedding(self) -> None:
        embedding = [0.1] * 384
        sk = Skill(
            skill_id="ts_001",
            content="Use parameterized queries.",
            tier=SkillTier.TASK_SPECIFIC,
            category="database",
            embedding=embedding,
            source_colony="db_colony",
            created_at=time.time(),
        )
        assert sk.category == "database"
        assert len(sk.embedding) == 384
        assert sk.source_colony == "db_colony"

    def test_feedback_record(self) -> None:
        fr = FeedbackRecord(
            agent_id="coder_01",
            round_num=3,
            feedback_text="Good progress on authentication.",
        )
        assert fr.agent_id == "coder_01"
        assert fr.round_num == 3
        assert fr.timestamp > 0

    def test_subcaste_map_entry(self) -> None:
        sme = SubcasteMapEntry(primary="local/qwen3-30b")
        assert sme.primary == "local/qwen3-30b"
        assert sme.refine_with is None
        assert sme.refine_prompt is None

    def test_subcaste_map_entry_with_refine(self) -> None:
        sme = SubcasteMapEntry(
            primary="local/qwen3-30b",
            refine_with="cloud/claude",
            refine_prompt="Review for accuracy.",
        )
        assert sme.refine_with == "cloud/claude"
        assert sme.refine_prompt == "Review for accuracy."


# ═══════════════════════════════════════════════════════════════════════════
# Sub-config Construction Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestSubConfigs:
    """Verify all FormicOSConfig sub-models construct correctly."""

    def test_identity_config(self) -> None:
        ic = IdentityConfig(name="FormicOS", version="0.6.0")
        assert ic.name == "FormicOS"

    def test_identity_config_defaults(self) -> None:
        ic = IdentityConfig()
        assert ic.name == "FormicOS"
        assert ic.version == "0.6.0"

    def test_hardware_config(self) -> None:
        hc = HardwareConfig(gpu="rtx5090", vram_gb=32.0)
        assert hc.gpu == "rtx5090"
        assert hc.vram_alert_threshold_gb == 28.0

    def test_inference_config(self) -> None:
        ic = InferenceConfig()
        assert ic.endpoint == "http://llm:8080/v1"
        assert ic.temperature == 0.0
        assert ic.intent_model is None

    def test_embedding_config(self) -> None:
        ec = EmbeddingConfig()
        assert ec.model == "BAAI/bge-m3"
        assert ec.dimensions == 1024
        assert ec.routing_model == "all-MiniLM-L6-v2"

    def test_routing_config(self) -> None:
        rc = RoutingConfig()
        assert rc.tau == 0.35
        assert rc.k_in == 3
        assert rc.broadcast_fallback is True

    def test_convergence_config(self) -> None:
        cc = ConvergenceConfig()
        assert cc.similarity_threshold == 0.95
        assert cc.path_diversity_warning_after == 3

    def test_summarization_config(self) -> None:
        sc = SummarizationConfig()
        assert sc.epoch_window == 5
        assert sc.tree_sitter_languages == ["python"]

    def test_temporal_config(self) -> None:
        tc = TemporalConfig()
        assert tc.episodic_ttl_hours == 72
        assert tc.tkg_max_tuples == 5000

    def test_cloud_burst_config(self) -> None:
        cb = CloudBurstConfig()
        assert cb.enabled is False
        assert cb.provider == "anthropic"

    def test_persistence_config(self) -> None:
        pc = PersistenceConfig()
        assert pc.session_dir == ".formicos/sessions"
        assert pc.autosave_interval_seconds == 30

    def test_qdrant_collection_config(self) -> None:
        qcc = QdrantCollectionConfig(embedding="bge-m3", dimensions=1024)
        assert qcc.embedding == "bge-m3"
        assert qcc.dimensions == 1024

    def test_qdrant_config(self) -> None:
        qc = QdrantConfig(
            host="qdrant",
            port=6333,
            collections={
                "project_docs": QdrantCollectionConfig(
                    embedding="bge-m3", dimensions=1024
                )
            },
        )
        assert qc.host == "qdrant"
        assert "project_docs" in qc.collections

    def test_mcp_gateway_config(self) -> None:
        mgc = MCPGatewayConfig()
        assert mgc.enabled is True
        assert mgc.transport == "stdio"
        assert mgc.command == "docker"
        assert mgc.args == ["mcp", "gateway", "run"]

    def test_skill_bank_config(self) -> None:
        sbc = SkillBankConfig()
        assert sbc.retrieval_top_k == 3
        assert sbc.dedup_threshold == 0.85

    def test_teams_config(self) -> None:
        tc = TeamsConfig()
        assert tc.max_teams_per_colony == 4
        assert tc.allow_dynamic_spawn is True


# ═══════════════════════════════════════════════════════════════════════════
# Validation Rejection Tests -- bad input
# ═══════════════════════════════════════════════════════════════════════════


class TestValidationRejection:
    """Verify that models reject invalid data."""

    def test_agent_state_bad_caste(self) -> None:
        # v0.6.2: caste is now a free-form string, so any non-empty string is valid.
        # Verify it normalizes to lowercase instead of rejecting.
        state = AgentState(agent_id="x", caste="custom_caste")
        assert state.caste == "custom_caste"

    def test_agent_state_empty_id(self) -> None:
        with pytest.raises(Exception):
            AgentState(agent_id="", caste=Caste.CODER)

    def test_agent_state_blank_id(self) -> None:
        with pytest.raises(Exception):
            AgentState(agent_id="   ", caste=Caste.CODER)

    def test_agent_config_empty_id(self) -> None:
        with pytest.raises(Exception):
            AgentConfig(agent_id="", caste=Caste.CODER, tools=[])

    def test_agent_config_missing_caste(self) -> None:
        with pytest.raises(Exception):
            AgentConfig(agent_id="coder_01", tools=[])  # type: ignore[call-arg]

    def test_topology_edge_negative_weight(self) -> None:
        with pytest.raises(Exception):
            TopologyEdge(sender="a", receiver="b", weight=-0.5)

    def test_topology_density_out_of_range(self) -> None:
        with pytest.raises(Exception):
            Topology(density=1.5)

    def test_topology_density_negative(self) -> None:
        with pytest.raises(Exception):
            Topology(density=-0.1)

    def test_episode_negative_round(self) -> None:
        with pytest.raises(Exception):
            Episode(round_num=-1, summary="s", goal="g")

    def test_epoch_summary_inverted_range(self) -> None:
        with pytest.raises(Exception):
            EpochSummary(
                epoch_id=1, summary="s", round_range=(5, 1)
            )

    def test_epoch_summary_negative_start(self) -> None:
        with pytest.raises(Exception):
            EpochSummary(
                epoch_id=1, summary="s", round_range=(-1, 5)
            )

    def test_decision_negative_round(self) -> None:
        with pytest.raises(Exception):
            Decision(
                round_num=-1,
                decision_type=DecisionType.ROUTING,
                detail="bad",
            )

    def test_decision_bad_type(self) -> None:
        with pytest.raises(Exception):
            Decision(
                round_num=1,
                decision_type="nonexistent_type",  # type: ignore[arg-type]
                detail="bad",
            )

    def test_round_record_negative_round(self) -> None:
        with pytest.raises(Exception):
            RoundRecord(round_num=-1, goal="g")

    def test_session_result_negative_rounds_completed(self) -> None:
        with pytest.raises(Exception):
            SessionResult(
                session_id="s",
                task="t",
                status=ColonyStatus.COMPLETED,
                rounds_completed=-1,
            )

    def test_session_result_bad_status(self) -> None:
        with pytest.raises(Exception):
            SessionResult(
                session_id="s",
                task="t",
                status="bogus",  # type: ignore[arg-type]
                rounds_completed=0,
            )

    def test_colony_config_empty_id(self) -> None:
        with pytest.raises(Exception):
            ColonyConfig(colony_id="", task="t")

    def test_colony_config_max_rounds_zero(self) -> None:
        with pytest.raises(Exception):
            ColonyConfig(colony_id="c", task="t", max_rounds=0)

    def test_colony_config_max_rounds_too_high(self) -> None:
        with pytest.raises(Exception):
            ColonyConfig(colony_id="c", task="t", max_rounds=101)

    def test_colony_config_routing_tau_out_of_range(self) -> None:
        with pytest.raises(Exception):
            ColonyConfig(colony_id="c", task="t", routing_tau=2.0)

    def test_model_registry_entry_bad_backend(self) -> None:
        with pytest.raises(Exception):
            ModelRegistryEntry(backend="invalid_backend")  # type: ignore[arg-type]

    def test_model_registry_entry_zero_context_length(self) -> None:
        with pytest.raises(Exception):
            ModelRegistryEntry(
                backend=ModelBackendType.LLAMA_CPP, context_length=0
            )

    def test_skill_negative_retrieval_count(self) -> None:
        with pytest.raises(Exception):
            Skill(
                skill_id="s",
                content="c",
                tier=SkillTier.GENERAL,
                retrieval_count=-1,
                created_at=time.time(),
            )

    def test_skill_correlation_too_high(self) -> None:
        with pytest.raises(Exception):
            Skill(
                skill_id="s",
                content="c",
                tier=SkillTier.GENERAL,
                success_correlation=1.5,
                created_at=time.time(),
            )

    def test_feedback_record_negative_round(self) -> None:
        with pytest.raises(Exception):
            FeedbackRecord(
                agent_id="a", round_num=-1, feedback_text="bad"
            )

    def test_team_config_empty_id(self) -> None:
        with pytest.raises(Exception):
            TeamConfig(team_id="", name="n", objective="o")

    def test_team_config_max_members_zero(self) -> None:
        with pytest.raises(Exception):
            TeamConfig(
                team_id="t", name="n", objective="o", max_members=0
            )

    def test_tkg_tuple_negative_round(self) -> None:
        with pytest.raises(Exception):
            TKGTuple(
                subject="s", predicate="p", object_="o", round_num=-1
            )

    def test_inference_config_negative_temperature(self) -> None:
        with pytest.raises(Exception):
            InferenceConfig(temperature=-0.1)

    def test_inference_config_temperature_too_high(self) -> None:
        with pytest.raises(Exception):
            InferenceConfig(temperature=2.5)

    def test_convergence_similarity_out_of_range(self) -> None:
        with pytest.raises(Exception):
            ConvergenceConfig(similarity_threshold=1.5)

    def test_qdrant_port_out_of_range(self) -> None:
        with pytest.raises(Exception):
            QdrantConfig(port=70000)

    def test_skill_bank_config_dedup_out_of_range(self) -> None:
        with pytest.raises(Exception):
            SkillBankConfig(dedup_threshold=1.5)


# ═══════════════════════════════════════════════════════════════════════════
# Serialization Round-trip Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestSerializationRoundTrip:
    """model_dump() -> model_validate() should produce an equivalent model."""

    def test_agent_state_roundtrip(self) -> None:
        original = AgentState(
            agent_id="coder_01",
            caste=Caste.CODER,
            status=AgentStatus.EXECUTING,
            model_id="local/qwen3-30b",
            subcaste_tier=SubcasteTier.BALANCED,
            team_id="team_a",
        )
        data = original.model_dump()
        restored = AgentState.model_validate(data)
        assert restored == original

    def test_agent_config_roundtrip(self) -> None:
        original = AgentConfig(
            agent_id="arch_01",
            caste=Caste.ARCHITECT,
            model_override="cloud/claude",
            tools=["qdrant_search", "file_read"],
        )
        data = original.model_dump()
        restored = AgentConfig.model_validate(data)
        assert restored == original

    def test_topology_roundtrip(self) -> None:
        original = Topology(
            edges=[
                TopologyEdge(sender="a", receiver="b", weight=0.7),
                TopologyEdge(sender="b", receiver="c", weight=0.3),
            ],
            execution_order=["a", "b", "c"],
            density=0.67,
            isolated_agents=["d"],
        )
        data = original.model_dump()
        restored = Topology.model_validate(data)
        assert restored == original

    def test_episode_roundtrip(self) -> None:
        original = Episode(
            round_num=5,
            summary="Completed feature X.",
            goal="Build feature X",
            agent_outputs={"coder_01": "Wrote module", "reviewer_01": "Approved"},
            timestamp=1709100000.0,
        )
        data = original.model_dump()
        restored = Episode.model_validate(data)
        assert restored == original

    def test_epoch_summary_roundtrip(self) -> None:
        original = EpochSummary(
            epoch_id=2,
            summary="Phase 2 complete.",
            round_range=(6, 10),
            timestamp=1709200000.0,
        )
        data = original.model_dump()
        restored = EpochSummary.model_validate(data)
        assert restored == original

    def test_tkg_tuple_roundtrip(self) -> None:
        original = TKGTuple(
            subject="Coder_01",
            predicate="created",
            object_="handler.py",
            round_num=3,
            team_id="backend",
            timestamp=1709100000.0,
        )
        data = original.model_dump()
        restored = TKGTuple.model_validate(data)
        assert restored == original

    def test_decision_roundtrip(self) -> None:
        original = Decision(
            round_num=4,
            decision_type=DecisionType.ESCALATION,
            detail="Cloud burst triggered.",
            recommendations=["Retry with larger model", "Split task"],
            timestamp=1709100000.0,
        )
        data = original.model_dump()
        restored = Decision.model_validate(data)
        assert restored == original

    def test_round_record_roundtrip(self) -> None:
        topo = Topology(density=0.4, isolated_agents=["orphan"])
        ep = Episode(round_num=2, summary="s", goal="g", timestamp=1709100000.0)
        dec = Decision(
            round_num=2,
            decision_type=DecisionType.ROUTING,
            detail="d",
            timestamp=1709100000.0,
        )
        original = RoundRecord(
            round_num=2,
            goal="Phase 2",
            agent_outputs={"a": "done"},
            topology=topo,
            episode=ep,
            decisions=[dec],
        )
        data = original.model_dump()
        restored = RoundRecord.model_validate(data)
        assert restored == original

    def test_session_result_roundtrip(self) -> None:
        original = SessionResult(
            session_id="sess_042",
            task="Deploy microservice",
            status=ColonyStatus.FAILED,
            rounds_completed=3,
            final_answer=None,
            skill_ids=["lesson_001"],
        )
        data = original.model_dump()
        restored = SessionResult.model_validate(data)
        assert restored == original

    def test_colony_config_roundtrip(self) -> None:
        original = ColonyConfig(
            colony_id="my_colony",
            task="Refactor auth",
            agents=[
                AgentConfig(agent_id="c1", caste=Caste.CODER, tools=["file_write"]),
            ],
            max_rounds=15,
            routing_tau=0.4,
            routing_k_in=4,
            teams=[
                TeamConfig(
                    team_id="t1",
                    name="Core",
                    objective="Refactor core",
                    members=["c1"],
                ),
            ],
            manager=AgentConfig(agent_id="m1", caste=Caste.MANAGER, tools=[]),
            tools_scope=ToolsScope(builtin=["file_read"], mcp=["fetch*"]),
            skill_scope=["general"],
            max_agents=8,
        )
        data = original.model_dump()
        restored = ColonyConfig.model_validate(data)
        assert restored == original

    def test_model_registry_entry_roundtrip(self) -> None:
        original = ModelRegistryEntry(
            model_id="local/qwen3-30b",
            type="autoregressive",
            backend=ModelBackendType.LLAMA_CPP,
            endpoint="http://llm:8080/v1",
            context_length=32768,
            vram_gb=25.6,
            supports_tools=True,
            supports_streaming=True,
            requires_approval=False,
        )
        data = original.model_dump()
        restored = ModelRegistryEntry.model_validate(data)
        assert restored == original

    def test_skill_roundtrip(self) -> None:
        original = Skill(
            skill_id="ts_db_001",
            content="Use connection pooling for database access.",
            tier=SkillTier.TASK_SPECIFIC,
            category="database",
            embedding=[0.1, 0.2, 0.3],
            retrieval_count=5,
            success_correlation=0.8,
            source_colony="db_colony",
            created_at=1709100000.0,
            superseded_by="ts_db_002",
        )
        data = original.model_dump()
        restored = Skill.model_validate(data)
        assert restored == original

    def test_feedback_record_roundtrip(self) -> None:
        original = FeedbackRecord(
            agent_id="coder_01",
            round_num=7,
            feedback_text="Needs more error handling.",
            timestamp=1709100000.0,
        )
        data = original.model_dump()
        restored = FeedbackRecord.model_validate(data)
        assert restored == original

    def test_subcaste_map_entry_roundtrip(self) -> None:
        original = SubcasteMapEntry(
            primary="local/qwen3-30b",
            refine_with="cloud/claude",
            refine_prompt="Review and correct.",
        )
        data = original.model_dump()
        restored = SubcasteMapEntry.model_validate(data)
        assert restored == original

    def test_tools_scope_roundtrip(self) -> None:
        original = ToolsScope(builtin=["file_read", "file_write"], mcp=["fetch*"])
        data = original.model_dump()
        restored = ToolsScope.model_validate(data)
        assert restored == original


# ═══════════════════════════════════════════════════════════════════════════
# load_config() Tests
# ═══════════════════════════════════════════════════════════════════════════


def _minimal_config_dict() -> dict:
    """Return a minimal valid config dict matching FormicOSConfig requirements."""
    return {
        "identity": {"name": "FormicOS", "version": "0.6.0"},
        "hardware": {"gpu": "rtx5090", "vram_gb": 32, "vram_alert_threshold_gb": 28},
        "inference": {
            "endpoint": "http://llm:8080/v1",
            "model": "Qwen3-30B-A3B",
            "model_alias": "gpt-4",
            "max_tokens_per_agent": 5000,
            "temperature": 0,
            "timeout_seconds": 120,
            "context_size": 131072,
            "intent_model": None,
            "intent_max_tokens": 512,
        },
        "embedding": {
            "model": "BAAI/bge-m3",
            "endpoint": "http://embedding:8080/v1",
            "dimensions": 1024,
            "max_tokens": 8192,
            "batch_size": 32,
            "routing_model": "all-MiniLM-L6-v2",
        },
        "routing": {"tau": 0.35, "k_in": 3, "broadcast_fallback": True},
        "convergence": {
            "similarity_threshold": 0.95,
            "rounds_before_force_halt": 2,
            "path_diversity_warning_after": 3,
        },
        "summarization": {
            "epoch_window": 5,
            "max_epoch_tokens": 400,
            "max_agent_summary_tokens": 200,
            "tree_sitter_languages": ["python"],
        },
        "temporal": {
            "episodic_ttl_hours": 72,
            "stall_repeat_threshold": 3,
            "stall_window_minutes": 20,
            "tkg_max_tuples": 5000,
        },
        "castes": {
            "manager": {
                "system_prompt_file": "manager.md",
                "tools": [],
                "model_override": None,
            },
            "coder": {
                "system_prompt_file": "coder.md",
                "tools": ["file_read", "file_write"],
                "model_override": None,
            },
        },
        "persistence": {
            "session_dir": ".formicos/sessions",
            "autosave_interval_seconds": 30,
        },
        "approval_required": ["main_branch_merge"],
        "qdrant": {
            "host": "qdrant",
            "port": 6333,
            "grpc_port": 6334,
            "collections": {
                "project_docs": {"embedding": "bge-m3", "dimensions": 1024},
            },
        },
        "mcp_gateway": {
            "enabled": True,
            "transport": "stdio",
            "command": "docker",
            "args": ["mcp", "gateway", "run"],
            "docker_fallback_endpoint": "http://mcp-gateway:8811",
            "sse_retry_attempts": 5,
            "sse_retry_delay_seconds": 3,
        },
        "model_registry": {
            "local/qwen3-30b": {
                "type": "autoregressive",
                "backend": "llama_cpp",
                "endpoint": "http://llm:8080/v1",
                "context_length": 32768,
                "vram_gb": 25.6,
                "supports_tools": True,
                "supports_streaming": True,
            },
        },
        "skill_bank": {
            "storage_file": ".formicos/skill_bank.json",
            "retrieval_top_k": 3,
            "dedup_threshold": 0.85,
            "evolution_interval": 5,
            "prune_zero_hit_after": 10,
        },
        "subcaste_map": {
            "heavy": {"primary": "local/qwen3-30b"},
            "balanced": {"primary": "local/qwen3-30b"},
            "light": {"primary": "local/qwen3-30b"},
        },
        "teams": {
            "max_teams_per_colony": 4,
            "team_summary_max_tokens": 200,
            "allow_dynamic_spawn": True,
        },
        "colonies": {},
    }


class TestLoadConfig:
    """Test load_config() with YAML files."""

    def test_load_minimal_valid_yaml(self, tmp_path: Path) -> None:
        config_data = _minimal_config_dict()
        config_file = tmp_path / "formicos.yaml"
        config_file.write_text(yaml.dump(config_data), encoding="utf-8")

        cfg = load_config(config_file)

        assert isinstance(cfg, FormicOSConfig)
        assert cfg.identity.name == "FormicOS"
        assert cfg.identity.version == "0.6.0"
        assert cfg.hardware.gpu == "rtx5090"
        assert cfg.inference.model == "Qwen3-30B-A3B"
        assert cfg.embedding.dimensions == 1024
        assert cfg.routing.tau == 0.35
        assert cfg.convergence.similarity_threshold == 0.95
        assert "manager" in cfg.castes
        assert "coder" in cfg.castes
        assert cfg.castes["coder"].tools == ["file_read", "file_write"]
        assert cfg.qdrant.host == "qdrant"
        assert "project_docs" in cfg.qdrant.collections
        assert cfg.mcp_gateway.enabled is True
        assert "local/qwen3-30b" in cfg.model_registry
        assert cfg.model_registry["local/qwen3-30b"].backend == ModelBackendType.LLAMA_CPP
        assert cfg.skill_bank.retrieval_top_k == 3
        assert cfg.subcaste_map["heavy"].primary == "local/qwen3-30b"
        assert cfg.teams.max_teams_per_colony == 4
        assert cfg.colonies == {}
        assert cfg.cloud_burst is None

    def test_load_with_cloud_burst(self, tmp_path: Path) -> None:
        config_data = _minimal_config_dict()
        config_data["cloud_burst"] = {
            "enabled": False,
            "provider": "anthropic",
            "model": "claude-sonnet-4-5-20250929",
            "trigger": "2 consecutive test failures",
            "requires_approval": True,
        }
        config_file = tmp_path / "formicos.yaml"
        config_file.write_text(yaml.dump(config_data), encoding="utf-8")

        cfg = load_config(config_file)
        assert cfg.cloud_burst is not None
        assert cfg.cloud_burst.provider == "anthropic"
        assert cfg.cloud_burst.requires_approval is True

    def test_load_with_colonies(self, tmp_path: Path) -> None:
        config_data = _minimal_config_dict()
        config_data["colonies"] = {
            "test_colony": {
                "colony_id": "test_colony",
                "task": "Build a REST API",
                "max_rounds": 10,
            }
        }
        config_file = tmp_path / "formicos.yaml"
        config_file.write_text(yaml.dump(config_data), encoding="utf-8")

        cfg = load_config(config_file)
        assert "test_colony" in cfg.colonies
        assert cfg.colonies["test_colony"].task == "Build a REST API"

    def test_load_missing_file(self) -> None:
        with pytest.raises(FileNotFoundError):
            load_config("/nonexistent/path/formicos.yaml")

    def test_load_empty_file(self, tmp_path: Path) -> None:
        config_file = tmp_path / "formicos.yaml"
        config_file.write_text("", encoding="utf-8")
        with pytest.raises(ValueError, match="empty"):
            load_config(config_file)

    def test_load_missing_required_field_identity(self, tmp_path: Path) -> None:
        config_data = _minimal_config_dict()
        del config_data["identity"]
        config_file = tmp_path / "formicos.yaml"
        config_file.write_text(yaml.dump(config_data), encoding="utf-8")

        with pytest.raises(Exception):
            load_config(config_file)

    def test_load_missing_required_field_castes(self, tmp_path: Path) -> None:
        config_data = _minimal_config_dict()
        del config_data["castes"]
        config_file = tmp_path / "formicos.yaml"
        config_file.write_text(yaml.dump(config_data), encoding="utf-8")

        with pytest.raises(Exception):
            load_config(config_file)

    def test_load_missing_required_field_model_registry(self, tmp_path: Path) -> None:
        config_data = _minimal_config_dict()
        del config_data["model_registry"]
        config_file = tmp_path / "formicos.yaml"
        config_file.write_text(yaml.dump(config_data), encoding="utf-8")

        with pytest.raises(Exception):
            load_config(config_file)

    def test_load_empty_castes_rejected(self, tmp_path: Path) -> None:
        config_data = _minimal_config_dict()
        config_data["castes"] = {}
        config_file = tmp_path / "formicos.yaml"
        config_file.write_text(yaml.dump(config_data), encoding="utf-8")

        with pytest.raises(Exception):
            load_config(config_file)

    def test_load_empty_model_registry_rejected(self, tmp_path: Path) -> None:
        config_data = _minimal_config_dict()
        config_data["model_registry"] = {}
        config_file = tmp_path / "formicos.yaml"
        config_file.write_text(yaml.dump(config_data), encoding="utf-8")

        with pytest.raises(Exception):
            load_config(config_file)

    def test_load_invalid_backend_in_registry(self, tmp_path: Path) -> None:
        config_data = _minimal_config_dict()
        config_data["model_registry"]["local/qwen3-30b"]["backend"] = "invalid"
        config_file = tmp_path / "formicos.yaml"
        config_file.write_text(yaml.dump(config_data), encoding="utf-8")

        with pytest.raises(Exception):
            load_config(config_file)

    def test_load_via_env_var(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        config_data = _minimal_config_dict()
        config_file = tmp_path / "custom_config.yaml"
        config_file.write_text(yaml.dump(config_data), encoding="utf-8")

        monkeypatch.setenv("FORMICOS_CONFIG", str(config_file))
        cfg = load_config()  # No path argument -- should use env var

        assert isinstance(cfg, FormicOSConfig)
        assert cfg.identity.name == "FormicOS"

    def test_load_path_argument_overrides_env_var(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Set env var to a non-existent file
        monkeypatch.setenv("FORMICOS_CONFIG", "/nonexistent/env_config.yaml")

        # But pass a valid file as the path argument
        config_data = _minimal_config_dict()
        config_file = tmp_path / "direct_config.yaml"
        config_file.write_text(yaml.dump(config_data), encoding="utf-8")

        cfg = load_config(config_file)
        assert isinstance(cfg, FormicOSConfig)

    def test_load_string_path(self, tmp_path: Path) -> None:
        config_data = _minimal_config_dict()
        config_file = tmp_path / "formicos.yaml"
        config_file.write_text(yaml.dump(config_data), encoding="utf-8")

        cfg = load_config(str(config_file))
        assert isinstance(cfg, FormicOSConfig)


# ═══════════════════════════════════════════════════════════════════════════
# Schema Version Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestSchemaVersion:
    """All persisted models must have schema_version='0.6.0'."""

    @pytest.mark.parametrize(
        "model_cls,kwargs",
        [
            (AgentState, {"agent_id": "x", "caste": "coder"}),
            (AgentConfig, {"agent_id": "x", "caste": "coder", "tools": []}),
            (TopologyEdge, {"sender": "a", "receiver": "b", "weight": 0.5}),
            (Topology, {}),
            (Episode, {"round_num": 0, "summary": "s", "goal": "g"}),
            (EpochSummary, {"epoch_id": 0, "summary": "s", "round_range": (0, 1)}),
            (TKGTuple, {"subject": "s", "predicate": "p", "object_": "o", "round_num": 0}),
            (Decision, {"round_num": 0, "decision_type": "routing", "detail": "d"}),
            (RoundRecord, {"round_num": 0, "goal": "g"}),
            (SessionResult, {"session_id": "s", "task": "t", "status": "completed", "rounds_completed": 0}),
            (ColonyConfig, {"colony_id": "c", "task": "t"}),
            (TeamConfig, {"team_id": "t", "name": "n", "objective": "o"}),
            (ModelRegistryEntry, {"backend": "llama_cpp"}),
            (Skill, {"skill_id": "s", "content": "c", "tier": "general", "created_at": 0.0}),
            (FeedbackRecord, {"agent_id": "a", "round_num": 0, "feedback_text": "f"}),
        ],
    )
    def test_schema_version_present(self, model_cls: type, kwargs: dict) -> None:
        instance = model_cls(**kwargs)
        assert instance.schema_version == "0.6.0"


# ═══════════════════════════════════════════════════════════════════════════
# Edge Case Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestEdgeCases:
    """Test boundary conditions and edge cases."""

    def test_topology_empty(self) -> None:
        t = Topology()
        assert t.edges == []
        assert t.execution_order == []
        assert t.density == 0.0
        assert t.isolated_agents == []

    def test_colony_config_boundary_max_rounds(self) -> None:
        cc1 = ColonyConfig(colony_id="c", task="t", max_rounds=1)
        assert cc1.max_rounds == 1
        cc100 = ColonyConfig(colony_id="c", task="t", max_rounds=100)
        assert cc100.max_rounds == 100

    def test_epoch_summary_same_start_end(self) -> None:
        es = EpochSummary(
            epoch_id=1, summary="Single round epoch.", round_range=(5, 5)
        )
        assert es.round_range == (5, 5)

    def test_episode_zero_round(self) -> None:
        ep = Episode(round_num=0, summary="init", goal="start")
        assert ep.round_num == 0

    def test_skill_zero_correlation(self) -> None:
        sk = Skill(
            skill_id="s",
            content="c",
            tier=SkillTier.GENERAL,
            success_correlation=0.0,
            created_at=0.0,
        )
        assert sk.success_correlation == 0.0

    def test_skill_max_correlation(self) -> None:
        sk = Skill(
            skill_id="s",
            content="c",
            tier=SkillTier.GENERAL,
            success_correlation=1.0,
            created_at=0.0,
        )
        assert sk.success_correlation == 1.0

    def test_topology_density_zero(self) -> None:
        t = Topology(density=0.0)
        assert t.density == 0.0

    def test_topology_density_one(self) -> None:
        t = Topology(density=1.0)
        assert t.density == 1.0

    def test_decision_empty_recommendations(self) -> None:
        d = Decision(
            round_num=0,
            decision_type=DecisionType.STALL,
            detail="No progress.",
        )
        assert d.recommendations == []

    def test_session_result_no_final_answer(self) -> None:
        sr = SessionResult(
            session_id="s",
            task="t",
            status=ColonyStatus.FAILED,
            rounds_completed=0,
        )
        assert sr.final_answer is None
        assert sr.skill_ids == []

    def test_model_registry_entry_minimal(self) -> None:
        mre = ModelRegistryEntry(backend=ModelBackendType.OLLAMA)
        assert mre.endpoint is None
        assert mre.model_string is None
        assert mre.vram_gb is None
        assert mre.context_length == 32768

    def test_formicos_config_from_dict(self) -> None:
        """FormicOSConfig can be constructed from a dict (model_validate)."""
        data = _minimal_config_dict()
        cfg = FormicOSConfig.model_validate(data)
        assert cfg.identity.name == "FormicOS"
        assert len(cfg.castes) == 2
        assert len(cfg.model_registry) == 1

    def test_formicos_config_roundtrip(self) -> None:
        """Full FormicOSConfig round-trip through model_dump/model_validate."""
        data = _minimal_config_dict()
        cfg1 = FormicOSConfig.model_validate(data)
        dumped = cfg1.model_dump()
        cfg2 = FormicOSConfig.model_validate(dumped)
        assert cfg1 == cfg2
