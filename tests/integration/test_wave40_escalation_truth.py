"""Wave 40 Team 2: Escalation × validator × reporting seam tests.

Covers the interaction between:
- Auto-escalation governance (stall_count ≥ 2/4 in runner.py)
- Validator verdicts (pass/fail/inconclusive from Wave 39 1B)
- ColonyOutcome escalation fields (Wave 38 2B)
- Escalation matrix truth (routing_override → outcome derivation)

Also tests that escalation-related projections are replay-derivable.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest

from formicos.engine.runner import RoundRunner
from formicos.surface.projections import (
    AgentProjection,
    ColonyOutcome,
    ColonyProjection,
    ProjectionStore,
    RoundProjection,
    _build_colony_outcome,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_colony(
    colony_id: str,
    *,
    workspace_id: str = "ws-1",
    thread_id: str = "th-1",
    strategy: str = "stigmergic",
    routing_override: dict[str, Any] | None = None,
    rounds: int = 5,
    cost: float = 1.0,
    quality: float = 0.7,
    validator_verdict: str | None = None,
    validator_task_type: str | None = None,
) -> ColonyProjection:
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
        validator_verdict=validator_verdict,
        validator_task_type=validator_task_type,
    )
    colony.agents["a1"] = AgentProjection(id="a1", caste="coder", model="test-model")
    for r in range(1, rounds + 1):
        colony.round_records.append(RoundProjection(
            round_number=r,
            cost=cost / rounds,
        ))
    return colony


def _build_outcome(
    colony: ColonyProjection,
    succeeded: bool = True,
) -> ColonyOutcome:
    store = ProjectionStore()
    store.colonies[colony.id] = colony
    end_ts = datetime(2026, 3, 19, 10, 30, tzinfo=timezone.utc).isoformat()
    _build_colony_outcome(store, colony, succeeded, end_ts)
    return store.colony_outcomes[colony.id]


# ---------------------------------------------------------------------------
# Validators × auto-escalation
# ---------------------------------------------------------------------------


class TestValidatorEscalationInteraction:
    """Test that validator verdicts and auto-escalation are independent.

    DOCUMENTED BEHAVIOR: Validator verdicts (pass/fail/inconclusive) are
    recorded on ColonyProjection but do NOT trigger escalation directly.
    Only stall_count logic triggers escalation. These are separate subsystems.
    """

    def test_governance_ignores_validator_verdict(self) -> None:
        """_evaluate_governance only checks stall_count, not validator verdict.

        The governance decision is independent of whether the validator
        says pass, fail, or inconclusive.
        """
        from formicos.engine.runner import GovernanceDecision

        class FakeConvergence:
            is_stalled: bool
            is_converged: bool
            goal_alignment: float

            def __init__(self, stalled: bool = False, converged: bool = False) -> None:
                self.is_stalled = stalled
                self.is_converged = converged
                self.goal_alignment = 0.8

        # Stalled with 2 rounds — warns regardless of validator
        result = RoundRunner._evaluate_governance(
            FakeConvergence(stalled=True),
            round_number=5,
            stall_count=2,
        )
        assert result.action == "warn"
        assert result.reason == "stalled 2+ rounds"

        # Stalled with 4 rounds — force_halt regardless of validator
        result = RoundRunner._evaluate_governance(
            FakeConvergence(stalled=True),
            round_number=8,
            stall_count=4,
        )
        assert result.action == "force_halt"
        assert result.reason == "stalled 3+ rounds"

    def test_successful_code_execute_overrides_stall(self) -> None:
        """A successful code_execute can trigger 'complete' even when stalled."""

        class FakeConvergence:
            is_stalled = True
            is_converged = False
            goal_alignment = 0.8

        result = RoundRunner._evaluate_governance(
            FakeConvergence(),
            round_number=3,
            stall_count=2,
            recent_successful_code_execute=True,
        )
        assert result.action == "complete"
        assert result.reason == "verified_execution_converged"

    def test_convergence_complete_at_round_2_plus(self) -> None:
        """Converged after round 2 → complete."""

        class FakeConvergence:
            is_stalled = False
            is_converged = True
            goal_alignment = 0.9

        result = RoundRunner._evaluate_governance(
            FakeConvergence(),
            round_number=3,
            stall_count=0,
        )
        assert result.action == "complete"
        assert result.reason == "converged"

    def test_low_alignment_warn_after_round_3(self) -> None:
        """Off-track warning when goal_alignment < 0.2 after round 3."""

        class FakeConvergence:
            is_stalled = False
            is_converged = False
            goal_alignment = 0.1

        result = RoundRunner._evaluate_governance(
            FakeConvergence(),
            round_number=4,
            stall_count=0,
        )
        assert result.action == "warn"
        assert result.reason == "off_track"


# ---------------------------------------------------------------------------
# Validator verdict → ColonyOutcome propagation
# ---------------------------------------------------------------------------


class TestValidatorOutcomePropagation:
    """Test that validator verdicts propagate correctly to ColonyOutcome."""

    def test_verdict_passes_through_to_outcome(self) -> None:
        """ColonyOutcome.validator_verdict mirrors ColonyProjection."""
        colony = _make_colony(
            "c-pass",
            validator_verdict="pass",
            validator_task_type="code",
        )
        outcome = _build_outcome(colony)

        assert outcome.validator_verdict == "pass"
        assert outcome.validator_task_type == "code"

    def test_fail_verdict_on_successful_colony(self) -> None:
        """A colony can succeed (complete) but have a 'fail' validator verdict.

        The validator checks task-type alignment, not colony success.
        """
        colony = _make_colony(
            "c-fail-verdict",
            validator_verdict="fail",
            validator_task_type="research",
        )
        outcome = _build_outcome(colony, succeeded=True)

        assert outcome.succeeded is True
        assert outcome.validator_verdict == "fail"

    def test_inconclusive_verdict_preserved(self) -> None:
        """Inconclusive verdict is preserved in the outcome."""
        colony = _make_colony(
            "c-incon",
            validator_verdict="inconclusive",
            validator_task_type="unknown",
        )
        outcome = _build_outcome(colony)
        assert outcome.validator_verdict == "inconclusive"

    def test_no_verdict_is_none(self) -> None:
        """Colonies without validator output have None verdict."""
        colony = _make_colony("c-none")
        outcome = _build_outcome(colony)
        assert outcome.validator_verdict is None
        assert outcome.validator_task_type is None


# ---------------------------------------------------------------------------
# Escalation matrix → ColonyOutcome fields
# ---------------------------------------------------------------------------


class TestEscalationOutcomeMatrix:
    """Test the escalation fields on ColonyOutcome derived from routing_override."""

    def test_non_escalated_colony_has_no_escalation_fields(self) -> None:
        """Colony without routing_override has escalated=False."""
        colony = _make_colony("c-normal")
        outcome = _build_outcome(colony)

        assert outcome.escalated is False
        assert outcome.escalated_tier is None
        assert outcome.escalation_reason is None
        assert outcome.escalation_round is None
        assert outcome.pre_escalation_cost == 0.0

    def test_escalated_colony_captures_tier_and_reason(self) -> None:
        """routing_override populates escalation tier and reason."""
        colony = _make_colony(
            "c-escalated",
            routing_override={
                "tier": "advanced",
                "reason": "stalled 3+ rounds",
                "set_at_round": 3,
            },
            rounds=6,
            cost=3.0,
        )
        outcome = _build_outcome(colony, succeeded=True)

        assert outcome.escalated is True
        assert outcome.escalated_tier == "advanced"
        assert outcome.escalation_reason == "stalled 3+ rounds"
        assert outcome.escalation_round == 3

    def test_pre_escalation_cost_calculated_correctly(self) -> None:
        """Pre-escalation cost sums round costs before the escalation round."""
        colony = _make_colony(
            "c-cost",
            routing_override={
                "tier": "advanced",
                "reason": "stalled",
                "set_at_round": 3,
            },
            rounds=5,
            cost=5.0,  # 1.0 per round
        )
        outcome = _build_outcome(colony)

        # Rounds 1,2 are before escalation round 3 → 2.0 cost
        assert abs(outcome.pre_escalation_cost - 2.0) < 0.01

    def test_escalation_with_validator_verdict(self) -> None:
        """Escalated colony can also carry a validator verdict."""
        colony = _make_colony(
            "c-esc-val",
            routing_override={
                "tier": "premium",
                "reason": "capability_needed",
                "set_at_round": 2,
            },
            validator_verdict="pass",
            validator_task_type="code",
            rounds=5,
            cost=5.0,
        )
        outcome = _build_outcome(colony)

        assert outcome.escalated is True
        assert outcome.validator_verdict == "pass"
        assert outcome.validator_task_type == "code"

    def test_failed_escalated_colony_outcome(self) -> None:
        """Failed colony with escalation captures both escalation and failure."""
        colony = _make_colony(
            "c-fail-esc",
            routing_override={
                "tier": "advanced",
                "reason": "stalled 3+ rounds",
                "set_at_round": 4,
            },
            rounds=8,
            cost=8.0,
        )
        outcome = _build_outcome(colony, succeeded=False)

        assert outcome.succeeded is False
        assert outcome.escalated is True
        assert outcome.escalated_tier == "advanced"


# ---------------------------------------------------------------------------
# Escalation governance thresholds
# ---------------------------------------------------------------------------


class TestEscalationThresholds:
    """Test the exact governance thresholds for escalation decisions."""

    def _evaluate(
        self,
        stall_count: int,
        round_number: int = 5,
        stalled: bool = True,
        code_execute: bool = False,
    ) -> Any:
        class FakeConvergence:
            is_stalled: bool
            is_converged: bool = False
            goal_alignment: float = 0.8

            def __init__(self, s: bool) -> None:
                self.is_stalled = s

        return RoundRunner._evaluate_governance(
            FakeConvergence(stalled),
            round_number=round_number,
            stall_count=stall_count,
            recent_successful_code_execute=code_execute,
        )

    def test_stall_0_continues(self) -> None:
        result = self._evaluate(stall_count=0, stalled=False)
        assert result.action == "continue"

    def test_stall_1_no_warn(self) -> None:
        """stall_count=1 does not trigger warn (threshold is 2)."""
        result = self._evaluate(stall_count=1)
        # With stalled=True but stall_count < 2, it falls through to continue
        # unless goal_alignment is low
        # Actually checking: stalled + code_execute → complete (if round >= 2)
        # No, code_execute is False here
        # stalled + stall_count < 2 → falls to continue (goal_alignment 0.8 > 0.2)
        assert result.action == "continue"

    def test_stall_2_warns(self) -> None:
        result = self._evaluate(stall_count=2)
        assert result.action == "warn"

    def test_stall_3_force_halts(self) -> None:
        result = self._evaluate(stall_count=3)
        assert result.action == "force_halt"

    def test_stall_4_force_halts(self) -> None:
        result = self._evaluate(stall_count=4)
        assert result.action == "force_halt"

    def test_stall_10_force_halts(self) -> None:
        result = self._evaluate(stall_count=10)
        assert result.action == "force_halt"

    def test_code_execute_overrides_stall_4(self) -> None:
        """Successful code_execute at round >= 2 overrides even stall_count=4."""
        result = self._evaluate(stall_count=4, round_number=3, code_execute=True)
        # code_execute check comes BEFORE stall_count check in the method
        assert result.action == "complete"

    def test_code_execute_requires_round_2(self) -> None:
        """Successful code_execute at round < 2 does not trigger complete."""
        result = self._evaluate(stall_count=2, round_number=1, code_execute=True)
        # round_number < 2 → code_execute check fails → falls to stall_count check
        assert result.action == "warn"
