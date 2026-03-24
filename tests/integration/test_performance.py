"""Performance benchmarks — Key public-path timing (Wave 36 C3).

Validates that critical operations complete within practical bounds.
Thresholds are generous to avoid flaky failures on normal dev machines.
"""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime

import pytest

from formicos.core.events import (
    ColonyCompleted,
    ColonySpawned,
    MemoryEntryCreated,
    RoundCompleted,
    RoundStarted,
    WorkspaceConfigChanged,
    WorkspaceConfigSnapshot,
    WorkspaceCreated,
)
from formicos.core.types import CasteSlot
from formicos.surface.proactive_intelligence import generate_briefing
from formicos.surface.projections import ProjectionStore


def _now() -> datetime:
    return datetime.now(tz=UTC)


_seq = 0


def _next_seq() -> int:
    global _seq
    _seq += 1
    return _seq


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _build_large_store(
    num_entries: int = 50,
    num_colonies: int = 10,
    num_rounds_per_colony: int = 5,
) -> tuple[ProjectionStore, str]:
    """Build a projection store with realistic data volume."""
    store = ProjectionStore()
    ws_id = "perf-ws"

    store.apply(WorkspaceCreated(
        seq=_next_seq(), timestamp=_now(), address=ws_id,
        name="Performance Test", config=WorkspaceConfigSnapshot(budget=10.0, strategy="stigmergic"),
    ))

    # Seed entries
    for i in range(num_entries):
        store.apply(MemoryEntryCreated(
            seq=_next_seq(), timestamp=_now(), address=ws_id,
            entry={
                "id": f"entry-{i}",
                "category": "skill" if i % 2 == 0 else "experience",
                "sub_type": "technique" if i % 2 == 0 else "learning",
                "title": f"Knowledge entry {i}",
                "content": f"Content for entry {i} with enough text to be realistic.",
                "domains": [f"domain-{i % 5}", f"domain-{(i + 1) % 5}"],
                "decay_class": ["ephemeral", "stable", "permanent"][i % 3],
                "status": ["verified", "candidate", "observed"][i % 3],
                "conf_alpha": 5.0 + (i % 20),
                "conf_beta": 2.0 + (i % 10),
                "workspace_id": ws_id,
                "source_colony_id": f"colony-{i % num_colonies}",
                "source_round": 1,
                "polarity": "positive" if i % 3 != 2 else "negative",
                "prediction_error_count": i % 4,
                "created_at": _now().isoformat(),
            },
            workspace_id=ws_id,
        ))

    # Spawn and complete colonies
    for c in range(num_colonies):
        cid = f"colony-{c}"
        address = f"{ws_id}/main/{cid}"
        store.apply(ColonySpawned(
            seq=_next_seq(), timestamp=_now(), address=address,
            thread_id="main", task=f"Task for colony {c}",
            castes=[CasteSlot(caste="coder"), CasteSlot(caste="reviewer")],
            model_assignments={}, strategy="stigmergic" if c % 2 == 0 else "sequential",
            max_rounds=num_rounds_per_colony, budget_limit=5.0,
        ))

        for r in range(1, num_rounds_per_colony + 1):
            store.apply(RoundStarted(
                seq=_next_seq(), timestamp=_now(), address=cid,
                colony_id=cid, round_number=r,
            ))
            store.apply(RoundCompleted(
                seq=_next_seq(), timestamp=_now(), address=cid,
                colony_id=cid, round_number=r,
                convergence=0.3 + (r * 0.1), cost=0.05, duration_ms=200,
            ))

        store.apply(ColonyCompleted(
            seq=_next_seq(), timestamp=_now(), address=cid,
            colony_id=cid,
            summary=f"Colony {c} completed its task successfully.",
            skills_extracted=2,
        ))

    return store, ws_id


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestBriefingPerformance:
    """Proactive briefing generation timing."""

    def test_briefing_under_200ms_with_50_entries(self) -> None:
        """Briefing generation with 50 entries completes under 200ms."""
        store, ws_id = _build_large_store(num_entries=50, num_colonies=10)

        start = time.perf_counter()
        briefing = generate_briefing(ws_id, store)
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert briefing.total_entries >= 50
        assert elapsed_ms < 200, f"Briefing took {elapsed_ms:.1f}ms (limit: 200ms)"

    def test_briefing_under_500ms_with_200_entries(self) -> None:
        """Briefing generation with 200 entries completes under 500ms."""
        store, ws_id = _build_large_store(num_entries=200, num_colonies=20)

        start = time.perf_counter()
        briefing = generate_briefing(ws_id, store)
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert briefing.total_entries >= 200
        assert elapsed_ms < 500, f"Briefing took {elapsed_ms:.1f}ms (limit: 500ms)"


class TestProjectionReplayPerformance:
    """Projection replay and event application timing."""

    def test_replay_100_events_under_100ms(self) -> None:
        """Replaying 100 events into a fresh store completes under 100ms."""
        # Build events first
        events = []
        ws_id = "replay-ws"
        events.append(WorkspaceCreated(
            seq=1, timestamp=_now(), address=ws_id,
            name="Replay Test", config=WorkspaceConfigSnapshot(budget=5.0, strategy="stigmergic"),
        ))
        for i in range(99):
            events.append(MemoryEntryCreated(
                seq=i + 2, timestamp=_now(), address=ws_id,
                entry={
                    "id": f"replay-entry-{i}",
                    "category": "skill",
                    "sub_type": "technique",
                    "title": f"Entry {i}",
                    "content": f"Content {i}",
                    "domains": ["test"],
                    "status": "verified",
                    "conf_alpha": 10.0,
                    "conf_beta": 3.0,
                    "workspace_id": ws_id,
                    "source_colony_id": "col-1",
                    "polarity": "positive",
                    "created_at": _now().isoformat(),
                },
                workspace_id=ws_id,
            ))

        store = ProjectionStore()
        start = time.perf_counter()
        for e in events:
            store.apply(e)
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert len(store.memory_entries) == 99
        assert elapsed_ms < 100, f"Replay took {elapsed_ms:.1f}ms (limit: 100ms)"

    def test_colony_outcome_generated_during_replay(self) -> None:
        """ColonyOutcome is correctly computed during event replay."""
        store, ws_id = _build_large_store(num_entries=10, num_colonies=5)

        assert len(store.colony_outcomes) == 5
        for outcome in store.colony_outcomes.values():
            assert outcome.workspace_id == ws_id
            assert outcome.succeeded is True
            assert outcome.total_rounds == 5
            assert outcome.total_cost > 0


class TestDemoWorkspaceCreationPerformance:
    """Demo workspace creation timing."""

    def test_demo_workspace_seeding_under_500ms(self) -> None:
        """Seeding a demo workspace with template entries completes under 500ms."""
        from pathlib import Path

        import yaml

        template_path = (
            Path(__file__).resolve().parents[2]
            / "config" / "templates" / "demo-workspace.yaml"
        )
        if not template_path.exists():
            pytest.skip("Demo template not available")

        raw = yaml.safe_load(template_path.read_text(encoding="utf-8"))
        entries = raw.get("seeded_entries", [])

        store = ProjectionStore()
        ws_id = "demo-perf"

        start = time.perf_counter()

        store.apply(WorkspaceCreated(
            seq=1, timestamp=_now(), address=ws_id,
            name="Demo Perf Test",
            config=WorkspaceConfigSnapshot(budget=5.0, strategy="stigmergic"),
        ))

        policy = raw.get("maintenance_policy")
        if policy:
            store.apply(WorkspaceConfigChanged(
                seq=2, timestamp=_now(), address=ws_id,
                workspace_id=ws_id, field="maintenance_policy",
                old_value=None, new_value=json.dumps(policy),
            ))

        for i, entry_def in enumerate(entries):
            conf = entry_def.get("confidence", {})
            store.apply(MemoryEntryCreated(
                seq=i + 3, timestamp=_now(), address=ws_id,
                entry={
                    "id": entry_def.get("entry_id", f"perf-{i}"),
                    "category": entry_def.get("category", "skill"),
                    "sub_type": entry_def.get("sub_type", "technique"),
                    "title": entry_def.get("title", ""),
                    "content": entry_def.get("content", ""),
                    "domains": entry_def.get("domains", []),
                    "decay_class": entry_def.get("decay_class", "ephemeral"),
                    "status": entry_def.get("status", "observed"),
                    "conf_alpha": conf.get("alpha", 5.0),
                    "conf_beta": conf.get("beta", 2.0),
                    "workspace_id": ws_id,
                    "source_colony_id": "demo-seed",
                    "polarity": "positive",
                    "created_at": _now().isoformat(),
                },
                workspace_id=ws_id,
            ))

        elapsed_ms = (time.perf_counter() - start) * 1000

        assert len(store.memory_entries) == len(entries)
        assert elapsed_ms < 500, f"Demo seeding took {elapsed_ms:.1f}ms (limit: 500ms)"

    def test_briefing_after_seeding_under_100ms(self) -> None:
        """Briefing generation on a freshly-seeded demo workspace under 100ms."""
        from pathlib import Path

        import yaml

        template_path = (
            Path(__file__).resolve().parents[2]
            / "config" / "templates" / "demo-workspace.yaml"
        )
        if not template_path.exists():
            pytest.skip("Demo template not available")

        # Seed workspace first (not timed)
        raw = yaml.safe_load(template_path.read_text(encoding="utf-8"))
        store = ProjectionStore()
        ws_id = "briefing-perf"
        store.apply(WorkspaceCreated(
            seq=1, timestamp=_now(), address=ws_id,
            name="Briefing Perf", config=WorkspaceConfigSnapshot(budget=5.0, strategy="stigmergic"),
        ))
        for i, entry_def in enumerate(raw.get("seeded_entries", [])):
            conf = entry_def.get("confidence", {})
            store.apply(MemoryEntryCreated(
                seq=i + 2, timestamp=_now(), address=ws_id,
                entry={
                    "id": entry_def.get("entry_id", f"bp-{i}"),
                    "category": entry_def.get("category", "skill"),
                    "sub_type": entry_def.get("sub_type", "technique"),
                    "title": entry_def.get("title", ""),
                    "content": entry_def.get("content", ""),
                    "domains": entry_def.get("domains", []),
                    "status": entry_def.get("status", "observed"),
                    "conf_alpha": conf.get("alpha", 5.0),
                    "conf_beta": conf.get("beta", 2.0),
                    "workspace_id": ws_id,
                    "source_colony_id": "demo-seed",
                    "polarity": "positive",
                    "created_at": _now().isoformat(),
                },
                workspace_id=ws_id,
            ))

        # Time the briefing
        start = time.perf_counter()
        briefing = generate_briefing(ws_id, store)
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert briefing.total_entries >= 8
        assert elapsed_ms < 100, f"Briefing took {elapsed_ms:.1f}ms (limit: 100ms)"
