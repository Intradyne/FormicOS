"""Wave 30 Track C tests — event serialization, legacy removal, confidence math."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from formicos.core.events import (
    ColonySpawned,
    MemoryConfidenceUpdated,
    WorkflowStepCompleted,
    WorkflowStepDefined,
    deserialize,
    serialize,
)


# ---------------------------------------------------------------------------
# Round-trip serialization: MemoryConfidenceUpdated
# ---------------------------------------------------------------------------


class TestMemoryConfidenceUpdatedRoundTrip:
    def test_serialize_deserialize(self) -> None:
        evt = MemoryConfidenceUpdated(
            seq=1,
            timestamp=datetime(2026, 3, 17, tzinfo=UTC),
            address="ws-1/t-1/col-1",
            entry_id="mem-1",
            colony_id="col-1",
            colony_succeeded=True,
            old_alpha=5.0,
            old_beta=5.0,
            new_alpha=6.0,
            new_beta=5.0,
            new_confidence=6.0 / 11.0,
            workspace_id="ws-1",
            thread_id="t-1",
            reason="colony_outcome",
        )
        raw = serialize(evt)
        restored = deserialize(raw)
        assert restored.type == "MemoryConfidenceUpdated"
        assert restored.entry_id == "mem-1"  # type: ignore[attr-defined]
        assert restored.new_alpha == 6.0  # type: ignore[attr-defined]

    def test_archival_decay_fields(self) -> None:
        evt = MemoryConfidenceUpdated(
            seq=2,
            timestamp=datetime(2026, 3, 17, tzinfo=UTC),
            address="ws-1",
            entry_id="mem-2",
            colony_id="",
            colony_succeeded=True,
            old_alpha=10.0,
            old_beta=5.0,
            new_alpha=8.0,
            new_beta=6.0,
            new_confidence=8.0 / 14.0,
            workspace_id="ws-1",
            thread_id="",
            reason="archival_decay",
        )
        raw = serialize(evt)
        restored = deserialize(raw)
        assert restored.type == "MemoryConfidenceUpdated"
        assert restored.new_alpha == 8.0  # type: ignore[attr-defined]
        assert restored.new_beta == 6.0  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Round-trip serialization: WorkflowStepDefined / WorkflowStepCompleted
# ---------------------------------------------------------------------------


class TestWorkflowStepEventsRoundTrip:
    def test_step_defined(self) -> None:
        from formicos.core.events import WorkflowStep

        evt = WorkflowStepDefined(
            seq=1,
            timestamp=datetime(2026, 3, 17, tzinfo=UTC),
            address="ws-1/t-1",
            workspace_id="ws-1",
            thread_id="t-1",
            step=WorkflowStep(
                step_index=0,
                description="Research phase",
                expected_outputs=["report", "summary"],
            ),
        )
        raw = serialize(evt)
        restored = deserialize(raw)
        assert restored.type == "WorkflowStepDefined"
        assert restored.step.step_index == 0  # type: ignore[attr-defined]
        assert restored.step.description == "Research phase"  # type: ignore[attr-defined]

    def test_step_completed(self) -> None:
        evt = WorkflowStepCompleted(
            seq=2,
            timestamp=datetime(2026, 3, 17, tzinfo=UTC),
            address="ws-1/t-1/col-1",
            workspace_id="ws-1",
            thread_id="t-1",
            step_index=0,
            colony_id="col-1",
            success=True,
            artifacts_produced=["report"],
        )
        raw = serialize(evt)
        restored = deserialize(raw)
        assert restored.type == "WorkflowStepCompleted"
        assert restored.step_index == 0  # type: ignore[attr-defined]
        assert restored.success is True  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# ColonySpawned backward-compat: step_index defaults to -1
# ---------------------------------------------------------------------------


class TestColonySpawnedStepIndex:
    def test_step_index_default(self) -> None:
        """step_index defaults to -1 for colonies not associated with a workflow step."""
        evt = ColonySpawned(
            seq=1,
            timestamp=datetime(2026, 3, 17, tzinfo=UTC),
            address="ws-1/t-1",
            thread_id="t-1",
            task="Do something",
            castes=[{"caste": "coder", "tier": "standard", "count": 1}],
            model_assignments={"coder": "openai/gpt-4"},
            strategy="stigmergic",
            max_rounds=5,
            budget_limit=1.0,
        )
        assert evt.step_index == -1

    def test_step_index_explicit(self) -> None:
        evt = ColonySpawned(
            seq=2,
            timestamp=datetime(2026, 3, 17, tzinfo=UTC),
            address="ws-1/t-1",
            thread_id="t-1",
            task="Step 0 task",
            castes=[{"caste": "coder", "tier": "standard", "count": 1}],
            model_assignments={"coder": "openai/gpt-4"},
            strategy="stigmergic",
            max_rounds=5,
            budget_limit=1.0,
            step_index=0,
        )
        assert evt.step_index == 0


# ---------------------------------------------------------------------------
# Archival decay math: alpha * 0.8, beta * 1.2
# ---------------------------------------------------------------------------


class TestArchivalDecayMath:
    def test_decay_factors(self) -> None:
        """Archival decay should shrink alpha and grow beta."""
        alpha, beta = 10.0, 5.0
        new_alpha = alpha * 0.8
        new_beta = beta * 1.2
        assert new_alpha == pytest.approx(8.0)
        assert new_beta == pytest.approx(6.0)
        # Posterior mean should decrease
        old_mean = alpha / (alpha + beta)
        new_mean = new_alpha / (new_alpha + new_beta)
        assert new_mean < old_mean

    def test_decay_preserves_positivity(self) -> None:
        alpha, beta = 1.0, 1.0
        new_alpha = alpha * 0.8
        new_beta = beta * 1.2
        assert new_alpha > 0
        assert new_beta > 0


# ---------------------------------------------------------------------------
# Contradiction handler skips entries with empty polarity
# ---------------------------------------------------------------------------


class TestContradictionSkipsEmptyPolarity:
    @pytest.mark.asyncio
    async def test_entries_with_empty_polarity_excluded(self) -> None:
        """Entries with neutral/empty polarity should be excluded from contradiction scan."""
        from formicos.surface.maintenance import make_contradiction_handler

        runtime = MagicMock()
        runtime.projections.memory_entries = {
            "a": {
                "id": "a", "status": "verified", "polarity": "positive",
                "domains": ["python"], "confidence": 0.8,
            },
            "b": {
                "id": "b", "status": "verified", "polarity": "",
                "domains": ["python"], "confidence": 0.7,
            },
            "c": {
                "id": "c", "status": "verified", "polarity": "neutral",
                "domains": ["python"], "confidence": 0.6,
            },
        }
        handler = make_contradiction_handler(runtime)
        # The inner function filters out empty/neutral polarity entries,
        # so only entry "a" remains — no pair to contradict.
        result = await handler("scan", {})
        assert "0 pair(s) flagged" in result


# ---------------------------------------------------------------------------
# Legacy deletion verification
# ---------------------------------------------------------------------------


class TestLegacyDeletion:
    def test_skill_lifecycle_deleted(self) -> None:
        import importlib
        with pytest.raises(ModuleNotFoundError):
            importlib.import_module("formicos.surface.skill_lifecycle")

    def test_skill_dedup_deleted(self) -> None:
        import importlib
        with pytest.raises(ModuleNotFoundError):
            importlib.import_module("formicos.adapters.skill_dedup")

    @pytest.mark.asyncio
    async def test_crystallize_skills_returns_zero(self) -> None:
        """_crystallize_skills is gutted and always returns 0."""
        from formicos.surface.colony_manager import ColonyManager

        runtime = MagicMock()
        mgr = ColonyManager(runtime)
        result = await mgr._crystallize_skills("col-1", "task", "summary", 3)
        assert result == 0
