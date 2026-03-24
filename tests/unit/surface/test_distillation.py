"""Tests for knowledge distillation pipeline (Wave 35)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock

import pytest

from formicos.core.types import AutonomyLevel, MaintenancePolicy
from formicos.surface.projections import CooccurrenceEntry, ProjectionStore
from formicos.surface.self_maintenance import MaintenanceDispatcher


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@dataclass
class _FakeWorkspace:
    id: str
    config: dict[str, Any] = field(default_factory=dict)


@dataclass
class _FakeColonyProjection:
    id: str
    workspace_id: str
    status: str = "running"
    tags: list[str] = field(default_factory=list)


@dataclass
class _FakeProjections:
    workspaces: dict[str, _FakeWorkspace] = field(default_factory=dict)
    colonies: dict[str, _FakeColonyProjection] = field(default_factory=dict)
    memory_entries: dict[str, dict[str, Any]] = field(default_factory=dict)
    cooccurrence_weights: dict[tuple[str, str], CooccurrenceEntry] = field(
        default_factory=dict,
    )
    distillation_candidates: list[list[str]] = field(default_factory=list)


def _make_runtime(
    *,
    policy: MaintenancePolicy | None = None,
    candidates: list[list[str]] | None = None,
    entries: dict[str, dict[str, Any]] | None = None,
) -> Any:
    ws = _FakeWorkspace(id="ws-1")
    if policy is not None:
        ws.config["maintenance_policy"] = policy.model_dump()

    projections = _FakeProjections(workspaces={"ws-1": ws})
    if candidates is not None:
        projections.distillation_candidates = candidates
    if entries is not None:
        projections.memory_entries = entries

    # Build cooccurrence weights for distillation cluster
    now = datetime.now(UTC).isoformat()
    if candidates:
        for cluster in candidates:
            for i, a in enumerate(cluster):
                for b in cluster[i + 1:]:
                    key = (min(a, b), max(a, b))
                    projections.cooccurrence_weights[key] = CooccurrenceEntry(
                        weight=5.0, last_reinforced=now, reinforcement_count=10,
                    )

    runtime = type("Runtime", (), {
        "projections": projections,
        "spawn_colony": AsyncMock(return_value="distill-col"),
    })()
    return runtime


# ---------------------------------------------------------------------------
# Distillation dispatch tests
# ---------------------------------------------------------------------------


class TestDistillationDispatch:
    @pytest.mark.asyncio
    async def test_distillation_dispatches_when_policy_allows(self) -> None:
        """Distillation candidate flagged -> archivist colony spawns."""
        cluster = [f"e{i}" for i in range(5)]
        entries = {
            eid: {"id": eid, "title": f"Entry {eid}", "content": "test", "sub_type": "learning"}
            for eid in cluster
        }
        policy = MaintenancePolicy(
            autonomy_level=AutonomyLevel.auto_notify,
            auto_actions=["distillation"],
            daily_maintenance_budget=5.0,
        )
        runtime = _make_runtime(
            policy=policy, candidates=[cluster], entries=entries,
        )
        dispatcher = MaintenanceDispatcher(runtime)
        result = await dispatcher.evaluate_distillation("ws-1")
        assert len(result) == 1
        runtime.spawn_colony.assert_called_once()
        call_kwargs = runtime.spawn_colony.call_args
        assert call_kwargs.kwargs.get("castes")[0].caste == "archivist"
        assert "Synthesize" in call_kwargs.kwargs.get("task", "")

    @pytest.mark.asyncio
    async def test_distillation_blocked_at_suggest_level(self) -> None:
        """Distillation candidate flagged -> no colony (when policy is suggest)."""
        cluster = [f"e{i}" for i in range(5)]
        policy = MaintenancePolicy(autonomy_level=AutonomyLevel.suggest)
        runtime = _make_runtime(policy=policy, candidates=[cluster])
        dispatcher = MaintenanceDispatcher(runtime)
        result = await dispatcher.evaluate_distillation("ws-1")
        assert result == []

    @pytest.mark.asyncio
    async def test_distillation_requires_opt_in_at_auto_notify(self) -> None:
        """auto_notify without distillation in auto_actions: no dispatch."""
        cluster = [f"e{i}" for i in range(5)]
        policy = MaintenancePolicy(
            autonomy_level=AutonomyLevel.auto_notify,
            auto_actions=["contradiction"],  # no distillation
        )
        runtime = _make_runtime(policy=policy, candidates=[cluster])
        dispatcher = MaintenanceDispatcher(runtime)
        result = await dispatcher.evaluate_distillation("ws-1")
        assert result == []

    @pytest.mark.asyncio
    async def test_distillation_at_autonomous_no_opt_in_needed(self) -> None:
        """autonomous level: distillation dispatches without explicit opt-in."""
        cluster = [f"e{i}" for i in range(5)]
        entries = {
            eid: {"id": eid, "title": f"Entry {eid}", "content": "test"}
            for eid in cluster
        }
        policy = MaintenancePolicy(
            autonomy_level=AutonomyLevel.autonomous,
            daily_maintenance_budget=5.0,
        )
        runtime = _make_runtime(
            policy=policy, candidates=[cluster], entries=entries,
        )
        dispatcher = MaintenanceDispatcher(runtime)
        result = await dispatcher.evaluate_distillation("ws-1")
        assert len(result) == 1


# ---------------------------------------------------------------------------
# KnowledgeDistilled projection tests
# ---------------------------------------------------------------------------


class TestKnowledgeDistilledProjection:
    def _make_event(
        self,
        distilled_id: str = "mem-distilled",
        source_ids: list[str] | None = None,
    ) -> Any:
        from formicos.core.events import KnowledgeDistilled
        return KnowledgeDistilled(
            seq=100,
            timestamp=datetime.now(UTC),
            address="ws-1",
            distilled_entry_id=distilled_id,
            source_entry_ids=source_ids or ["src-1", "src-2", "src-3"],
            workspace_id="ws-1",
            cluster_avg_weight=4.5,
            distillation_strategy="archivist_synthesis",
        )

    def test_upgrades_existing_entry(self) -> None:
        """KnowledgeDistilled -> existing entry upgraded to stable + elevated alpha."""
        store = ProjectionStore()
        # Pre-populate: archivist's MemoryEntryCreated already ran
        store.memory_entries["mem-distilled"] = {
            "id": "mem-distilled",
            "title": "Synthesized knowledge",
            "content": "Comprehensive synthesis of the cluster",
            "domains": ["testing"],
            "sub_type": "learning",
            "decay_class": "ephemeral",
            "conf_alpha": 5.0,
            "conf_beta": 5.0,
        }
        # Source entries
        for sid in ["src-1", "src-2", "src-3"]:
            store.memory_entries[sid] = {
                "id": sid,
                "conf_alpha": 10.0,
                "conf_beta": 5.0,
            }

        event = self._make_event()
        store.apply(event)

        entry = store.memory_entries["mem-distilled"]
        assert entry["decay_class"] == "stable"
        assert entry["conf_alpha"] == min(30.0 / 2, 30.0)  # sum(10,10,10)/2 = 15
        assert entry["merged_from"] == ["src-1", "src-2", "src-3"]
        assert entry["distillation_strategy"] == "archivist_synthesis"
        # Content preserved from archivist
        assert entry["content"] == "Comprehensive synthesis of the cluster"
        assert entry["domains"] == ["testing"]
        assert entry["sub_type"] == "learning"

    def test_source_entries_marked(self) -> None:
        """KnowledgeDistilled -> source entries marked with distilled_into."""
        store = ProjectionStore()
        store.memory_entries["mem-distilled"] = {
            "id": "mem-distilled",
            "conf_alpha": 5.0,
            "conf_beta": 5.0,
        }
        for sid in ["src-1", "src-2"]:
            store.memory_entries[sid] = {
                "id": sid,
                "conf_alpha": 8.0,
                "conf_beta": 5.0,
            }

        event = self._make_event(source_ids=["src-1", "src-2"])
        store.apply(event)

        for sid in ["src-1", "src-2"]:
            assert store.memory_entries[sid]["distilled_into"] == "mem-distilled"

    def test_idempotent_double_apply(self) -> None:
        """Double-apply KnowledgeDistilled -> idempotent."""
        store = ProjectionStore()
        store.memory_entries["mem-distilled"] = {
            "id": "mem-distilled",
            "conf_alpha": 5.0,
            "conf_beta": 5.0,
            "decay_class": "ephemeral",
        }
        for sid in ["src-1", "src-2"]:
            store.memory_entries[sid] = {
                "id": sid,
                "conf_alpha": 10.0,
                "conf_beta": 5.0,
            }

        event = self._make_event(source_ids=["src-1", "src-2"])
        store.apply(event)
        store.apply(event)  # second apply

        entry = store.memory_entries["mem-distilled"]
        assert entry["decay_class"] == "stable"
        assert entry["conf_alpha"] == 10.0  # min(20/2, 30) = 10
        assert entry["merged_from"] == ["src-1", "src-2"]

    def test_alpha_capped_at_30(self) -> None:
        """Distilled entry alpha = min(sum(source_alphas)/2, 30.0)."""
        store = ProjectionStore()
        store.memory_entries["mem-distilled"] = {
            "id": "mem-distilled",
            "conf_alpha": 5.0,
            "conf_beta": 5.0,
        }
        # High-alpha sources
        sources = [f"src-{i}" for i in range(5)]
        for sid in sources:
            store.memory_entries[sid] = {
                "id": sid,
                "conf_alpha": 20.0,  # total = 100, /2 = 50, capped at 30
                "conf_beta": 5.0,
            }

        event = self._make_event(source_ids=sources)
        store.apply(event)

        assert store.memory_entries["mem-distilled"]["conf_alpha"] == 30.0

    def test_skip_if_distilled_entry_missing(self) -> None:
        """If distilled entry doesn't exist (replay order), skip gracefully."""
        store = ProjectionStore()
        for sid in ["src-1", "src-2"]:
            store.memory_entries[sid] = {
                "id": sid,
                "conf_alpha": 10.0,
                "conf_beta": 5.0,
            }

        event = self._make_event(source_ids=["src-1", "src-2"])
        store.apply(event)  # should not raise

        # Source entries should NOT be modified since distilled entry is missing
        assert "distilled_into" not in store.memory_entries["src-1"]

    def test_content_preserved_after_upgrade(self) -> None:
        """Archivist's synthesis content/domains/sub_type preserved after upgrade."""
        store = ProjectionStore()
        store.memory_entries["mem-distilled"] = {
            "id": "mem-distilled",
            "title": "Archivist synthesis",
            "content": "Detailed synthesis content from archivist colony",
            "domains": ["python", "testing"],
            "sub_type": "pattern",
            "entry_type": "skill",
            "conf_alpha": 5.0,
            "conf_beta": 5.0,
            "decay_class": "ephemeral",
        }
        store.memory_entries["src-1"] = {"id": "src-1", "conf_alpha": 8.0, "conf_beta": 5.0}

        event = self._make_event(source_ids=["src-1"])
        store.apply(event)

        entry = store.memory_entries["mem-distilled"]
        # These should be preserved from archivist's extraction
        assert entry["title"] == "Archivist synthesis"
        assert entry["content"] == "Detailed synthesis content from archivist colony"
        assert entry["domains"] == ["python", "testing"]
        assert entry["sub_type"] == "pattern"
        assert entry["entry_type"] == "skill"
        # These should be upgraded
        assert entry["decay_class"] == "stable"
        assert entry["conf_alpha"] == 4.0  # min(8/2, 30) = 4
