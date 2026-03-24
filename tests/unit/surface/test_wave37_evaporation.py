"""Adaptive evaporation recommendation tests (Wave 37, Pillar 4A + 4C).

Validates that:
- domain-specific decay recommendations are evidence-backed
- operator feedback influences recommendations (4C integration)
- recommendations are recommendation-only (no automatic tuning)
- the Queen can see and explain recommendations
"""

from __future__ import annotations

from datetime import UTC, datetime

from formicos.core.events import (
    MemoryConfidenceUpdated,
    MemoryEntryCreated,
    WorkspaceConfigSnapshot,
    WorkspaceCreated,
)
from formicos.surface.proactive_intelligence import (
    generate_briefing,
    generate_evaporation_recommendations,
)
from formicos.surface.projections import ProjectionStore


def _now() -> datetime:
    return datetime.now(tz=UTC)


_seq = 0


def _next_seq() -> int:
    global _seq
    _seq += 1
    return _seq


def _make_workspace(store: ProjectionStore, ws_id: str = "evap-ws") -> str:
    store.apply(WorkspaceCreated(
        seq=_next_seq(), timestamp=_now(), address=ws_id,
        name=ws_id,
        config=WorkspaceConfigSnapshot(budget=5.0, strategy="stigmergic"),
    ))
    return ws_id


def _seed_domain(
    store: ProjectionStore,
    ws_id: str,
    domain: str,
    count: int = 5,
    decay_class: str = "stable",
    prediction_errors: int = 0,
    conf_alpha: float = 10.0,
    conf_beta: float = 3.0,
) -> list[str]:
    """Seed multiple entries in a domain with consistent properties."""
    entry_ids = []
    for i in range(count):
        eid = f"{domain}-entry-{i}"
        entry_ids.append(eid)
        store.apply(MemoryEntryCreated(
            seq=_next_seq(), timestamp=_now(), address=ws_id,
            entry={
                "id": eid,
                "category": "skill",
                "sub_type": "technique",
                "title": f"{domain} technique {i}",
                "content": f"Content for {domain} entry {i}",
                "domains": [domain],
                "decay_class": decay_class,
                "status": "verified",
                "conf_alpha": conf_alpha,
                "conf_beta": conf_beta,
                "workspace_id": ws_id,
                "source_colony_id": f"col-{domain}-{i}",
                "polarity": "positive",
                "prediction_error_count": prediction_errors,
                "created_at": _now().isoformat(),
            },
            workspace_id=ws_id,
        ))
    return entry_ids


class TestEvaporationRecommendationGeneration:
    """generate_evaporation_recommendations returns structured results."""

    def test_no_recommendations_for_small_domains(self) -> None:
        """Domains with fewer than 3 entries get no recommendation."""
        store = ProjectionStore()
        ws_id = _make_workspace(store)
        _seed_domain(store, ws_id, "tiny", count=2)

        recs = generate_evaporation_recommendations(ws_id, store)
        assert len(recs) == 0

    def test_stable_domain_with_high_errors_recommends_ephemeral(self) -> None:
        """Stable entries with high prediction errors → recommend ephemeral."""
        store = ProjectionStore()
        ws_id = _make_workspace(store)
        _seed_domain(
            store, ws_id, "stale-auth",
            count=5, decay_class="stable",
            prediction_errors=5,
        )

        recs = generate_evaporation_recommendations(ws_id, store)
        assert len(recs) >= 1
        rec = next(r for r in recs if r.domain == "stale-auth")
        assert rec.current_decay_class == "stable"
        assert rec.recommended_decay_class == "ephemeral"
        assert "prediction errors" in rec.rationale

    def test_ephemeral_domain_with_high_confidence_recommends_stable(self) -> None:
        """Ephemeral entries with high confidence and low errors → stable."""
        store = ProjectionStore()
        ws_id = _make_workspace(store)
        _seed_domain(
            store, ws_id, "reliable-python",
            count=6, decay_class="ephemeral",
            prediction_errors=0,
            conf_alpha=20.0, conf_beta=3.0,
        )

        recs = generate_evaporation_recommendations(ws_id, store)
        assert len(recs) >= 1
        rec = next(r for r in recs if r.domain == "reliable-python")
        assert rec.current_decay_class == "ephemeral"
        assert rec.recommended_decay_class == "stable"
        assert "reliable" in rec.rationale

    def test_no_recommendation_when_decay_is_appropriate(self) -> None:
        """Domain with moderate metrics gets no change recommendation."""
        store = ProjectionStore()
        ws_id = _make_workspace(store)
        _seed_domain(
            store, ws_id, "moderate-domain",
            count=5, decay_class="stable",
            prediction_errors=1,
            conf_alpha=10.0, conf_beta=5.0,
        )

        recs = generate_evaporation_recommendations(ws_id, store)
        moderate_recs = [r for r in recs if r.domain == "moderate-domain"]
        assert len(moderate_recs) == 0


class TestEvaporationInBriefing:
    """Evaporation recommendations surface as briefing insights."""

    def test_evaporation_insight_in_briefing(self) -> None:
        """Briefing includes evaporation insight when conditions are met."""
        store = ProjectionStore()
        ws_id = _make_workspace(store)
        _seed_domain(
            store, ws_id, "problem-domain",
            count=5, decay_class="stable",
            prediction_errors=5,
        )

        briefing = generate_briefing(ws_id, store)
        evap_insights = [
            i for i in briefing.insights if i.category == "evaporation"
        ]
        assert len(evap_insights) >= 1
        assert "problem-domain" in evap_insights[0].title


class TestOperatorFeedbackInfluence:
    """Operator feedback drives evaporation recommendations (4C integration)."""

    def test_high_demotion_rate_triggers_faster_decay(self) -> None:
        """Operator demotions in a domain push toward faster decay."""
        store = ProjectionStore()
        ws_id = _make_workspace(store)
        _seed_domain(
            store, ws_id, "demoted-domain",
            count=5, decay_class="stable",
            prediction_errors=0,
            conf_alpha=10.0, conf_beta=3.0,
        )

        # Simulate operator demotions: 3 negative, 1 positive
        for i in range(4):
            store.apply(MemoryConfidenceUpdated(
                seq=_next_seq(), timestamp=_now(), address=ws_id,
                entry_id=f"demoted-domain-entry-{i}",
                colony_id=f"demotion-col-{i}",
                colony_succeeded=i == 0,  # only first is positive
                reason="colony_outcome",
                old_alpha=10.0, old_beta=3.0,
                new_alpha=11.0 if i == 0 else 10.0,
                new_beta=3.0 if i == 0 else 4.0,
                new_confidence=0.75, workspace_id=ws_id,
            ))

        # Demotion rate should be 0.75 (3/4)
        rate = store.operator_behavior.domain_demotion_rate("demoted-domain")
        assert rate == 0.75

        recs = generate_evaporation_recommendations(ws_id, store)
        demoted_recs = [r for r in recs if r.domain == "demoted-domain"]
        assert len(demoted_recs) >= 1
        assert demoted_recs[0].recommended_decay_class == "ephemeral"
        assert "demotion" in demoted_recs[0].rationale

    def test_low_demotion_rate_does_not_trigger(self) -> None:
        """Low demotion rate alone does not trigger decay change."""
        store = ProjectionStore()
        ws_id = _make_workspace(store)
        _seed_domain(
            store, ws_id, "healthy-domain",
            count=5, decay_class="stable",
            prediction_errors=0,
            conf_alpha=10.0, conf_beta=3.0,
        )

        # All positive feedback
        for i in range(3):
            store.apply(MemoryConfidenceUpdated(
                seq=_next_seq(), timestamp=_now(), address=ws_id,
                entry_id=f"healthy-domain-entry-{i}",
                colony_id=f"healthy-col-{i}",
                colony_succeeded=True, reason="colony_outcome",
                old_alpha=10.0, old_beta=3.0,
                new_alpha=11.0, new_beta=3.0,
                new_confidence=0.78, workspace_id=ws_id,
            ))

        recs = generate_evaporation_recommendations(ws_id, store)
        healthy_recs = [r for r in recs if r.domain == "healthy-domain"]
        assert len(healthy_recs) == 0


class TestRecommendationOnlyConstraint:
    """Recommendations are recommendation-only. No automatic tuning."""

    def test_recommendations_do_not_modify_entries(self) -> None:
        """Generating recommendations does not change entry decay_class."""
        store = ProjectionStore()
        ws_id = _make_workspace(store)
        _seed_domain(
            store, ws_id, "no-auto-domain",
            count=5, decay_class="stable",
            prediction_errors=5,
        )

        # Capture state before
        before = {
            eid: dict(e) for eid, e in store.memory_entries.items()
        }

        recs = generate_evaporation_recommendations(ws_id, store)
        assert len(recs) >= 1  # Recommendations exist

        # Verify entries are unchanged
        for eid, before_entry in before.items():
            assert store.memory_entries[eid]["decay_class"] == before_entry["decay_class"]

    def test_recommendation_includes_evidence(self) -> None:
        """Each recommendation includes inspectable evidence."""
        store = ProjectionStore()
        ws_id = _make_workspace(store)
        _seed_domain(
            store, ws_id, "evidence-domain",
            count=5, decay_class="stable",
            prediction_errors=4,
        )

        recs = generate_evaporation_recommendations(ws_id, store)
        assert len(recs) >= 1
        rec = recs[0]
        assert "entry_count" in rec.evidence
        assert "avg_prediction_errors" in rec.evidence
        assert "avg_confidence" in rec.evidence
        assert "operator_demotion_rate" in rec.evidence
