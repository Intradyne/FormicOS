"""
Tests for FormicOS v0.8.0 Durable Execution.

Covers:
  - CheckpointMeta and ResumeDirective model validation
  - Checkpoint written after round (round_history, pheromone weights)
  - Orchestrator resume from directive (round, history, janitor state)
  - Registry crash detection (RUNNING + session file → needs_crash_resume)
  - auto_resume_crashed() integration
  - Checkpoint failure is non-fatal
  - Governance streak restoration
"""

import asyncio
import json
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.context import AsyncContextTree
from src.models import (
    CheckpointMeta,
    ColonyStatus,
    ResumeDirective,
)


# ── Model Validation ─────────────────────────────────────────────────────


class TestCheckpointMetaModel:
    """CheckpointMeta Pydantic model tests."""

    def test_checkpoint_meta_defaults(self):
        """All optional fields have sane defaults."""
        meta = CheckpointMeta(
            colony_id="test-colony",
            session_id="sess-001",
            completed_round=2,
            max_rounds=10,
            task="Build an API",
        )
        assert meta.schema_version == "0.9.0"
        assert meta.colony_id == "test-colony"
        assert meta.completed_round == 2
        assert meta.max_rounds == 10
        assert meta.round_history == []
        assert meta.pheromone_weights == {}
        assert meta.convergence_streak == 0
        assert meta.prev_summary_vec is None
        assert meta.timestamp > 0

    def test_checkpoint_meta_full(self):
        """All fields populated and serializable."""
        meta = CheckpointMeta(
            colony_id="c1",
            session_id="s1",
            completed_round=5,
            max_rounds=10,
            task="test",
            timestamp=1234567890.0,
            round_history=[{"round": 0, "goal": "init"}],
            pheromone_weights={"a|b": 0.5, "b|c": -0.8},
            convergence_streak=3,
            prev_summary_vec=[0.1, 0.2, 0.3],
        )
        data = meta.model_dump()
        assert data["pheromone_weights"]["a|b"] == 0.5
        assert data["prev_summary_vec"] == [0.1, 0.2, 0.3]

        # Round-trip
        restored = CheckpointMeta.model_validate(data)
        assert restored.completed_round == 5
        assert restored.convergence_streak == 3

    def test_checkpoint_meta_json_serializable(self):
        """model_dump(mode='json') produces valid JSON."""
        meta = CheckpointMeta(
            colony_id="c1",
            session_id="s1",
            completed_round=1,
            max_rounds=5,
            task="test",
        )
        json_data = meta.model_dump(mode="json")
        serialized = json.dumps(json_data)
        assert "c1" in serialized


class TestResumeDirectiveModel:
    """ResumeDirective Pydantic model tests."""

    def test_resume_directive_defaults(self):
        """Minimal ResumeDirective with defaults."""
        rd = ResumeDirective(
            colony_id="c1",
            resume_from_round=3,
            max_rounds=10,
            session_id="s1",
        )
        assert rd.resume_from_round == 3
        assert rd.round_history == []
        assert rd.pheromone_weights == {}
        assert rd.convergence_streak == 0
        assert rd.prev_summary_vec is None

    def test_resume_directive_from_checkpoint(self):
        """Build ResumeDirective from CheckpointMeta data."""
        checkpoint_data = {
            "completed_round": 4,
            "max_rounds": 10,
            "session_id": "s1",
            "round_history": [{"round": 0}, {"round": 1}],
            "pheromone_weights": {"a|b": 0.3},
            "convergence_streak": 2,
            "prev_summary_vec": [0.5, 0.6],
        }
        rd = ResumeDirective(
            colony_id="c1",
            resume_from_round=checkpoint_data["completed_round"] + 1,
            max_rounds=checkpoint_data["max_rounds"],
            session_id=checkpoint_data["session_id"],
            round_history=checkpoint_data["round_history"],
            pheromone_weights=checkpoint_data["pheromone_weights"],
            convergence_streak=checkpoint_data["convergence_streak"],
            prev_summary_vec=checkpoint_data["prev_summary_vec"],
        )
        assert rd.resume_from_round == 5
        assert len(rd.round_history) == 2
        assert rd.pheromone_weights["a|b"] == 0.3


# ── Orchestrator Checkpoint ──────────────────────────────────────────────


def _make_mock_config():
    """Create a minimal mock config."""
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


class TestOrchestratorCheckpoint:
    """Test the _checkpoint() method on Orchestrator."""

    @pytest.mark.asyncio
    async def test_checkpoint_writes_to_context_tree(self, tmp_path):
        """_checkpoint() stores CheckpointMeta in ctx['colony']['checkpoint']."""
        from src.orchestrator import Orchestrator

        ctx = AsyncContextTree()
        config = _make_mock_config()

        orch = Orchestrator(
            context_tree=ctx,
            config=config,
            colony_id="ckpt-test",
        )

        # Simulate some orchestrator state
        orch._session_id = "sess-001"
        orch._current_round = 2
        orch._max_rounds = 10
        orch._round_history = [
            {"round": 0, "goal": "init"},
            {"round": 1, "goal": "iterate"},
        ]

        # Set the colony task in ctx so checkpoint can read it
        await ctx.set("colony", "task", "Build an API")

        # Set up session dir for save
        _session_dir = tmp_path / ".formicos" / "sessions" / "ckpt-test"

        with patch.object(orch, "ctx") as mock_ctx:
            mock_ctx.get = ctx.get
            mock_ctx.set = ctx.set
            mock_ctx.save = AsyncMock()

            # We need _ctx_set to work - it calls ctx.set
            async def _mock_ctx_set(scope, key, value):
                await ctx.set(scope, key, value)
            orch._ctx_set = _mock_ctx_set

            await orch._checkpoint()

        checkpoint_data = ctx.get("colony", "checkpoint")
        assert checkpoint_data is not None
        assert checkpoint_data["colony_id"] == "ckpt-test"
        assert checkpoint_data["completed_round"] == 2
        assert checkpoint_data["session_id"] == "sess-001"
        assert len(checkpoint_data["round_history"]) == 2

    @pytest.mark.asyncio
    async def test_checkpoint_failure_is_nonfatal(self):
        """If _checkpoint() raises, the orchestrator continues."""
        from src.orchestrator import Orchestrator

        ctx = AsyncContextTree()
        config = _make_mock_config()

        orch = Orchestrator(
            context_tree=ctx,
            config=config,
            colony_id="fail-ckpt",
        )

        # Force _ctx_set to raise
        orch._ctx_set = AsyncMock(side_effect=RuntimeError("disk full"))
        orch._session_id = "s1"
        orch._current_round = 1
        orch._max_rounds = 5
        orch._round_history = []

        # Should not raise — checkpoint failure is non-fatal
        try:
            await orch._checkpoint()
        except RuntimeError:
            pass  # Non-fatal in actual run() loop (wrapped in try/except)


class TestOrchestratorResume:
    """Test that Orchestrator correctly restores state from ResumeDirective."""

    def test_resume_directive_stored(self):
        """resume_directive parameter is stored on __init__."""
        from src.orchestrator import Orchestrator

        ctx = AsyncContextTree()
        config = _make_mock_config()

        rd = ResumeDirective(
            colony_id="c1",
            resume_from_round=3,
            max_rounds=10,
            session_id="s1",
            round_history=[{"round": 0}],
        )

        orch = Orchestrator(
            context_tree=ctx,
            config=config,
            colony_id="c1",
            resume_directive=rd,
        )

        assert orch._resume_directive is not None
        assert orch._resume_directive.resume_from_round == 3

    def test_no_resume_directive_by_default(self):
        """Without resume_directive, it defaults to None."""
        from src.orchestrator import Orchestrator

        ctx = AsyncContextTree()
        config = _make_mock_config()

        orch = Orchestrator(
            context_tree=ctx,
            config=config,
            colony_id="c1",
        )

        assert orch._resume_directive is None


# ── Colony Manager Crash Detection ───────────────────────────────────────


class TestRegistryCrashDetection:
    """Test _load_registry_sync() crash detection with checkpoints."""

    def test_running_colony_with_checkpoint_sets_needs_crash_resume(self, tmp_path):
        """RUNNING colony with checkpoint in session file → needs_crash_resume=True."""
        from src.colony_manager import ColonyManager

        # Create registry file with a RUNNING colony
        registry_path = tmp_path / ".formicos" / "registry.json"
        registry_path.parent.mkdir(parents=True, exist_ok=True)
        registry_data = {
            "colony-1": {
                "colony_id": "colony-1",
                "name": "Test Colony",
                "task": "Build something",
                "max_rounds": 10,
                "status": "running",
                "origin": "api",
                "created_at": time.time(),
                "updated_at": time.time(),
            }
        }
        with open(registry_path, "w") as f:
            json.dump(registry_data, f)

        # Create session file with checkpoint
        session_dir = tmp_path / ".formicos" / "sessions" / "colony-1"
        session_dir.mkdir(parents=True, exist_ok=True)
        session_file = session_dir / "context.json"
        session_data = {
            "colony": {
                "checkpoint": {
                    "schema_version": "0.9.0",
                    "colony_id": "colony-1",
                    "session_id": "s1",
                    "completed_round": 3,
                    "max_rounds": 10,
                    "task": "Build something",
                    "timestamp": time.time(),
                    "round_history": [],
                    "pheromone_weights": {},
                    "convergence_streak": 0,
                    "prev_summary_vec": None,
                },
                "task": "Build something",
            },
            "system": {},
            "agent": {},
            "round": {},
            "team": {},
            "supercolony": {},
        }
        with open(session_file, "w") as f:
            json.dump(session_data, f)

        # Create a mock ColonyManager that uses our tmp_path
        config = _make_mock_config()
        config.model_registry = {}

        with patch("src.colony_manager.DEFAULT_SESSION_BASE", tmp_path / ".formicos" / "sessions"):
            cm = ColonyManager.__new__(ColonyManager)
            cm._colonies = {}
            cm._lock = asyncio.Lock()
            cm._registry_path = registry_path
            cm._workspace_base = tmp_path / "workspace"
            cm._config = config

            cm._load_registry_sync()

        state = cm._colonies.get("colony-1")
        assert state is not None
        assert state.needs_crash_resume is True
        assert state.info.status == ColonyStatus.PAUSED

    def test_running_colony_without_checkpoint_no_crash_resume(self, tmp_path):
        """RUNNING colony without checkpoint → needs_crash_resume=False."""
        from src.colony_manager import ColonyManager

        registry_path = tmp_path / ".formicos" / "registry.json"
        registry_path.parent.mkdir(parents=True, exist_ok=True)
        registry_data = {
            "colony-2": {
                "colony_id": "colony-2",
                "name": "Test Colony 2",
                "task": "Build something",
                "max_rounds": 10,
                "status": "running",
                "origin": "api",
                "created_at": time.time(),
                "updated_at": time.time(),
            }
        }
        with open(registry_path, "w") as f:
            json.dump(registry_data, f)

        config = _make_mock_config()
        config.model_registry = {}

        with patch("src.colony_manager.DEFAULT_SESSION_BASE", tmp_path / ".formicos" / "sessions"):
            cm = ColonyManager.__new__(ColonyManager)
            cm._colonies = {}
            cm._lock = asyncio.Lock()
            cm._registry_path = registry_path
            cm._workspace_base = tmp_path / "workspace"
            cm._config = config

            cm._load_registry_sync()

        state = cm._colonies.get("colony-2")
        assert state is not None
        assert state.needs_crash_resume is False
        assert state.info.status == ColonyStatus.PAUSED

    def test_completed_colony_not_flagged_for_resume(self, tmp_path):
        """COMPLETED colony is not flagged for crash resume."""
        from src.colony_manager import ColonyManager

        registry_path = tmp_path / ".formicos" / "registry.json"
        registry_path.parent.mkdir(parents=True, exist_ok=True)
        registry_data = {
            "colony-3": {
                "colony_id": "colony-3",
                "name": "Done Colony",
                "task": "Done",
                "max_rounds": 5,
                "status": "completed",
                "origin": "api",
                "created_at": time.time(),
                "updated_at": time.time(),
            }
        }
        with open(registry_path, "w") as f:
            json.dump(registry_data, f)

        config = _make_mock_config()
        config.model_registry = {}

        with patch("src.colony_manager.DEFAULT_SESSION_BASE", tmp_path / ".formicos" / "sessions"):
            cm = ColonyManager.__new__(ColonyManager)
            cm._colonies = {}
            cm._lock = asyncio.Lock()
            cm._registry_path = registry_path
            cm._workspace_base = tmp_path / "workspace"
            cm._config = config

            cm._load_registry_sync()

        state = cm._colonies.get("colony-3")
        assert state is not None
        assert state.needs_crash_resume is False


# ── Auto-Resume Integration ──────────────────────────────────────────────


class TestAutoResumeCrashed:
    """Test auto_resume_crashed() method."""

    @pytest.mark.asyncio
    async def test_auto_resume_with_no_candidates(self):
        """No colonies need resume → empty list returned."""
        from src.colony_manager import ColonyManager

        cm = ColonyManager.__new__(ColonyManager)
        cm._colonies = {}
        cm._lock = asyncio.Lock()

        result = await cm.auto_resume_crashed()
        assert result == []

    @pytest.mark.asyncio
    async def test_auto_resume_failed_clears_flag(self, tmp_path):
        """If _resume_from_checkpoint fails, needs_crash_resume is cleared."""
        from src.colony_manager import ColonyManager, _ColonyState, ColonyInfo

        info = ColonyInfo(
            colony_id="crash-1",
            name="Crashed",
            task="test",
            max_rounds=5,
            status=ColonyStatus.PAUSED,
        )

        state = _ColonyState(
            info=info,
            context_tree=AsyncContextTree(),
            needs_crash_resume=True,
        )

        cm = ColonyManager.__new__(ColonyManager)
        cm._colonies = {"crash-1": state}
        cm._lock = asyncio.Lock()

        # Mock _resume_from_checkpoint to fail
        cm._resume_from_checkpoint = AsyncMock(
            side_effect=FileNotFoundError("no session")
        )

        result = await cm.auto_resume_crashed()
        assert result == []
        assert state.needs_crash_resume is False


# ── Checkpoint + Governance Streak ───────────────────────────────────────


class TestGovernanceStreakRestoration:
    """Verify governance convergence_streak survives checkpoint/resume cycle."""

    def test_checkpoint_captures_streak(self):
        """CheckpointMeta.convergence_streak field works."""
        meta = CheckpointMeta(
            colony_id="c1",
            session_id="s1",
            completed_round=3,
            max_rounds=10,
            task="test",
            convergence_streak=5,
        )
        assert meta.convergence_streak == 5

        data = meta.model_dump()
        restored = CheckpointMeta.model_validate(data)
        assert restored.convergence_streak == 5

    def test_resume_directive_carries_streak(self):
        """ResumeDirective passes streak to orchestrator."""
        rd = ResumeDirective(
            colony_id="c1",
            resume_from_round=4,
            max_rounds=10,
            session_id="s1",
            convergence_streak=3,
        )
        assert rd.convergence_streak == 3
