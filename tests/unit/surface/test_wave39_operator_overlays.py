"""Wave 39 Team 2: Operator overlay and annotation projection tests.

Verifies:
- Replay rebuilds pinned/muted/invalidated overlay state
- Overlay actions are reversible (pin/unpin, mute/unmute, invalidate/reinstate)
- Annotations accumulate and survive replay
- Config overrides are recorded per workspace
- Overlays do NOT mutate shared Beta confidence truth
- Retrieval respects overlay state
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest

from formicos.core.events import (
    ConfigSuggestionOverridden,
    KnowledgeEntryAnnotated,
    KnowledgeEntryOperatorAction,
    MemoryConfidenceUpdated,
    MemoryEntryCreated,
)
from formicos.surface.projections import (
    OperatorOverlayState,
    ProjectionStore,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TS = datetime(2026, 3, 19, 12, 0, tzinfo=timezone.utc)


def _operator_action(
    entry_id: str,
    action: str,
    workspace_id: str = "ws-1",
    seq: int = 1,
) -> KnowledgeEntryOperatorAction:
    return KnowledgeEntryOperatorAction(
        seq=seq,
        timestamp=_TS,
        address=f"{workspace_id}/{entry_id}",
        entry_id=entry_id,
        workspace_id=workspace_id,
        action=action,
        actor="operator",
    )


def _annotation(
    entry_id: str,
    text: str,
    tag: str = "",
    seq: int = 1,
) -> KnowledgeEntryAnnotated:
    return KnowledgeEntryAnnotated(
        seq=seq,
        timestamp=_TS,
        address=f"ws-1/{entry_id}",
        entry_id=entry_id,
        workspace_id="ws-1",
        annotation_text=text,
        tag=tag,
        actor="operator",
    )


def _config_override(
    workspace_id: str = "ws-1",
    category: str = "strategy",
    seq: int = 1,
) -> ConfigSuggestionOverridden:
    return ConfigSuggestionOverridden(
        seq=seq,
        timestamp=_TS,
        address=workspace_id,
        workspace_id=workspace_id,
        suggestion_category=category,
        original_config={"strategy": "stigmergic"},
        overridden_config={"strategy": "direct"},
        reason="Operator preference.",
        actor="operator",
    )


def _memory_entry_created(
    entry_id: str,
    workspace_id: str = "ws-1",
    seq: int = 0,
) -> MemoryEntryCreated:
    return MemoryEntryCreated(
        seq=seq,
        timestamp=_TS,
        address=f"{workspace_id}/th-1/col-1",
        workspace_id=workspace_id,
        entry={
            "id": entry_id,
            "workspace_id": workspace_id,
            "thread_id": "th-1",
            "colony_id": "col-1",
            "entry_type": "skill",
            "title": f"Entry {entry_id}",
            "content": f"Content for {entry_id}",
            "domains": ["python"],
            "conf_alpha": 5.0,
            "conf_beta": 5.0,
            "status": "candidate",
        },
    )


# ---------------------------------------------------------------------------
# Tests: Overlay state rebuild via replay
# ---------------------------------------------------------------------------


class TestOverlayReplay:
    """Verify overlay state rebuilds correctly from event replay."""

    def test_pin_survives_replay(self) -> None:
        store = ProjectionStore()
        store.apply(_operator_action("e1", "pin"))
        assert "e1" in store.operator_overlays.pinned_entries

    def test_unpin_removes_pin(self) -> None:
        store = ProjectionStore()
        store.apply(_operator_action("e1", "pin", seq=1))
        store.apply(_operator_action("e1", "unpin", seq=2))
        assert "e1" not in store.operator_overlays.pinned_entries

    def test_mute_survives_replay(self) -> None:
        store = ProjectionStore()
        store.apply(_operator_action("e1", "mute"))
        assert "e1" in store.operator_overlays.muted_entries

    def test_unmute_removes_mute(self) -> None:
        store = ProjectionStore()
        store.apply(_operator_action("e1", "mute", seq=1))
        store.apply(_operator_action("e1", "unmute", seq=2))
        assert "e1" not in store.operator_overlays.muted_entries

    def test_invalidate_survives_replay(self) -> None:
        store = ProjectionStore()
        store.apply(_operator_action("e1", "invalidate"))
        assert "e1" in store.operator_overlays.invalidated_entries

    def test_reinstate_removes_invalidation(self) -> None:
        store = ProjectionStore()
        store.apply(_operator_action("e1", "invalidate", seq=1))
        store.apply(_operator_action("e1", "reinstate", seq=2))
        assert "e1" not in store.operator_overlays.invalidated_entries

    def test_multiple_entries_independent(self) -> None:
        store = ProjectionStore()
        store.apply(_operator_action("e1", "pin", seq=1))
        store.apply(_operator_action("e2", "mute", seq=2))
        store.apply(_operator_action("e3", "invalidate", seq=3))
        assert "e1" in store.operator_overlays.pinned_entries
        assert "e2" in store.operator_overlays.muted_entries
        assert "e3" in store.operator_overlays.invalidated_entries

    def test_full_replay_rebuilds_state(self) -> None:
        """Replay a sequence of actions and verify final state."""
        events = [
            _operator_action("e1", "pin", seq=1),
            _operator_action("e2", "mute", seq=2),
            _operator_action("e3", "invalidate", seq=3),
            _operator_action("e1", "unpin", seq=4),
            _operator_action("e2", "unmute", seq=5),
            _operator_action("e4", "pin", seq=6),
        ]
        store = ProjectionStore()
        store.replay(events)  # type: ignore[arg-type]

        assert "e1" not in store.operator_overlays.pinned_entries
        assert "e4" in store.operator_overlays.pinned_entries
        assert "e2" not in store.operator_overlays.muted_entries
        assert "e3" in store.operator_overlays.invalidated_entries


# ---------------------------------------------------------------------------
# Tests: Annotations
# ---------------------------------------------------------------------------


class TestAnnotationProjection:
    """Verify annotation projection accumulates and replays correctly."""

    def test_annotation_recorded(self) -> None:
        store = ProjectionStore()
        store.apply(_annotation("e1", "Important for compliance."))
        annotations = store.operator_overlays.annotations.get("e1", [])
        assert len(annotations) == 1
        assert annotations[0].annotation_text == "Important for compliance."

    def test_multiple_annotations_on_same_entry(self) -> None:
        store = ProjectionStore()
        store.apply(_annotation("e1", "First note.", seq=1))
        store.apply(_annotation("e1", "Second note.", tag="review", seq=2))
        annotations = store.operator_overlays.annotations.get("e1", [])
        assert len(annotations) == 2
        assert annotations[0].annotation_text == "First note."
        assert annotations[1].tag == "review"

    def test_annotations_on_different_entries_independent(self) -> None:
        store = ProjectionStore()
        store.apply(_annotation("e1", "Note for e1.", seq=1))
        store.apply(_annotation("e2", "Note for e2.", seq=2))
        assert len(store.operator_overlays.annotations.get("e1", [])) == 1
        assert len(store.operator_overlays.annotations.get("e2", [])) == 1

    def test_annotation_survives_replay(self) -> None:
        events = [
            _annotation("e1", "Compliance note.", tag="compliance", seq=1),
            _annotation("e1", "Review note.", tag="review", seq=2),
        ]
        store = ProjectionStore()
        store.replay(events)  # type: ignore[arg-type]
        annotations = store.operator_overlays.annotations["e1"]
        assert len(annotations) == 2


# ---------------------------------------------------------------------------
# Tests: Config overrides
# ---------------------------------------------------------------------------


class TestConfigOverrideProjection:
    """Verify config override history is recorded per workspace."""

    def test_override_recorded(self) -> None:
        store = ProjectionStore()
        store.apply(_config_override(workspace_id="ws-1"))
        overrides = store.operator_overlays.config_overrides.get("ws-1", [])
        assert len(overrides) == 1
        assert overrides[0].suggestion_category == "strategy"
        assert overrides[0].original_config == {"strategy": "stigmergic"}
        assert overrides[0].overridden_config == {"strategy": "direct"}

    def test_multiple_overrides_accumulate(self) -> None:
        store = ProjectionStore()
        store.apply(_config_override(workspace_id="ws-1", category="strategy", seq=1))
        store.apply(_config_override(workspace_id="ws-1", category="model_tier", seq=2))
        overrides = store.operator_overlays.config_overrides.get("ws-1", [])
        assert len(overrides) == 2

    def test_overrides_per_workspace(self) -> None:
        store = ProjectionStore()
        store.apply(_config_override(workspace_id="ws-1", seq=1))
        store.apply(_config_override(workspace_id="ws-2", seq=2))
        assert len(store.operator_overlays.config_overrides.get("ws-1", [])) == 1
        assert len(store.operator_overlays.config_overrides.get("ws-2", [])) == 1


# ---------------------------------------------------------------------------
# Tests: Local-first — no shared confidence mutation
# ---------------------------------------------------------------------------


class TestNoConfidenceMutation:
    """Verify operator actions do NOT silently mutate shared Beta posteriors."""

    def test_pin_does_not_change_confidence(self) -> None:
        """Pin action must not emit or imply MemoryConfidenceUpdated."""
        store = ProjectionStore()
        # Create an entry first
        store.apply(_memory_entry_created("e1", seq=0))
        entry_before = dict(store.memory_entries.get("e1", {}))
        alpha_before = entry_before.get("conf_alpha", 5.0)
        beta_before = entry_before.get("conf_beta", 5.0)

        # Pin the entry
        store.apply(_operator_action("e1", "pin", seq=1))

        entry_after = store.memory_entries.get("e1", {})
        assert entry_after.get("conf_alpha", 5.0) == alpha_before
        assert entry_after.get("conf_beta", 5.0) == beta_before

    def test_mute_does_not_change_confidence(self) -> None:
        store = ProjectionStore()
        store.apply(_memory_entry_created("e1", seq=0))
        entry_before = dict(store.memory_entries.get("e1", {}))

        store.apply(_operator_action("e1", "mute", seq=1))

        entry_after = store.memory_entries.get("e1", {})
        assert entry_after.get("conf_alpha") == entry_before.get("conf_alpha")
        assert entry_after.get("conf_beta") == entry_before.get("conf_beta")

    def test_invalidate_does_not_change_confidence(self) -> None:
        store = ProjectionStore()
        store.apply(_memory_entry_created("e1", seq=0))
        entry_before = dict(store.memory_entries.get("e1", {}))

        store.apply(_operator_action("e1", "invalidate", seq=1))

        entry_after = store.memory_entries.get("e1", {})
        assert entry_after.get("conf_alpha") == entry_before.get("conf_alpha")
        assert entry_after.get("conf_beta") == entry_before.get("conf_beta")

    def test_overlay_state_separate_from_entry(self) -> None:
        """The canonical knowledge entry remains unmodified by overlays."""
        store = ProjectionStore()
        store.apply(_memory_entry_created("e1", seq=0))
        store.apply(_operator_action("e1", "pin", seq=1))
        store.apply(_operator_action("e1", "mute", seq=2))

        entry = store.memory_entries.get("e1", {})
        # No overlay keys leaked into the entry
        assert "_pinned" not in entry
        assert "_muted" not in entry
        assert "_invalidated" not in entry


# ---------------------------------------------------------------------------
# Tests: Retrieval overlay behavior
# ---------------------------------------------------------------------------


class TestRetrievalOverlays:
    """Verify KnowledgeCatalog respects operator overlays."""

    def _make_catalog_with_overlays(
        self,
        muted: set[str] | None = None,
        invalidated: set[str] | None = None,
        pinned: set[str] | None = None,
    ) -> Any:
        """Create a KnowledgeCatalog with pre-configured overlays."""
        from formicos.surface.knowledge_catalog import KnowledgeCatalog
        store = ProjectionStore()
        if muted:
            store.operator_overlays.muted_entries = muted
        if invalidated:
            store.operator_overlays.invalidated_entries = invalidated
        if pinned:
            store.operator_overlays.pinned_entries = pinned
        return KnowledgeCatalog(
            memory_store=None,
            vector_port=None,
            skill_collection="test",
            projections=store,
        )

    def test_muted_entries_filtered(self) -> None:
        catalog = self._make_catalog_with_overlays(muted={"e1", "e3"})
        items = [
            {"id": "e1", "title": "Entry 1"},
            {"id": "e2", "title": "Entry 2"},
            {"id": "e3", "title": "Entry 3"},
        ]
        filtered = catalog._apply_operator_overlays(items)
        ids = [i["id"] for i in filtered]
        assert "e1" not in ids
        assert "e2" in ids
        assert "e3" not in ids

    def test_invalidated_entries_filtered(self) -> None:
        catalog = self._make_catalog_with_overlays(invalidated={"e2"})
        items = [
            {"id": "e1", "title": "Entry 1"},
            {"id": "e2", "title": "Entry 2"},
        ]
        filtered = catalog._apply_operator_overlays(items)
        ids = [i["id"] for i in filtered]
        assert "e1" in ids
        assert "e2" not in ids

    def test_pinned_entries_get_boost(self) -> None:
        catalog = self._make_catalog_with_overlays(pinned={"e1"})
        items = [
            {"id": "e1", "title": "Entry 1"},
            {"id": "e2", "title": "Entry 2"},
        ]
        filtered = catalog._apply_operator_overlays(items)
        e1 = next(i for i in filtered if i["id"] == "e1")
        assert e1.get("_pinned") is True
        assert e1.get("_pin_boost") == 1.0

    def test_non_pinned_entries_have_no_boost(self) -> None:
        catalog = self._make_catalog_with_overlays(pinned={"e1"})
        items = [
            {"id": "e1", "title": "Entry 1"},
            {"id": "e2", "title": "Entry 2"},
        ]
        filtered = catalog._apply_operator_overlays(items)
        e2 = next(i for i in filtered if i["id"] == "e2")
        assert "_pin_boost" not in e2

    def test_no_projections_passes_through(self) -> None:
        """With no projection store, overlays are no-op."""
        from formicos.surface.knowledge_catalog import KnowledgeCatalog
        catalog = KnowledgeCatalog(
            memory_store=None,
            vector_port=None,
            skill_collection="test",
            projections=None,
        )
        items = [{"id": "e1"}, {"id": "e2"}]
        filtered = catalog._apply_operator_overlays(items)
        assert len(filtered) == 2

    def test_combined_overlays(self) -> None:
        """Muted, invalidated, and pinned overlays compose correctly."""
        catalog = self._make_catalog_with_overlays(
            muted={"e2"},
            invalidated={"e3"},
            pinned={"e1"},
        )
        items = [
            {"id": "e1", "title": "Entry 1"},
            {"id": "e2", "title": "Entry 2"},
            {"id": "e3", "title": "Entry 3"},
            {"id": "e4", "title": "Entry 4"},
        ]
        filtered = catalog._apply_operator_overlays(items)
        ids = [i["id"] for i in filtered]
        assert ids == ["e1", "e4"]
        assert filtered[0].get("_pinned") is True
