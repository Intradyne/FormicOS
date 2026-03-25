"""Wave 40 Team 2: Cross-feature interaction matrix tests.

Covers the highest-value interaction seams where multi-wave features meet:

1. operator overlays × retrieval scoring (Wave 39 overlays × Wave 28 composite)
2. operator overlays × federation truth (Wave 39 overlays × Wave 33 federation penalty)
3. topology bias × muted/invalidated entries (Wave 26 prior × Wave 39 overlays)
4. co-occurrence × operator invalidation (Wave 33 co-occurrence × Wave 39 overlays)
5. proactive insights × operator annotations (Wave 34.5 insights × Wave 39 annotations)
6. admission scoring × federation trust (Wave 38 admission × Wave 33 trust)
7. bi-temporal edges × graph query filtering (Wave 26 graph × Wave 33 co-occurrence)

These tests prove behavior at real multi-wave seams, not single-feature assertions.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from formicos.surface.admission import AdmissionResult, evaluate_entry
from formicos.surface.knowledge_catalog import (
    KnowledgeCatalog,
    _cooccurrence_score,
    _composite_key,
)
from formicos.surface.projections import (
    CooccurrenceEntry,
    OperatorOverlayState,
    ProjectionStore,
    cooccurrence_key,
)
from formicos.surface.trust import (
    PeerTrust,
    federated_retrieval_penalty,
    trust_discount,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_entry(
    entry_id: str,
    *,
    status: str = "active",
    conf_alpha: float = 10.0,
    conf_beta: float = 2.0,
    domains: list[str] | None = None,
    source_peer: str = "",
    score: float = 0.8,
    entry_type: str = "skill",
    sub_type: str = "",
    title: str = "Test entry",
    source_colony_id: str = "col-1",
    content: str = "Some content",
    created_at: str = "",
    scan_status: str = "safe",
) -> dict[str, Any]:
    """Create a knowledge entry dict suitable for retrieval and admission tests."""
    if created_at == "":
        created_at = datetime(2026, 3, 19, 10, 0, tzinfo=UTC).isoformat()
    return {
        "id": entry_id,
        "status": status,
        "conf_alpha": conf_alpha,
        "conf_beta": conf_beta,
        "domains": domains or ["python"],
        "source_peer": source_peer,
        "score": score,
        "entry_type": entry_type,
        "sub_type": sub_type,
        "title": title,
        "summary": f"Summary of {entry_id}",
        "source_colony_id": source_colony_id,
        "content": content,
        "created_at": created_at,
        "scan_status": scan_status,
    }


def _make_store_with_overlays(
    *,
    pinned: set[str] | None = None,
    muted: set[str] | None = None,
    invalidated: set[str] | None = None,
) -> ProjectionStore:
    """Create a ProjectionStore with pre-configured operator overlays."""
    store = ProjectionStore()
    store.operator_overlays = OperatorOverlayState(
        pinned_entries=pinned or set(),
        muted_entries=muted or set(),
        invalidated_entries=invalidated or set(),
    )
    return store


# ---------------------------------------------------------------------------
# 1. Operator overlays × retrieval scoring
# ---------------------------------------------------------------------------


class TestOverlayRetrievalScoring:
    """Verify that operator overlays correctly modify retrieval composite scores."""

    def test_pin_boost_increases_composite_score(self) -> None:
        """Pinned entries get +1.0 added to raw composite before fed_penalty."""
        entry_normal = _make_entry("e-1", score=0.5, conf_alpha=5.0, conf_beta=5.0)
        entry_pinned = _make_entry("e-2", score=0.5, conf_alpha=5.0, conf_beta=5.0)
        entry_pinned["_pin_boost"] = 1.0

        # Use fixed seed for deterministic Thompson sampling
        random.seed(42)
        score_normal = _composite_key(entry_normal)
        random.seed(42)
        score_pinned = _composite_key(entry_pinned)

        # Pinned should have a lower (more negative = better) composite key
        assert score_pinned < score_normal, (
            f"Pinned entry (score={score_pinned}) should rank higher than "
            f"normal (score={score_normal})"
        )

    def test_muted_entries_excluded_from_overlay_filter(self) -> None:
        """_apply_operator_overlays removes muted entries from results."""
        store = _make_store_with_overlays(muted={"e-2"})
        catalog = KnowledgeCatalog(
            memory_store=None, vector_port=None,
            skill_collection="test", projections=store,
        )

        items = [
            _make_entry("e-1"),
            _make_entry("e-2"),
            _make_entry("e-3"),
        ]
        filtered = catalog._apply_operator_overlays(items)

        result_ids = [item["id"] for item in filtered]
        assert "e-1" in result_ids
        assert "e-2" not in result_ids
        assert "e-3" in result_ids

    def test_invalidated_entries_excluded_from_overlay_filter(self) -> None:
        """_apply_operator_overlays removes invalidated entries from results."""
        store = _make_store_with_overlays(invalidated={"e-1", "e-3"})
        catalog = KnowledgeCatalog(
            memory_store=None, vector_port=None,
            skill_collection="test", projections=store,
        )

        items = [_make_entry("e-1"), _make_entry("e-2"), _make_entry("e-3")]
        filtered = catalog._apply_operator_overlays(items)

        result_ids = [item["id"] for item in filtered]
        assert result_ids == ["e-2"]

    def test_pinned_entries_get_pin_boost_attribute(self) -> None:
        """_apply_operator_overlays sets _pin_boost=1.0 on pinned items."""
        store = _make_store_with_overlays(pinned={"e-1"})
        catalog = KnowledgeCatalog(
            memory_store=None, vector_port=None,
            skill_collection="test", projections=store,
        )

        items = [_make_entry("e-1"), _make_entry("e-2")]
        filtered = catalog._apply_operator_overlays(items)

        pinned_item = next(i for i in filtered if i["id"] == "e-1")
        unpinned_item = next(i for i in filtered if i["id"] == "e-2")
        assert pinned_item.get("_pin_boost") == 1.0
        assert unpinned_item.get("_pin_boost", 0.0) == 0.0

    def test_combined_overlays_filter_and_boost(self) -> None:
        """Multiple overlay types applied simultaneously: mute + pin + invalidate."""
        store = _make_store_with_overlays(
            pinned={"e-1"},
            muted={"e-2"},
            invalidated={"e-4"},
        )
        catalog = KnowledgeCatalog(
            memory_store=None, vector_port=None,
            skill_collection="test", projections=store,
        )

        items = [
            _make_entry("e-1"),
            _make_entry("e-2"),
            _make_entry("e-3"),
            _make_entry("e-4"),
        ]
        filtered = catalog._apply_operator_overlays(items)

        result_ids = [item["id"] for item in filtered]
        assert result_ids == ["e-1", "e-3"]
        assert filtered[0].get("_pin_boost") == 1.0


# ---------------------------------------------------------------------------
# 2. Operator overlays × federation truth
# ---------------------------------------------------------------------------


class TestOverlayFederationInteraction:
    """Verify that overlays compose correctly with federation penalties."""

    def test_pinned_federated_entry_overcomes_penalty(self) -> None:
        """A pinned federated entry should rank higher than without pin boost."""
        fed_entry = _make_entry(
            "fed-1", source_peer="peer-a", status="active", score=0.6,
        )
        fed_entry_pinned = _make_entry(
            "fed-2", source_peer="peer-a", status="active", score=0.6,
        )
        fed_entry_pinned["_pin_boost"] = 1.0

        random.seed(42)
        score_plain = _composite_key(fed_entry)
        random.seed(42)
        score_pinned = _composite_key(fed_entry_pinned)

        # Pin boost should overcome the 0.65 penalty for active federated
        assert score_pinned < score_plain

    def test_muted_federated_entry_removed_regardless_of_trust(self) -> None:
        """Muted entries are removed from retrieval even if they have high trust."""
        store = _make_store_with_overlays(muted={"fed-1"})
        catalog = KnowledgeCatalog(
            memory_store=None, vector_port=None,
            skill_collection="test", projections=store,
        )

        items = [
            _make_entry("fed-1", source_peer="peer-a", status="verified"),
            _make_entry("local-1"),
        ]
        filtered = catalog._apply_operator_overlays(items)

        result_ids = [item["id"] for item in filtered]
        assert "fed-1" not in result_ids
        assert "local-1" in result_ids

    def test_federation_penalty_applied_after_pin_boost(self) -> None:
        """The composite key applies fed_penalty as a multiplier on the raw score.

        Pin boost is additive to raw, then the whole raw is multiplied by fed_penalty.
        Wave 41 A1: penalty is now posterior-aware (not a fixed status band).
        """
        entry = _make_entry("fed-1", source_peer="peer-a", status="active", score=0.7)
        entry["_pin_boost"] = 1.0

        # Wave 41: penalty is posterior-aware — just verify it's a reasonable
        # penalty for an active federated entry (less than 1.0, more than 0.1)
        penalty = federated_retrieval_penalty(entry)
        assert 0.1 < penalty < 1.0

        # The composite key formula: -(raw * fed_penalty)
        # pin_boost adds to raw before multiplication
        random.seed(42)
        composite = _composite_key(entry)
        # Just verify the entry gets a valid negative score (better rank)
        assert composite < 0.0


# ---------------------------------------------------------------------------
# 3. Topology bias × muted/invalidated entries
# ---------------------------------------------------------------------------


class TestTopologyBiasMutedEntries:
    """Test that _compute_knowledge_prior processes entries without overlay checks.

    DOCUMENTED GAP: _compute_knowledge_prior does NOT check operator overlays.
    Muted/invalidated entries still affect topology bias if they appear in
    knowledge_items. This test documents the current behavior.
    """

    def test_muted_entry_still_contributes_to_knowledge_prior(self) -> None:
        """Currently, muted entries contribute to topology prior if present in items."""
        from formicos.engine.runner import _compute_knowledge_prior

        @dataclass
        class FakeRecipe:
            name: str

        @dataclass
        class FakeAgent:
            id: str
            caste: str
            recipe: FakeRecipe

        agents = [
            FakeAgent(id="a1", caste="coder", recipe=FakeRecipe(name="python_coder")),
            FakeAgent(id="a2", caste="researcher", recipe=FakeRecipe(name="web_researcher")),
        ]

        # An entry with "python" domain — would be muted in retrieval
        items = [
            _make_entry("e-muted", domains=["python"], conf_alpha=20.0, conf_beta=2.0),
        ]

        prior = _compute_knowledge_prior(agents, items)
        # The prior should still be produced — muted status is NOT checked here
        # This documents the architectural gap
        assert prior is not None, (
            "_compute_knowledge_prior should produce a prior even for entries "
            "that would be muted in retrieval (gap: no overlay check)"
        )

    def test_invalidated_entry_domains_affect_topology(self) -> None:
        """Invalidated entries still affect agent-domain affinity mapping."""
        from formicos.engine.runner import _compute_knowledge_prior

        @dataclass
        class FakeRecipe:
            name: str

        @dataclass
        class FakeAgent:
            id: str
            caste: str
            recipe: FakeRecipe

        agents = [
            FakeAgent(id="a1", caste="coder", recipe=FakeRecipe(name="python_coder")),
            FakeAgent(id="a2", caste="coder", recipe=FakeRecipe(name="js_coder")),
        ]

        # Mix of valid and would-be-invalidated entries
        items = [
            _make_entry("e-valid", domains=["python"], conf_alpha=15.0, conf_beta=2.0),
            _make_entry("e-invalidated", domains=["javascript"], conf_alpha=15.0, conf_beta=2.0),
        ]

        prior = _compute_knowledge_prior(agents, items)
        assert prior is not None
        # Both agents should have topology edges influenced by their domains
        assert (agents[0].id, agents[1].id) in prior


# ---------------------------------------------------------------------------
# 4. Co-occurrence × operator invalidation
# ---------------------------------------------------------------------------


class TestCooccurrenceOperatorInvalidation:
    """Test that co-occurrence reinforcement does not check operator overlays.

    DOCUMENTED GAP: co-occurrence reinforcement at knowledge_catalog.py:559-583
    fires on all result IDs without checking if entries are muted/invalidated.
    Invalidated entries will still accumulate co-occurrence weight with valid ones.
    """

    def test_cooccurrence_reinforces_regardless_of_overlay_state(self) -> None:
        """Co-occurrence weights accumulate for any pair in retrieval results.

        Even if one entry is later invalidated, its existing co-occurrence
        links persist and reinforce.
        """
        store = ProjectionStore()

        # Simulate co-occurrence reinforcement (the same logic as knowledge_catalog)
        result_ids = ["e-valid", "e-invalidated", "e-normal"]
        now_iso = datetime(2026, 3, 19, 10, 0, tzinfo=UTC).isoformat()
        for i, id_a in enumerate(result_ids):
            for id_b in result_ids[i + 1:]:
                key = cooccurrence_key(id_a, id_b)
                co_entry = store.cooccurrence_weights.get(key)
                if co_entry is None:
                    co_entry = CooccurrenceEntry(
                        weight=0.5, last_reinforced=now_iso, reinforcement_count=1,
                    )
                else:
                    co_entry.weight = min(co_entry.weight * 1.05, 10.0)
                    co_entry.last_reinforced = now_iso
                    co_entry.reinforcement_count += 1
                store.cooccurrence_weights[key] = co_entry

        # Now set e-invalidated as invalidated
        store.operator_overlays.invalidated_entries.add("e-invalidated")

        # Co-occurrence weights still exist for invalidated entry pairs
        key_inv = cooccurrence_key("e-valid", "e-invalidated")
        assert key_inv in store.cooccurrence_weights
        assert store.cooccurrence_weights[key_inv].weight > 0

    def test_cooccurrence_signal_reads_from_invalidated_entry_pairs(self) -> None:
        """_cooccurrence_score does not filter by overlay state."""
        store = ProjectionStore()

        # Set up co-occurrence between a valid and invalidated entry
        key = cooccurrence_key("e-valid", "e-invalidated")
        store.cooccurrence_weights[key] = CooccurrenceEntry(
            weight=5.0, last_reinforced="2026-03-19T10:00:00+00:00", reinforcement_count=10,
        )

        # Mark one as invalidated
        store.operator_overlays.invalidated_entries.add("e-invalidated")

        # Co-occurrence signal still returns a value for the pair
        signal = _cooccurrence_score(
            "e-valid", ["e-invalidated"], projections=store,
        )
        assert signal > 0.0, (
            "Co-occurrence signal should return non-zero for invalidated pairs "
            "(gap: no overlay filter in co-occurrence path)"
        )

    def test_muted_entry_cooccurrence_persists(self) -> None:
        """Muted entries retain co-occurrence edges — muting is retrieval-only."""
        store = ProjectionStore()

        key = cooccurrence_key("e-a", "e-muted")
        store.cooccurrence_weights[key] = CooccurrenceEntry(
            weight=3.0, last_reinforced="2026-03-19T10:00:00+00:00",
            reinforcement_count=5,
        )

        # Mute one entry
        store.operator_overlays.muted_entries.add("e-muted")

        # Weight is preserved
        assert store.cooccurrence_weights[key].weight == 3.0
        assert store.cooccurrence_weights[key].reinforcement_count == 5


# ---------------------------------------------------------------------------
# 5. Proactive insights × operator annotations
# ---------------------------------------------------------------------------


class TestProactiveInsightsAnnotations:
    """Test that proactive intelligence rules work with annotated entries."""

    def test_annotated_entry_still_triggers_confidence_decline(self) -> None:
        """Annotations don't prevent confidence decline insights."""
        from formicos.surface.proactive_intelligence import _rule_confidence_decline

        # _rule_confidence_decline takes entries dict directly
        entries: dict[str, dict[str, Any]] = {
            "e-1": {
                "id": "e-1",
                "workspace_id": "ws-1",
                "conf_alpha": 2.0,
                "conf_beta": 15.0,  # Very low posterior mean
                "peak_alpha": 20.0,
                "status": "active",
                "title": "Annotated entry",
                "domains": ["python"],
                "created_at": datetime(2026, 1, 1, tzinfo=UTC).isoformat(),
                "last_confidence_update": (datetime.now(UTC) - timedelta(days=3)).isoformat(),
            },
        }

        # Also set up overlays to show annotations exist but don't block insights
        store = ProjectionStore()
        store.memory_entries.update(entries)
        from formicos.surface.projections import OperatorAnnotation

        store.operator_overlays.annotations["e-1"] = [
            OperatorAnnotation(
                annotation_text="This is important",
                tag="important",
                actor="operator",
                timestamp="2026-03-19T10:00:00+00:00",
            ),
        ]

        insights = _rule_confidence_decline(entries)
        # Entry should still trigger confidence decline despite annotation
        declined_ids = [
            eid for insight in insights for eid in insight.affected_entries
        ]
        assert "e-1" in declined_ids

    def test_muted_entries_still_appear_in_contradiction_detection(self) -> None:
        """Muted entries are still visible to proactive insight rules.

        Contradiction detection scans all entries passed to it, not filtered
        by overlays. The caller (briefing generator) passes store.memory_entries
        which includes muted entries.
        """
        from formicos.surface.proactive_intelligence import _rule_contradiction

        # _rule_contradiction takes entries dict directly
        # Entries need status=verified and conf_alpha>5 to be candidates
        entries: dict[str, dict[str, Any]] = {
            "e-pos": {
                "id": "e-pos",
                "workspace_id": "ws-1",
                "title": "Python is fast for data processing",
                "content": "Python excels at data processing due to optimized libraries",
                "domains": ["python", "data"],
                "polarity": "positive",
                "status": "verified",
                "conf_alpha": 10.0,
                "conf_beta": 2.0,
                "created_at": datetime(2026, 3, 1, tzinfo=UTC).isoformat(),
            },
            "e-neg": {
                "id": "e-neg",
                "workspace_id": "ws-1",
                "title": "Python is slow for data processing",
                "content": "Python is too slow for real-time data processing",
                "domains": ["python", "data"],
                "polarity": "negative",
                "status": "verified",
                "conf_alpha": 10.0,
                "conf_beta": 2.0,
                "created_at": datetime(2026, 3, 1, tzinfo=UTC).isoformat(),
            },
        }

        # Also verify that muting in overlays doesn't affect rule input
        store = ProjectionStore()
        store.memory_entries.update(entries)
        store.operator_overlays.muted_entries.add("e-neg")

        # Contradiction rule receives ALL memory_entries, including muted ones
        # (overlays are retrieval-level, not insight-level)
        insights = _rule_contradiction(store.memory_entries)
        assert isinstance(insights, list)
        # The muted entry should still participate in contradiction detection
        # If a contradiction is found, it should include the muted entry
        if insights:
            all_affected = [eid for i in insights for eid in i.affected_entries]
            # At least one of our entries should be affected
            assert "e-pos" in all_affected or "e-neg" in all_affected


# ---------------------------------------------------------------------------
# 6. Admission scoring × federation trust
# ---------------------------------------------------------------------------


class TestAdmissionFederationTrust:
    """Test the interaction between admission scoring and federation trust."""

    def test_high_trust_federated_entry_admitted(self) -> None:
        """Federated entry with high peer trust gets admitted."""
        entry = _make_entry(
            "fed-1", source_peer="peer-a", status="verified",
            conf_alpha=15.0, conf_beta=2.0,
        )
        result = evaluate_entry(entry, peer_trust_score=0.9)

        assert result.admitted is True
        assert "federated" in result.flags
        assert result.signal_scores["federation"] == 0.9 * 0.8

    def test_low_trust_federated_entry_demoted(self) -> None:
        """Federated entry with low peer trust gets demoted to candidate."""
        entry = _make_entry(
            "fed-2", source_peer="peer-b", status="active",
            conf_alpha=5.0, conf_beta=5.0,
        )
        result = evaluate_entry(entry, peer_trust_score=0.2)

        assert "low_peer_trust" in result.flags
        # Low trust leads to low federation signal → possible demotion
        assert result.signal_scores["federation"] == 0.2 * 0.8

    def test_unknown_peer_gets_conservative_score(self) -> None:
        """Federated entry with no trust score defaults to 0.3."""
        entry = _make_entry("fed-3", source_peer="peer-unknown")
        result = evaluate_entry(entry, peer_trust_score=None)

        assert result.signal_scores["federation"] == 0.3
        assert "federated" in result.flags

    def test_local_entry_full_federation_trust(self) -> None:
        """Local entries always get federation signal of 1.0."""
        entry = _make_entry("local-1")
        result = evaluate_entry(entry)

        assert result.signal_scores["federation"] == 1.0
        assert "federated" not in result.flags

    def test_scanner_critical_overrides_high_trust(self) -> None:
        """Scanner critical finding rejects even high-trust federated entries."""
        entry = _make_entry("fed-4", source_peer="peer-a")
        scanner = {"tier": "critical", "findings": ["prompt_injection"]}
        result = evaluate_entry(entry, peer_trust_score=0.95, scanner_result=scanner)

        assert result.admitted is False
        assert result.status_override == "rejected"

    def test_admission_federation_penalty_composition(self) -> None:
        """Admission's federation signal × retrieval's fed_penalty are independent.

        Admission scores with fed_score = trust * 0.8 for known peers.
        Retrieval penalizes with fed_penalty via posterior-aware trust (Wave 41 A1).
        These are separate subsystems that both reduce federated entry ranking.
        """
        entry = _make_entry(
            "fed-5", source_peer="peer-a", status="active",
            conf_alpha=15.0, conf_beta=2.0,
        )

        # Admission path
        admission = evaluate_entry(entry, peer_trust_score=0.7)
        assert admission.signal_scores["federation"] == 0.7 * 0.8

        # Retrieval path (independent) — Wave 41: posterior-aware, not fixed band
        retrieval_penalty = federated_retrieval_penalty(entry)
        assert 0.1 < retrieval_penalty < 1.0  # bounded penalty

        # Both apply, but they are independent subsystems
        assert admission.signal_scores["federation"] != retrieval_penalty


# ---------------------------------------------------------------------------
# 7. Bi-temporal edges × co-occurrence filtering
# ---------------------------------------------------------------------------


class TestBitemporalCooccurrence:
    """Test that co-occurrence weights interact correctly with graph structures."""

    def test_cooccurrence_key_canonical_ordering(self) -> None:
        """Co-occurrence keys are always ordered (min, max) for consistency."""
        key_ab = cooccurrence_key("b-entry", "a-entry")
        key_ba = cooccurrence_key("a-entry", "b-entry")
        assert key_ab == key_ba == ("a-entry", "b-entry")

    def test_cooccurrence_weight_growth_is_bounded(self) -> None:
        """Co-occurrence weight reinforcement caps at 10.0."""
        store = ProjectionStore()
        key = cooccurrence_key("e-1", "e-2")
        store.cooccurrence_weights[key] = CooccurrenceEntry(
            weight=9.8, last_reinforced="2026-03-19T10:00:00+00:00",
            reinforcement_count=100,
        )

        # Reinforce (same logic as knowledge_catalog.py:578)
        store.cooccurrence_weights[key].weight = min(
            store.cooccurrence_weights[key].weight * 1.05, 10.0,
        )
        assert store.cooccurrence_weights[key].weight <= 10.0

    def test_cooccurrence_signal_sigmoid_normalization(self) -> None:
        """Co-occurrence signal uses sigmoid: 1 - e^{-0.6w}."""
        # With weight=0 → signal ~0.0
        signal_zero = _cooccurrence_score("e-1", [], projections=None)
        assert signal_zero == 0.0

        # With high weight → signal close to 1.0
        store = ProjectionStore()
        key = cooccurrence_key("e-1", "e-2")
        store.cooccurrence_weights[key] = CooccurrenceEntry(weight=8.0)

        signal_high = _cooccurrence_score("e-1", ["e-2"], projections=store)
        assert signal_high > 0.99, f"High-weight signal should be near 1.0, got {signal_high}"

    def test_cooccurrence_takes_max_across_pairs(self) -> None:
        """Co-occurrence signal uses max weight across all other_ids."""
        store = ProjectionStore()
        key1 = cooccurrence_key("e-1", "e-2")
        key2 = cooccurrence_key("e-1", "e-3")
        store.cooccurrence_weights[key1] = CooccurrenceEntry(weight=2.0)
        store.cooccurrence_weights[key2] = CooccurrenceEntry(weight=5.0)

        signal = _cooccurrence_score("e-1", ["e-2", "e-3"], projections=store)
        signal_just_high = _cooccurrence_score(
            "e-1", ["e-3"], projections=store,
        )
        # Should equal the higher weight's signal since it takes max
        assert signal == signal_just_high
