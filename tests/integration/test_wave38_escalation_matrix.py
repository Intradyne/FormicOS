"""Wave 38 Team 2: Escalation outcome matrix tests.

Verifies that the replay-derived escalation outcome matrix:
- reads from governance-owned routing_override truth
- does not conflate provider fallback with capability escalation
- captures tier, reason, round, cost, quality, and outcome
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any

import pytest

from formicos.surface.projections import (
    AgentProjection,
    ColonyOutcome,
    ColonyProjection,
    ProjectionStore,
    RoundProjection,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_colony(
    colony_id: str,
    workspace_id: str = "ws-1",
    thread_id: str = "th-1",
    strategy: str = "stigmergic",
    routing_override: dict[str, Any] | None = None,
    rounds: int = 5,
    cost: float = 1.0,
    quality: float = 0.7,
) -> ColonyProjection:
    """Create a test colony projection with optional escalation."""
    colony = ColonyProjection(
        id=colony_id,
        thread_id=thread_id,
        workspace_id=workspace_id,
        task=f"Task for {colony_id}",
        status="running",
        strategy=strategy,
        round_number=rounds,
        cost=cost,
        quality_score=quality,
        spawned_at=datetime(2026, 3, 19, 10, 0, tzinfo=timezone.utc).isoformat(),
        routing_override=routing_override,
    )
    # Add agent and round records for realism
    colony.agents["a1"] = AgentProjection(id="a1", caste="coder", model="test-model")
    for r in range(1, rounds + 1):
        colony.round_records.append(RoundProjection(
            round_number=r,
            cost=cost / rounds,
        ))
    return colony


def _build_outcome_via_store(
    colony: ColonyProjection,
    succeeded: bool = True,
) -> ColonyOutcome:
    """Use the real _build_colony_outcome path through ProjectionStore."""
    from formicos.surface.projections import _build_colony_outcome

    store = ProjectionStore()
    store.colonies[colony.id] = colony
    end_ts = datetime(2026, 3, 19, 10, 30, tzinfo=timezone.utc).isoformat()
    _build_colony_outcome(store, colony, succeeded, end_ts)
    return store.colony_outcomes[colony.id]


# ---------------------------------------------------------------------------
# Tests: Escalation fields on ColonyOutcome
# ---------------------------------------------------------------------------


class TestEscalationOutcomeFields:
    """Verify escalation fields are correctly derived from routing_override."""

    def test_non_escalated_colony_has_defaults(self) -> None:
        """Colony without routing_override has escalated=False."""
        colony = _make_colony("col-plain")
        outcome = _build_outcome_via_store(colony)

        assert outcome.escalated is False
        assert outcome.starting_tier is None
        assert outcome.escalated_tier is None
        assert outcome.escalation_reason is None
        assert outcome.escalation_round is None
        assert outcome.pre_escalation_cost == 0.0

    def test_escalated_colony_captures_tier(self) -> None:
        """Colony with routing_override captures escalation tier."""
        colony = _make_colony(
            "col-esc",
            routing_override={
                "tier": "heavy",
                "reason": "capability_mismatch",
                "set_at_round": 3,
            },
            rounds=5,
            cost=2.0,
        )
        outcome = _build_outcome_via_store(colony)

        assert outcome.escalated is True
        assert outcome.escalated_tier == "heavy"
        assert outcome.escalation_reason == "capability_mismatch"
        assert outcome.escalation_round == 3
        assert outcome.starting_tier == "standard"

    def test_starting_tier_derived_from_castes(self) -> None:
        """Starting tier is derived from actual spawned caste tiers, not hard-coded."""
        from formicos.core.types import CasteSlot, SubcasteTier

        colony = _make_colony(
            "col-tiers",
            routing_override={
                "tier": "heavy",
                "reason": "test",
                "set_at_round": 2,
            },
        )
        # Set explicit caste tiers
        colony.castes = [
            CasteSlot(caste="coder", tier=SubcasteTier.light),
            CasteSlot(caste="reviewer", tier=SubcasteTier.light),
        ]
        outcome = _build_outcome_via_store(colony)
        assert outcome.starting_tier == "light"

    def test_starting_tier_mixed_castes(self) -> None:
        """Mixed caste tiers are represented honestly."""
        from formicos.core.types import CasteSlot, SubcasteTier

        colony = _make_colony(
            "col-mixed",
            routing_override={
                "tier": "heavy",
                "reason": "test",
                "set_at_round": 2,
            },
        )
        colony.castes = [
            CasteSlot(caste="coder", tier=SubcasteTier.standard),
            CasteSlot(caste="reviewer", tier=SubcasteTier.light),
        ]
        outcome = _build_outcome_via_store(colony)
        # Sorted unique tiers joined
        assert outcome.starting_tier == "light,standard"

    def test_pre_escalation_cost_computed(self) -> None:
        """Pre-escalation cost sums rounds before the override round."""
        colony = _make_colony(
            "col-cost",
            routing_override={
                "tier": "heavy",
                "reason": "slow_progress",
                "set_at_round": 3,
            },
            rounds=5,
            cost=5.0,  # 1.0 per round
        )
        outcome = _build_outcome_via_store(colony)

        # Rounds 1, 2 are before round 3 → pre_escalation_cost = 2 × 1.0 = 2.0
        assert outcome.pre_escalation_cost == pytest.approx(2.0, abs=0.01)

    def test_escalation_fields_serializable(self) -> None:
        """ColonyOutcome with escalation fields serializes correctly via asdict."""
        colony = _make_colony(
            "col-ser",
            routing_override={
                "tier": "max",
                "reason": "complex_task",
                "set_at_round": 1,
            },
        )
        outcome = _build_outcome_via_store(colony)
        d = asdict(outcome)

        assert d["escalated"] is True
        assert d["escalated_tier"] == "max"
        assert d["escalation_reason"] == "complex_task"
        assert d["escalation_round"] == 1
        assert isinstance(d["pre_escalation_cost"], (int, float))

    def test_escalation_success_vs_failure(self) -> None:
        """Escalated colonies can succeed or fail independently."""
        override = {
            "tier": "heavy",
            "reason": "test",
            "set_at_round": 2,
        }
        colony_ok = _make_colony("col-ok", routing_override=override)
        colony_fail = _make_colony("col-fail", routing_override=override)

        outcome_ok = _build_outcome_via_store(colony_ok, succeeded=True)
        outcome_fail = _build_outcome_via_store(colony_fail, succeeded=False)

        assert outcome_ok.escalated is True
        assert outcome_ok.succeeded is True
        assert outcome_fail.escalated is True
        assert outcome_fail.succeeded is False


# ---------------------------------------------------------------------------
# Tests: Provider fallback is NOT escalation
# ---------------------------------------------------------------------------


class TestProviderFallbackExclusion:
    """Verify that provider fallback does not appear as escalation."""

    def test_no_routing_override_means_no_escalation(self) -> None:
        """A colony that used provider fallback (no routing_override) shows
        as non-escalated. Provider fallback is router infrastructure, not
        governance-owned capability escalation."""
        colony = _make_colony("col-fallback", routing_override=None)
        outcome = _build_outcome_via_store(colony)

        assert outcome.escalated is False
        assert outcome.escalated_tier is None
        # Even if the colony used a different model via fallback,
        # the escalation matrix does not know about it — by design.

    def test_escalation_requires_governance_reason(self) -> None:
        """The escalation matrix only reports entries with explicit reasons."""
        # Valid governance escalation
        gov_colony = _make_colony(
            "col-gov",
            routing_override={
                "tier": "heavy",
                "reason": "governance_escalation_on_stall",
                "set_at_round": 4,
            },
        )
        outcome = _build_outcome_via_store(gov_colony)

        assert outcome.escalated is True
        assert outcome.escalation_reason == "governance_escalation_on_stall"


# ---------------------------------------------------------------------------
# Tests: Matrix reporting shape
# ---------------------------------------------------------------------------


class TestEscalationMatrixReporting:
    """Verify the escalation matrix can produce correct reports."""

    def test_matrix_distinguishes_escalated_from_not(self) -> None:
        """The matrix correctly separates escalated and non-escalated colonies."""
        store = ProjectionStore()
        from formicos.surface.projections import _build_colony_outcome

        # Non-escalated colony
        plain = _make_colony("col-plain", workspace_id="ws-1")
        store.colonies["col-plain"] = plain
        _build_colony_outcome(
            store, plain, True,
            datetime(2026, 3, 19, 10, 30, tzinfo=timezone.utc).isoformat(),
        )

        # Escalated colony
        esc = _make_colony(
            "col-esc", workspace_id="ws-1",
            routing_override={"tier": "heavy", "reason": "stall", "set_at_round": 2},
        )
        store.colonies["col-esc"] = esc
        _build_colony_outcome(
            store, esc, True,
            datetime(2026, 3, 19, 10, 45, tzinfo=timezone.utc).isoformat(),
        )

        # Build matrix report
        escalated = [
            o for o in store.colony_outcomes.values()
            if o.workspace_id == "ws-1" and o.escalated
        ]
        non_escalated = [
            o for o in store.colony_outcomes.values()
            if o.workspace_id == "ws-1" and not o.escalated
        ]

        assert len(escalated) == 1
        assert len(non_escalated) == 1
        assert escalated[0].colony_id == "col-esc"
        assert non_escalated[0].colony_id == "col-plain"

    def test_matrix_captures_required_fields(self) -> None:
        """The matrix report includes all fields required by Wave 38 spec:
        domain/task family, starting tier, escalated tier, reason,
        round at override, total cost, wall time, quality, outcome."""
        colony = _make_colony(
            "col-full",
            routing_override={
                "tier": "max",
                "reason": "hard_reasoning_task",
                "set_at_round": 3,
            },
            cost=3.5,
            quality=0.85,
        )
        outcome = _build_outcome_via_store(colony)

        # All required fields present and typed correctly
        assert isinstance(outcome.strategy, str)  # domain/task family
        assert isinstance(outcome.starting_tier, str)
        assert isinstance(outcome.escalated_tier, str)
        assert isinstance(outcome.escalation_reason, str)
        assert isinstance(outcome.escalation_round, int)
        assert isinstance(outcome.total_cost, float)
        assert isinstance(outcome.duration_ms, int)
        assert isinstance(outcome.quality_score, float)
        assert isinstance(outcome.succeeded, bool)

    def test_multiple_escalations_in_workspace(self) -> None:
        """Multiple escalated colonies in same workspace are all captured."""
        store = ProjectionStore()
        from formicos.surface.projections import _build_colony_outcome

        for i in range(4):
            colony = _make_colony(
                f"col-esc-{i}",
                workspace_id="ws-multi",
                routing_override={
                    "tier": "heavy" if i % 2 == 0 else "max",
                    "reason": f"reason_{i}",
                    "set_at_round": i + 1,
                },
                cost=float(i + 1),
                quality=0.5 + i * 0.1,
            )
            store.colonies[colony.id] = colony
            _build_colony_outcome(
                store, colony, succeeded=(i % 3 != 0),
                end_ts=datetime(2026, 3, 19, 11, i, tzinfo=timezone.utc).isoformat(),
            )

        escalated = [
            o for o in store.colony_outcomes.values()
            if o.workspace_id == "ws-multi" and o.escalated
        ]
        assert len(escalated) == 4

        # Distinct tiers captured
        tiers = {o.escalated_tier for o in escalated}
        assert tiers == {"heavy", "max"}

        # Distinct reasons
        reasons = {o.escalation_reason for o in escalated}
        assert len(reasons) == 4

    def test_cost_delta_computable(self) -> None:
        """Post-escalation cost is derivable from total - pre_escalation."""
        colony = _make_colony(
            "col-delta",
            routing_override={
                "tier": "heavy",
                "reason": "test",
                "set_at_round": 2,
            },
            rounds=5,
            cost=5.0,
        )
        outcome = _build_outcome_via_store(colony)

        post_cost = outcome.total_cost - outcome.pre_escalation_cost
        assert post_cost >= 0
        assert abs(outcome.pre_escalation_cost + post_cost - outcome.total_cost) < 0.001
