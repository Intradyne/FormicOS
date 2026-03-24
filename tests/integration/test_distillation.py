"""Integration test — Knowledge distillation pipeline (Wave 35, ADR-045 D2).

Dense co-occurrence cluster → maintenance flags candidates → archivist colony
dispatched → KnowledgeDistilled event.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from formicos.core.events import KnowledgeDistilled
from formicos.core.types import AutonomyLevel, MaintenancePolicy
from formicos.surface.projections import CooccurrenceEntry, ProjectionStore
from formicos.surface.self_maintenance import MaintenanceDispatcher


def _now_iso() -> str:
    return datetime.now(tz=UTC).isoformat()


def _make_entry(entry_id: str, **overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": entry_id,
        "workspace_id": "ws-1",
        "title": f"Entry {entry_id}",
        "entry_type": "skill",
        "status": "verified",
        "conf_alpha": 10.0,
        "conf_beta": 5.0,
        "domains": ["testing"],
        "polarity": "positive",
        "decay_class": "stable",
        "prediction_error_count": 0,
        "created_at": _now_iso(),
        "summary": f"Summary {entry_id}",
        "content_preview": f"Content {entry_id}",
        "source_colony_id": "col-1",
        "score": 0.7,
    }
    base.update(overrides)
    return base


def _build_dense_cluster(
    entry_ids: list[str],
    weight: float = 4.0,
) -> dict[tuple[str, str], CooccurrenceEntry]:
    """Build fully-connected co-occurrence graph above distillation threshold."""
    from formicos.surface.projections import cooccurrence_key

    weights: dict[tuple[str, str], CooccurrenceEntry] = {}
    for i, a in enumerate(entry_ids):
        for b in entry_ids[i + 1 :]:
            key = cooccurrence_key(a, b)
            weights[key] = CooccurrenceEntry(
                weight=weight,
                last_reinforced=_now_iso(),
                reinforcement_count=5,
            )
    return weights


class TestDistillationPipeline:
    """Integration: dense cluster → candidates → archivist dispatch."""

    def test_find_distillation_candidates(self) -> None:
        """Maintenance identifies dense co-occurrence clusters."""
        from formicos.surface.maintenance import _find_distillation_candidates

        entry_ids = [f"mem-{i}" for i in range(6)]
        cooc = _build_dense_cluster(entry_ids, weight=4.0)

        runtime = MagicMock()
        runtime.projections.cooccurrence_weights = cooc
        runtime.projections.memory_entries = {
            eid: _make_entry(eid) for eid in entry_ids
        }

        candidates = _find_distillation_candidates(runtime)
        assert len(candidates) >= 1, "Should find at least 1 distillation cluster"
        # Cluster should contain all 6 entries
        assert set(candidates[0]) == set(entry_ids)

    def test_sparse_cluster_not_candidate(self) -> None:
        """Cluster with < 5 entries is not a distillation candidate."""
        from formicos.surface.maintenance import _find_distillation_candidates

        entry_ids = [f"mem-{i}" for i in range(3)]
        cooc = _build_dense_cluster(entry_ids, weight=4.0)

        runtime = MagicMock()
        runtime.projections.cooccurrence_weights = cooc

        candidates = _find_distillation_candidates(runtime)
        assert candidates == [], "Fewer than 5 entries should not qualify"

    def test_low_weight_cluster_not_candidate(self) -> None:
        """Cluster with avg weight <= 3.0 is not a distillation candidate."""
        from formicos.surface.maintenance import _find_distillation_candidates

        entry_ids = [f"mem-{i}" for i in range(6)]
        # Weight 2.5 is above the 2.0 edge threshold but avg will be 2.5 <= 3.0
        cooc = _build_dense_cluster(entry_ids, weight=2.5)

        runtime = MagicMock()
        runtime.projections.cooccurrence_weights = cooc

        candidates = _find_distillation_candidates(runtime)
        assert candidates == [], "Avg weight <= 3.0 should not qualify"

    @pytest.mark.asyncio
    async def test_distillation_dispatch_with_policy(self) -> None:
        """Archivist colony spawns when distillation is in auto_actions."""
        entry_ids = [f"mem-{i}" for i in range(6)]

        policy = MaintenancePolicy(
            autonomy_level=AutonomyLevel.auto_notify,
            auto_actions=["distillation"],
            daily_maintenance_budget=5.0,
        )

        runtime = MagicMock()
        runtime.spawn_colony = AsyncMock(return_value="colony-distill-1")

        ws = MagicMock()
        ws.config = {"maintenance_policy": json.dumps(policy.model_dump())}
        runtime.projections.workspaces = {"ws-1": ws}
        runtime.projections.colonies = {}
        runtime.projections.distillation_candidates = [entry_ids]
        runtime.projections.memory_entries = {
            eid: _make_entry(eid) for eid in entry_ids
        }

        dispatcher = MaintenanceDispatcher(runtime)
        dispatched = await dispatcher.evaluate_distillation("ws-1")

        assert len(dispatched) == 1
        assert dispatched[0] == "colony-distill-1"
        # Verify archivist caste
        call_kwargs = runtime.spawn_colony.call_args
        if call_kwargs.kwargs:
            assert call_kwargs.kwargs.get("castes") is not None
        runtime.spawn_colony.assert_called_once()

    @pytest.mark.asyncio
    async def test_distillation_blocked_without_opt_in(self) -> None:
        """auto_notify without 'distillation' in auto_actions blocks dispatch."""
        entry_ids = [f"mem-{i}" for i in range(6)]

        policy = MaintenancePolicy(
            autonomy_level=AutonomyLevel.auto_notify,
            auto_actions=["contradiction"],  # NOT distillation
        )

        runtime = MagicMock()
        ws = MagicMock()
        ws.config = {"maintenance_policy": json.dumps(policy.model_dump())}
        runtime.projections.workspaces = {"ws-1": ws}
        runtime.projections.colonies = {}
        runtime.projections.distillation_candidates = [entry_ids]

        dispatcher = MaintenanceDispatcher(runtime)
        dispatched = await dispatcher.evaluate_distillation("ws-1")

        assert dispatched == []

    def test_knowledge_distilled_event_round_trip(self) -> None:
        """KnowledgeDistilled serializes and deserializes correctly."""
        event = KnowledgeDistilled(
            seq=100, timestamp=datetime.now(tz=UTC),
            address="ws-1/t-1/col-1",
            distilled_entry_id="mem-distilled-1",
            source_entry_ids=["mem-1", "mem-2", "mem-3", "mem-4", "mem-5"],
            workspace_id="ws-1",
            cluster_avg_weight=4.2,
        )
        data = event.model_dump()
        restored = KnowledgeDistilled.model_validate(data)
        assert restored.distilled_entry_id == "mem-distilled-1"
        assert restored.source_entry_ids == ["mem-1", "mem-2", "mem-3", "mem-4", "mem-5"]
        assert restored.cluster_avg_weight == 4.2
