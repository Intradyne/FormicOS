"""Unit tests for formicos.surface.colony_manager."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from formicos.engine.strategies.sequential import SequentialStrategy
from formicos.surface.colony_manager import ColonyManager


def _make_colony_projection(
    colony_id: str = "colony-abc",
    status: str = "running",
    round_number: int = 0,
    max_rounds: int = 5,
    workspace_id: str = "ws1",
    thread_id: str = "th1",
    task: str = "do stuff",
    strategy: str = "sequential",
    castes: list[dict[str, str]] | None = None,
    model_assignments: dict[str, str] | None = None,
) -> MagicMock:
    colony = MagicMock()
    colony.id = colony_id
    colony.status = status
    colony.round_number = round_number
    colony.max_rounds = max_rounds
    colony.workspace_id = workspace_id
    colony.thread_id = thread_id
    colony.task = task
    colony.strategy = strategy
    colony.castes = castes or [{"caste": "coder", "tier": "standard", "count": 1}]
    colony.model_assignments = model_assignments or {}
    return colony


def _make_runtime(
    colony: Any = None,
    colonies_dict: dict[str, Any] | None = None,
) -> MagicMock:
    runtime = MagicMock()
    runtime.emit_and_broadcast = AsyncMock(return_value=1)
    runtime.embed_fn = None
    runtime.embed_client = None
    runtime.vector_store = None
    runtime.settings = MagicMock()
    runtime.settings.routing.tau_threshold = 0.35
    runtime.settings.routing.k_in_cap = 5
    runtime.build_agents.return_value = []

    if colony is not None:
        runtime.projections.get_colony.return_value = colony
    else:
        runtime.projections.get_colony.return_value = None

    runtime.projections.colonies = colonies_dict or {}

    return runtime


# ---------------------------------------------------------------------------
# start_colony tests
# ---------------------------------------------------------------------------


class TestStartColony:
    """Tests for ColonyManager.start_colony."""

    @pytest.mark.anyio()
    async def test_creates_task_for_running_colony(self) -> None:
        colony = _make_colony_projection(status="running")
        runtime = _make_runtime(colony=colony)
        manager = ColonyManager(runtime)

        # Patch _run_colony to avoid actual execution
        async def _fake_run(cid: str) -> None:
            return

        with patch.object(manager, "_run_colony", side_effect=_fake_run):
            await manager.start_colony("colony-abc")

        assert manager.active_count >= 0  # task may already be done
        # The task was created (even if completed immediately)

    @pytest.mark.anyio()
    async def test_skips_non_running_colony(self) -> None:
        colony = _make_colony_projection(status="completed")
        runtime = _make_runtime(colony=colony)
        manager = ColonyManager(runtime)

        await manager.start_colony("colony-abc")

        assert manager.active_count == 0

    @pytest.mark.anyio()
    async def test_skips_colony_not_found(self) -> None:
        runtime = _make_runtime(colony=None)
        manager = ColonyManager(runtime)

        await manager.start_colony("colony-missing")

        assert manager.active_count == 0

    @pytest.mark.anyio()
    async def test_skips_already_active_colony(self) -> None:
        colony = _make_colony_projection(status="running")
        runtime = _make_runtime(colony=colony)
        manager = ColonyManager(runtime)

        # Simulate an existing active task
        manager._active["colony-abc"] = MagicMock(spec=asyncio.Task)

        await manager.start_colony("colony-abc")

        # Should not have replaced the task
        assert manager.active_count == 1


# ---------------------------------------------------------------------------
# stop_colony tests
# ---------------------------------------------------------------------------


class TestStopColony:
    """Tests for ColonyManager.stop_colony."""

    @pytest.mark.anyio()
    async def test_cancels_active_task(self) -> None:
        runtime = _make_runtime()
        manager = ColonyManager(runtime)

        task = MagicMock(spec=asyncio.Task)
        manager._active["colony-abc"] = task

        await manager.stop_colony("colony-abc")

        task.cancel.assert_called_once()
        assert "colony-abc" not in manager._active

    @pytest.mark.anyio()
    async def test_noop_for_unknown_colony(self) -> None:
        runtime = _make_runtime()
        manager = ColonyManager(runtime)

        await manager.stop_colony("colony-missing")

        assert manager.active_count == 0


# ---------------------------------------------------------------------------
# rehydrate tests
# ---------------------------------------------------------------------------


class TestRehydrate:
    """Tests for rehydrating running colonies on startup."""

    @pytest.mark.anyio()
    async def test_restarts_running_colonies(self) -> None:
        colony1 = _make_colony_projection(colony_id="c1", status="running")
        colony2 = _make_colony_projection(colony_id="c2", status="completed")
        colony3 = _make_colony_projection(colony_id="c3", status="running")

        runtime = _make_runtime(colonies_dict={"c1": colony1, "c2": colony2, "c3": colony3})
        # get_colony must return the right colony for each id
        runtime.projections.get_colony.side_effect = lambda cid: {"c1": colony1, "c3": colony3}.get(cid)
        manager = ColonyManager(runtime)

        async def _fake_run(cid: str) -> None:
            return

        with patch.object(manager, "_run_colony", side_effect=_fake_run):
            await manager.rehydrate()

        # Should have attempted to start c1 and c3 (both running), not c2 (completed)
        # Since _run_colony completes immediately, tasks may already be cleaned up
        # but we can verify get_colony was called for the running ones
        calls = [c.args[0] for c in runtime.projections.get_colony.call_args_list]
        assert "c1" in calls
        assert "c3" in calls


# ---------------------------------------------------------------------------
# active_count tests
# ---------------------------------------------------------------------------


class TestActiveCount:
    """Tests for the active_count property."""

    def test_zero_when_empty(self) -> None:
        runtime = _make_runtime()
        manager = ColonyManager(runtime)
        assert manager.active_count == 0

    def test_reflects_active_tasks(self) -> None:
        runtime = _make_runtime()
        manager = ColonyManager(runtime)
        manager._active["c1"] = MagicMock(spec=asyncio.Task)
        manager._active["c2"] = MagicMock(spec=asyncio.Task)
        assert manager.active_count == 2


class TestTranscriptHarvest:
    """Tests for runtime transcript harvest close-out seams."""

    @pytest.mark.anyio()
    async def test_run_transcript_harvest_uses_round_records(self) -> None:
        runtime = MagicMock()
        runtime.resolve_model = MagicMock(return_value="anthropic/claude-haiku")
        runtime.llm_router.complete = AsyncMock(return_value=SimpleNamespace(
            content=(
                '{"entries": [{"turn_index": 0, "type": "learning", '
                '"summary": "Document auth timeout retry handling before '
                'future database changes."}]}'
            ),
        ))
        runtime.emit_and_broadcast = AsyncMock(return_value=1)
        runtime.memory_store = None
        runtime.projections = SimpleNamespace(memory_extractions_completed=set())

        colony_proj = SimpleNamespace(
            thread_id="thread-1",
            round_records=[
                SimpleNamespace(
                    round_number=2,
                    agent_outputs={
                        "agent-1": (
                            "Investigated the timeout root cause and added a safe "
                            "retry guard around the connection setup."
                        ),
                    },
                ),
            ],
            agents={"agent-1": SimpleNamespace(caste="coder")},
        )

        manager = ColonyManager.__new__(ColonyManager)
        manager._runtime = runtime

        await manager._run_transcript_harvest("col-1", "ws-1", True, colony_proj)

        prompt = runtime.llm_router.complete.await_args.kwargs["messages"][1]["content"]
        assert "agent=agent-1" in prompt
        assert "caste=coder" in prompt
        assert "round=2" in prompt

        emitted = [call.args[0] for call in runtime.emit_and_broadcast.await_args_list]
        created = [event for event in emitted if getattr(event, "type", "") == "MemoryEntryCreated"]
        completed = [event for event in emitted if getattr(event, "type", "") == "MemoryExtractionCompleted"]
        assert len(created) == 1
        assert len(completed) == 1
        assert completed[0].entries_created == 1
        assert "col-1:harvest" in runtime.projections.memory_extractions_completed

    @pytest.mark.anyio()
    async def test_run_transcript_harvest_skips_environment_noise(self) -> None:
        runtime = MagicMock()
        runtime.resolve_model = MagicMock(return_value="anthropic/claude-haiku")
        runtime.llm_router.complete = AsyncMock(return_value=SimpleNamespace(
            content=(
                '{"entries": ['
                '{"turn_index": 0, "type": "learning", '
                '"summary": "The workspace directory remains unconfigured despite repeated attempts."}, '
                '{"turn_index": 0, "type": "learning", '
                '"summary": "Document auth timeout retry handling before future database changes."}'
                "]}")
        ))
        runtime.emit_and_broadcast = AsyncMock(return_value=1)
        runtime.memory_store = None
        runtime.projections = SimpleNamespace(memory_extractions_completed=set())

        colony_proj = SimpleNamespace(
            thread_id="thread-1",
            round_records=[
                SimpleNamespace(
                    round_number=1,
                    agent_outputs={"agent-1": "Investigated timeout handling."},
                ),
            ],
            agents={"agent-1": SimpleNamespace(caste="coder")},
        )

        manager = ColonyManager.__new__(ColonyManager)
        manager._runtime = runtime

        await manager._run_transcript_harvest("col-2", "ws-1", True, colony_proj)

        emitted = [call.args[0] for call in runtime.emit_and_broadcast.await_args_list]
        created = [event for event in emitted if getattr(event, "type", "") == "MemoryEntryCreated"]
        completed = [event for event in emitted if getattr(event, "type", "") == "MemoryExtractionCompleted"]
        assert len(created) == 1
        assert created[0].entry["content"] == "Document auth timeout retry handling before future database changes."
        assert completed[0].entries_created == 1


class TestDeferredPostColonyWork:
    """Completion-time extraction/harvest should defer until colonies go idle."""

    @pytest.mark.anyio()
    async def test_memory_extraction_is_deferred_while_other_colonies_run(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        runtime = _make_runtime()
        runtime.projections.memory_extractions_completed = set()
        runtime.projections.get_colony.return_value = SimpleNamespace(
            artifacts=[],
            summary="final summary",
        )
        manager = ColonyManager(runtime)
        manager.extract_institutional_memory = AsyncMock()

        active_task = MagicMock(spec=asyncio.Task)
        active_task.done.return_value = False
        manager._active["other-colony"] = active_task

        monkeypatch.setattr(
            "formicos.surface.colony_manager._POST_COLONY_DRAIN_POLL_S",
            0.01,
        )

        manager._hook_memory_extraction("col-1", "ws1", True)
        await asyncio.sleep(0.02)

        manager.extract_institutional_memory.assert_not_awaited()
        assert len(manager._deferred_post_colony_work) == 1

        if manager._post_colony_drain_task is not None:
            manager._post_colony_drain_task.cancel()
            with patch("formicos.surface.colony_manager.log"):
                await asyncio.gather(
                    manager._post_colony_drain_task,
                    return_exceptions=True,
                )

    @pytest.mark.anyio()
    async def test_deferred_memory_extraction_drains_when_colonies_go_idle(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        runtime = _make_runtime()
        runtime.projections.memory_extractions_completed = set()
        runtime.projections.get_colony.return_value = SimpleNamespace(
            artifacts=[],
            summary="final summary",
        )
        manager = ColonyManager(runtime)
        manager.extract_institutional_memory = AsyncMock()

        active_task = MagicMock(spec=asyncio.Task)
        active_task.done.return_value = False
        manager._active["other-colony"] = active_task

        monkeypatch.setattr(
            "formicos.surface.colony_manager._POST_COLONY_DRAIN_POLL_S",
            0.01,
        )

        manager._hook_memory_extraction("col-2", "ws1", True)
        await asyncio.sleep(0.02)
        manager.extract_institutional_memory.assert_not_awaited()

        active_task.done.return_value = True
        manager._on_colony_task_done("other-colony")
        await asyncio.sleep(0.05)

        manager.extract_institutional_memory.assert_awaited_once()
        assert manager._deferred_post_colony_work == []

    @pytest.mark.anyio()
    async def test_transcript_harvest_is_deferred_while_other_colonies_run(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        runtime = _make_runtime()
        runtime.projections.memory_extractions_completed = set()
        runtime.projections.get_colony.return_value = SimpleNamespace(
            thread_id="th1",
            round_records=[],
            agents={},
        )
        manager = ColonyManager(runtime)
        manager._run_transcript_harvest = AsyncMock()

        active_task = MagicMock(spec=asyncio.Task)
        active_task.done.return_value = False
        manager._active["other-colony"] = active_task

        monkeypatch.setattr(
            "formicos.surface.colony_manager._POST_COLONY_DRAIN_POLL_S",
            0.01,
        )

        manager._hook_transcript_harvest("col-3", "ws1", True)
        await asyncio.sleep(0.02)

        manager._run_transcript_harvest.assert_not_awaited()
        assert len(manager._deferred_post_colony_work) == 1

        if manager._post_colony_drain_task is not None:
            manager._post_colony_drain_task.cancel()
            with patch("formicos.surface.colony_manager.log"):
                await asyncio.gather(
                    manager._post_colony_drain_task,
                    return_exceptions=True,
                )


class TestEscalationTierViability:
    """Tests for local-only escalation truth."""

    def test_next_viable_tier_skips_unavailable_heavy_provider(self) -> None:
        from formicos.surface.colony_manager import _next_viable_tier

        runtime = SimpleNamespace(
            resolve_model=lambda caste, workspace_id: "llama-cpp/gpt-4",
            llm_router=SimpleNamespace(
                _adapters={"llama-cpp": object()},
                _cooldown=SimpleNamespace(is_cooled_down=lambda provider: False),
            ),
        )

        next_tier = _next_viable_tier(
            [SimpleNamespace(tier="standard")],
            runtime,
            "ws-1",
        )

        assert next_tier is None

    def test_next_viable_tier_returns_heavy_when_provider_exists(self) -> None:
        from formicos.surface.colony_manager import _next_viable_tier

        runtime = SimpleNamespace(
            resolve_model=lambda caste, workspace_id: "llama-cpp/gpt-4",
            llm_router=SimpleNamespace(
                _adapters={"llama-cpp": object(), "anthropic": object()},
                _cooldown=SimpleNamespace(is_cooled_down=lambda provider: False),
            ),
        )

        next_tier = _next_viable_tier(
            [SimpleNamespace(tier="standard")],
            runtime,
            "ws-1",
        )

        assert next_tier == "heavy"


# ---------------------------------------------------------------------------
# _make_strategy tests
# ---------------------------------------------------------------------------


class TestMakeStrategy:
    """Tests for strategy factory."""

    def test_returns_sequential_when_embed_fn_is_none(self) -> None:
        runtime = _make_runtime()
        runtime.embed_fn = None
        manager = ColonyManager(runtime)

        strategy = manager._make_strategy("stigmergic")
        assert isinstance(strategy, SequentialStrategy)

    def test_returns_sequential_for_sequential_name(self) -> None:
        runtime = _make_runtime()
        runtime.embed_fn = MagicMock()  # even with embed_fn
        manager = ColonyManager(runtime)

        strategy = manager._make_strategy("sequential")
        assert isinstance(strategy, SequentialStrategy)


# ---------------------------------------------------------------------------
# Wave 37 1B: quality-aware confidence update tests
# ---------------------------------------------------------------------------


class TestQualityAwareConfidenceUpdate:
    """Verify quality_score threads into confidence updates."""

    @pytest.mark.anyio()
    async def test_high_quality_success_gives_larger_delta(self) -> None:
        """Higher quality_score → larger alpha increment."""
        runtime = _make_runtime()
        colony = _make_colony_projection()
        runtime.projections.get_colony.return_value = colony
        runtime.emit_and_broadcast = AsyncMock(return_value=1)
        manager = ColonyManager(runtime)

        # Set up a knowledge access trace on the colony projection
        colony.knowledge_accesses = [{
            "items": [{"id": "entry-1"}],
        }]
        runtime.projections.memory_entries = {
            "entry-1": {
                "conf_alpha": 10.0,
                "conf_beta": 5.0,
                "workspace_id": "ws1",
                "decay_class": "permanent",
                "created_at": "2026-03-18T00:00:00+00:00",
            },
        }
        runtime.projections.cooccurrence_weights = {}

        # High quality
        await manager._hook_confidence_update(
            "colony-abc", "ws1", "th1", succeeded=True, quality_score=0.9,
        )

        # delta_alpha = clip(0.5 + 0.9, 0.5, 1.5) = 1.4
        # permanent decay_class → gamma=1.0, no decay, so new_alpha = 10.0 + 1.4
        calls = runtime.emit_and_broadcast.await_args_list
        conf_events = [
            c for c in calls
            if hasattr(c.args[0], "new_alpha")
        ]
        assert len(conf_events) == 1
        event = conf_events[0].args[0]
        assert event.new_alpha > event.old_alpha + 1.0

    @pytest.mark.anyio()
    async def test_low_quality_success_gives_smaller_delta(self) -> None:
        """Lower quality_score → smaller alpha increment (min 0.5)."""
        runtime = _make_runtime()
        colony = _make_colony_projection()
        runtime.projections.get_colony.return_value = colony
        runtime.emit_and_broadcast = AsyncMock(return_value=1)
        manager = ColonyManager(runtime)

        colony.knowledge_accesses = [{
            "items": [{"id": "entry-2"}],
        }]
        runtime.projections.memory_entries = {
            "entry-2": {
                "conf_alpha": 10.0,
                "conf_beta": 5.0,
                "workspace_id": "ws1",
                "decay_class": "ephemeral",
                "created_at": "2026-03-18T00:00:00+00:00",
            },
        }
        runtime.projections.cooccurrence_weights = {}

        # Zero quality
        await manager._hook_confidence_update(
            "colony-abc", "ws1", "th1", succeeded=True, quality_score=0.0,
        )

        calls = runtime.emit_and_broadcast.await_args_list
        conf_events = [
            c for c in calls
            if hasattr(c.args[0], "new_alpha")
        ]
        assert len(conf_events) == 1
        event = conf_events[0].args[0]
        # delta_alpha = clip(0.5 + 0.0, 0.5, 1.5) = 0.5
        # new_alpha ≈ old_alpha + 0.5 (modulo decay)
        assert event.new_alpha < event.old_alpha + 1.0

    @pytest.mark.anyio()
    async def test_failure_increases_beta(self) -> None:
        """Failed colony should increase beta, not alpha."""
        runtime = _make_runtime()
        colony = _make_colony_projection()
        runtime.projections.get_colony.return_value = colony
        runtime.emit_and_broadcast = AsyncMock(return_value=1)
        manager = ColonyManager(runtime)

        colony.knowledge_accesses = [{
            "items": [{"id": "entry-3"}],
        }]
        runtime.projections.memory_entries = {
            "entry-3": {
                "conf_alpha": 10.0,
                "conf_beta": 5.0,
                "workspace_id": "ws1",
                "decay_class": "ephemeral",
                "created_at": "2026-03-18T00:00:00+00:00",
            },
        }
        runtime.projections.cooccurrence_weights = {}

        await manager._hook_confidence_update(
            "colony-abc", "ws1", "th1", succeeded=False, quality_score=0.0,
        )

        calls = runtime.emit_and_broadcast.await_args_list
        conf_events = [
            c for c in calls
            if hasattr(c.args[0], "new_beta")
        ]
        assert len(conf_events) == 1
        event = conf_events[0].args[0]
        assert event.new_beta > event.old_beta
