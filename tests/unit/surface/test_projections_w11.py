"""Projection handler tests for Wave 11 Phase A events."""

from __future__ import annotations

from datetime import UTC, datetime

from formicos.core.events import (
    ColonyNamed,
    ColonyRedirected,
    ColonySpawned,
    ColonyTemplateCreated,
    ColonyTemplateUsed,
    SkillConfidenceUpdated,
    WorkspaceCreated,
    WorkspaceConfigSnapshot,
)
from formicos.core.types import CasteSlot
from formicos.surface.projections import ProjectionStore, TemplateProjection


_NOW = datetime(2026, 3, 14, tzinfo=UTC)


def _seeded_store() -> ProjectionStore:
    """Return a ProjectionStore with a workspace and colony for testing."""
    store = ProjectionStore()
    store.apply(WorkspaceCreated(
        seq=1, timestamp=_NOW, address="ws-1",
        name="ws-1",
        config=WorkspaceConfigSnapshot(budget=5.0, strategy="stigmergic"),
    ))
    store.apply(ColonySpawned(
        seq=3, timestamp=_NOW, address="ws-1/thread-1/colony-abc",
        thread_id="thread-1", task="test task",
        castes=[CasteSlot(caste="coder")], model_assignments={},
        strategy="stigmergic", max_rounds=10, budget_limit=2.0,
    ))
    return store


class TestColonyTemplateCreatedProjection:
    def test_template_added_to_store(self) -> None:
        store = ProjectionStore()
        store.apply(ColonyTemplateCreated(
            seq=10, timestamp=_NOW, address="ws-1",
            template_id="tmpl-001",
            name="Code Review",
            description="Coder + Reviewer pair.",
            castes=[CasteSlot(caste="coder"), CasteSlot(caste="reviewer")],
            strategy="stigmergic",
            source_colony_id="colony-abc",
        ))
        assert "tmpl-001" in store.templates
        tmpl = store.templates["tmpl-001"]
        assert tmpl.name == "Code Review"
        assert tmpl.castes == [CasteSlot(caste="coder"), CasteSlot(caste="reviewer")]
        assert tmpl.strategy == "stigmergic"
        assert tmpl.source_colony_id == "colony-abc"
        assert tmpl.use_count == 0

    def test_template_without_source_colony(self) -> None:
        store = ProjectionStore()
        store.apply(ColonyTemplateCreated(
            seq=11, timestamp=_NOW, address="ws-1",
            template_id="tmpl-002",
            name="Research",
            description="Solo researcher.",
            castes=[CasteSlot(caste="researcher")],
            strategy="sequential",
        ))
        tmpl = store.templates["tmpl-002"]
        assert tmpl.source_colony_id is None


class TestColonyTemplateUsedProjection:
    def test_use_count_incremented(self) -> None:
        store = ProjectionStore()
        store.apply(ColonyTemplateCreated(
            seq=10, timestamp=_NOW, address="ws-1",
            template_id="tmpl-001",
            name="Code Review",
            description="Pair.",
            castes=[CasteSlot(caste="coder"), CasteSlot(caste="reviewer")],
            strategy="stigmergic",
        ))
        assert store.templates["tmpl-001"].use_count == 0

        store.apply(ColonyTemplateUsed(
            seq=11, timestamp=_NOW, address="ws-1",
            template_id="tmpl-001",
            colony_id="colony-xyz",
        ))
        assert store.templates["tmpl-001"].use_count == 1

        store.apply(ColonyTemplateUsed(
            seq=12, timestamp=_NOW, address="ws-1",
            template_id="tmpl-001",
            colony_id="colony-abc",
        ))
        assert store.templates["tmpl-001"].use_count == 2

    def test_use_unknown_template_no_crash(self) -> None:
        store = ProjectionStore()
        store.apply(ColonyTemplateUsed(
            seq=11, timestamp=_NOW, address="ws-1",
            template_id="tmpl-nonexistent",
            colony_id="colony-xyz",
        ))
        assert "tmpl-nonexistent" not in store.templates


class TestColonyNamedProjection:
    def test_display_name_set(self) -> None:
        store = _seeded_store()
        colony = store.colonies.get("colony-abc")
        assert colony is not None
        assert colony.display_name is None

        store.apply(ColonyNamed(
            seq=20, timestamp=_NOW, address="ws-1/thread-1/colony-abc",
            colony_id="colony-abc",
            display_name="Phoenix Rising",
            named_by="queen",
        ))
        assert colony.display_name == "Phoenix Rising"

    def test_display_name_overwritten(self) -> None:
        store = _seeded_store()
        store.apply(ColonyNamed(
            seq=20, timestamp=_NOW, address="ws-1/thread-1/colony-abc",
            colony_id="colony-abc",
            display_name="Old Name",
            named_by="queen",
        ))
        store.apply(ColonyNamed(
            seq=21, timestamp=_NOW, address="ws-1/thread-1/colony-abc",
            colony_id="colony-abc",
            display_name="New Name",
            named_by="operator",
        ))
        assert store.colonies["colony-abc"].display_name == "New Name"

    def test_named_unknown_colony_no_crash(self) -> None:
        store = ProjectionStore()
        store.apply(ColonyNamed(
            seq=20, timestamp=_NOW, address="ws-1/thread-1/colony-missing",
            colony_id="colony-missing",
            display_name="Ghost",
            named_by="queen",
        ))
        assert "colony-missing" not in store.colonies


class TestSkillConfidenceUpdatedProjection:
    def test_no_state_change(self) -> None:
        store = _seeded_store()
        colony = store.colonies["colony-abc"]
        cost_before = colony.cost
        status_before = colony.status

        store.apply(SkillConfidenceUpdated(
            seq=30, timestamp=_NOW, address="ws-1/thread-1/colony-abc",
            colony_id="colony-abc",
            skills_updated=5,
            colony_succeeded=True,
        ))

        # Audit trail only — no projection state change
        assert colony.cost == cost_before
        assert colony.status == status_before


class TestReplayWithNewEvents:
    def test_replay_includes_new_events(self) -> None:
        """All 4 new event types survive a full replay cycle."""
        store = ProjectionStore()
        events = [
            WorkspaceCreated(
                seq=1, timestamp=_NOW, address="ws-1",
                name="ws-1",
                config=WorkspaceConfigSnapshot(budget=5.0, strategy="stigmergic"),
            ),
            ColonySpawned(
                seq=2, timestamp=_NOW, address="ws-1/thread-1/colony-abc",
                thread_id="thread-1", task="task",
                castes=[CasteSlot(caste="coder")], model_assignments={},
                strategy="stigmergic", max_rounds=10, budget_limit=2.0,
            ),
            ColonyTemplateCreated(
                seq=3, timestamp=_NOW, address="ws-1",
                template_id="tmpl-001", name="Review",
                description="Pair.", castes=[CasteSlot(caste="coder"), CasteSlot(caste="reviewer")],
                strategy="stigmergic",
            ),
            ColonyTemplateUsed(
                seq=4, timestamp=_NOW, address="ws-1",
                template_id="tmpl-001", colony_id="colony-abc",
            ),
            ColonyNamed(
                seq=5, timestamp=_NOW, address="ws-1/thread-1/colony-abc",
                colony_id="colony-abc", display_name="Alpha",
                named_by="queen",
            ),
            SkillConfidenceUpdated(
                seq=6, timestamp=_NOW, address="ws-1/thread-1/colony-abc",
                colony_id="colony-abc", skills_updated=2,
                colony_succeeded=True,
            ),
        ]
        store.replay(events)

        assert store.templates["tmpl-001"].use_count == 1
        assert store.colonies["colony-abc"].display_name == "Alpha"
        assert store.last_seq == 6


# ---------------------------------------------------------------------------
# Wave 19 — ColonyRedirected projection tests (ADR-032)
# ---------------------------------------------------------------------------


class TestColonyRedirectedProjection:
    def test_active_goal_initialized_on_spawn(self) -> None:
        store = _seeded_store()
        colony = store.colonies["colony-abc"]
        assert colony.active_goal == "test task"

    def test_redirect_updates_active_goal(self) -> None:
        store = _seeded_store()
        store.apply(ColonyRedirected(
            seq=10, timestamp=_NOW,
            address="ws-1/thread-1/colony-abc",
            colony_id="colony-abc",
            redirect_index=0,
            original_goal="test task",
            new_goal="fix the bug instead",
            reason="colony was going off-track",
            trigger="queen_inspection",
            round_at_redirect=3,
        ))
        colony = store.colonies["colony-abc"]
        assert colony.active_goal == "fix the bug instead"

    def test_redirect_appends_to_history(self) -> None:
        store = _seeded_store()
        store.apply(ColonyRedirected(
            seq=10, timestamp=_NOW,
            address="ws-1/thread-1/colony-abc",
            colony_id="colony-abc",
            redirect_index=0,
            original_goal="test task",
            new_goal="new goal",
            reason="needed change",
            trigger="governance_alert",
            round_at_redirect=5,
        ))
        colony = store.colonies["colony-abc"]
        assert len(colony.redirect_history) == 1
        entry = colony.redirect_history[0]
        assert entry["redirect_index"] == 0
        assert entry["new_goal"] == "new goal"
        assert entry["trigger"] == "governance_alert"
        assert entry["round"] == 5

    def test_redirect_appends_boundary(self) -> None:
        store = _seeded_store()
        store.apply(ColonyRedirected(
            seq=10, timestamp=_NOW,
            address="ws-1/thread-1/colony-abc",
            colony_id="colony-abc",
            redirect_index=0,
            original_goal="test task",
            new_goal="new goal",
            reason="reason",
            trigger="queen_inspection",
            round_at_redirect=4,
        ))
        colony = store.colonies["colony-abc"]
        assert colony.redirect_boundaries == [4]

    def test_redirect_unknown_colony_no_crash(self) -> None:
        store = ProjectionStore()
        store.apply(ColonyRedirected(
            seq=10, timestamp=_NOW,
            address="ws-1/thread-1/colony-missing",
            colony_id="colony-missing",
            redirect_index=0,
            original_goal="task",
            new_goal="new",
            reason="reason",
            trigger="queen_inspection",
            round_at_redirect=1,
        ))
        assert "colony-missing" not in store.colonies
