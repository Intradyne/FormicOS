"""Wave 39 1A tests: colony audit-view assembly and completion classification.

Verifies that:
- Audit view assembles from replay-safe projection state
- No runtime-only internals are overclaimed
- Tri-state completion classification is correct
- Validator state flows into audit view and ColonyOutcome
"""

from __future__ import annotations

from formicos.surface.projections import (
    AgentProjection,
    ChatMessageProjection,
    ColonyProjection,
    RoundProjection,
    build_colony_audit_view,
    _classify_completion_state,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_colony(
    colony_id: str = "col-1",
    status: str = "completed",
    task: str = "Test task",
    validator_verdict: str | None = None,
    validator_task_type: str | None = None,
    validator_reason: str | None = None,
) -> ColonyProjection:
    """Create a test colony projection."""
    return ColonyProjection(
        id=colony_id,
        thread_id="th-1",
        workspace_id="ws-1",
        task=task,
        status=status,
        round_number=5,
        max_rounds=10,
        quality_score=0.75,
        cost=1.5,
        validator_verdict=validator_verdict,
        validator_task_type=validator_task_type,
        validator_reason=validator_reason,
    )


# ---------------------------------------------------------------------------
# Tri-state completion classification
# ---------------------------------------------------------------------------


class TestCompletionClassification:
    """Verify tri-state completion classification."""

    def test_completed_with_pass_is_validated(self) -> None:
        colony = _make_colony(status="completed", validator_verdict="pass")
        assert _classify_completion_state(colony) == "validated"

    def test_completed_without_verdict_is_unvalidated(self) -> None:
        colony = _make_colony(status="completed", validator_verdict=None)
        assert _classify_completion_state(colony) == "unvalidated"

    def test_completed_with_inconclusive_is_unvalidated(self) -> None:
        colony = _make_colony(status="completed", validator_verdict="inconclusive")
        assert _classify_completion_state(colony) == "unvalidated"

    def test_completed_with_fail_is_unvalidated(self) -> None:
        colony = _make_colony(status="completed", validator_verdict="fail")
        assert _classify_completion_state(colony) == "unvalidated"

    def test_failed_is_stalled(self) -> None:
        colony = _make_colony(status="failed")
        assert _classify_completion_state(colony) == "stalled"

    def test_killed_is_stalled(self) -> None:
        colony = _make_colony(status="killed")
        assert _classify_completion_state(colony) == "stalled"

    def test_running_is_running(self) -> None:
        colony = _make_colony(status="running")
        assert _classify_completion_state(colony) == "running"

    def test_pending_is_pending(self) -> None:
        colony = _make_colony(status="pending")
        assert _classify_completion_state(colony) == "pending"


# ---------------------------------------------------------------------------
# Audit view assembly
# ---------------------------------------------------------------------------


class TestAuditViewAssembly:
    """Verify audit view is assembled from replay-safe state."""

    def test_basic_structure(self) -> None:
        colony = _make_colony()
        audit = build_colony_audit_view(colony)

        assert audit["colony_id"] == "col-1"
        assert audit["task"] == "Test task"
        assert audit["status"] == "completed"
        assert audit["round_count"] == 5
        assert audit["max_rounds"] == 10
        assert audit["quality_score"] == 0.75
        assert audit["cost"] == 1.5
        assert "replay_safe_note" in audit
        assert "replay-safe" in audit["replay_safe_note"]

    def test_knowledge_used_from_accesses(self) -> None:
        colony = _make_colony()
        colony.knowledge_accesses = [
            {
                "round": 2,
                "access_mode": "retrieval",
                "items": [
                    {
                        "id": "entry-1",
                        "title": "Test Entry",
                        "source_system": "library",
                        "canonical_type": "skill",
                        "confidence": 0.85,
                    },
                ],
            },
        ]
        audit = build_colony_audit_view(colony)
        assert len(audit["knowledge_used"]) == 1
        assert audit["knowledge_used"][0]["title"] == "Test Entry"
        assert audit["knowledge_used"][0]["round"] == 2

    def test_directives_from_chat_messages(self) -> None:
        colony = _make_colony()
        colony.chat_messages = [
            ChatMessageProjection(
                sender="operator",
                content="Focus on the auth module",
                timestamp="2026-03-19T10:00:00Z",
                event_kind="directive",
            ),
            ChatMessageProjection(
                sender="system",
                content="Round 1 started",
                timestamp="2026-03-19T10:01:00Z",
                event_kind="phase",
            ),
        ]
        audit = build_colony_audit_view(colony)
        assert len(audit["directives"]) == 1
        assert audit["directives"][0]["content"] == "Focus on the auth module"

    def test_governance_actions_from_chat(self) -> None:
        colony = _make_colony()
        colony.chat_messages = [
            ChatMessageProjection(
                sender="system",
                content="Convergence stall detected (similarity 0.35)",
                timestamp="2026-03-19T10:05:00Z",
                event_kind="governance",
            ),
        ]
        audit = build_colony_audit_view(colony)
        assert len(audit["governance_actions"]) == 1
        assert "stall" in audit["governance_actions"][0]["content"]

    def test_escalation_from_routing_override(self) -> None:
        colony = _make_colony()
        colony.routing_override = {
            "tier": "heavy",
            "reason": "auto_escalated_on_stall",
            "set_at_round": 3,
        }
        audit = build_colony_audit_view(colony)
        assert audit["escalation"] is not None
        assert audit["escalation"]["tier"] == "heavy"
        assert audit["escalation"]["reason"] == "auto_escalated_on_stall"
        assert audit["escalation"]["set_at_round"] == 3

    def test_no_escalation_when_none(self) -> None:
        colony = _make_colony()
        audit = build_colony_audit_view(colony)
        assert audit["escalation"] is None

    def test_validator_in_audit(self) -> None:
        colony = _make_colony(
            validator_verdict="pass",
            validator_task_type="code",
            validator_reason="verified_execution",
        )
        audit = build_colony_audit_view(colony)
        assert audit["validator"] is not None
        assert audit["validator"]["verdict"] == "pass"
        assert audit["validator"]["task_type"] == "code"
        assert audit["validator"]["reason"] == "verified_execution"

    def test_no_validator_when_none(self) -> None:
        colony = _make_colony()
        audit = build_colony_audit_view(colony)
        assert audit["validator"] is None

    def test_completion_state_validated(self) -> None:
        colony = _make_colony(status="completed", validator_verdict="pass")
        audit = build_colony_audit_view(colony)
        assert audit["completion_state"] == "validated"

    def test_completion_state_unvalidated(self) -> None:
        colony = _make_colony(status="completed")
        audit = build_colony_audit_view(colony)
        assert audit["completion_state"] == "unvalidated"

    def test_completion_state_stalled(self) -> None:
        colony = _make_colony(status="failed")
        audit = build_colony_audit_view(colony)
        assert audit["completion_state"] == "stalled"

    def test_redirects_included(self) -> None:
        colony = _make_colony()
        colony.redirect_history = [
            {"round": 3, "reason": "off_track", "new_goal": "Revised goal"},
        ]
        audit = build_colony_audit_view(colony)
        assert len(audit["redirects"]) == 1

    def test_empty_colony_has_valid_structure(self) -> None:
        """Even an empty colony produces a valid audit view."""
        colony = _make_colony(status="running")
        audit = build_colony_audit_view(colony)
        assert audit["knowledge_used"] == []
        assert audit["directives"] == []
        assert audit["governance_actions"] == []
        assert audit["escalation"] is None
        assert audit["redirects"] == []
        assert audit["validator"] is None
        assert audit["completion_state"] == "running"


# ---------------------------------------------------------------------------
# ColonyOutcome validator fields
# ---------------------------------------------------------------------------


class TestOutcomeValidatorFields:
    """Verify validator fields flow into ColonyOutcome."""

    def test_validator_fields_on_outcome(self) -> None:
        from formicos.surface.projections import (
            ProjectionStore,
            _build_colony_outcome,
        )

        colony = _make_colony(
            status="completed",
            validator_verdict="pass",
            validator_task_type="code",
        )
        store = ProjectionStore()
        store.colonies[colony.id] = colony
        _build_colony_outcome(
            store, colony, succeeded=True,
            end_ts="2026-03-19T10:30:00Z",
        )
        outcome = store.colony_outcomes[colony.id]
        assert outcome.validator_verdict == "pass"
        assert outcome.validator_task_type == "code"

    def test_no_validator_fields_when_none(self) -> None:
        from formicos.surface.projections import (
            ProjectionStore,
            _build_colony_outcome,
        )

        colony = _make_colony(status="completed")
        store = ProjectionStore()
        store.colonies[colony.id] = colony
        _build_colony_outcome(
            store, colony, succeeded=True,
            end_ts="2026-03-19T10:30:00Z",
        )
        outcome = store.colony_outcomes[colony.id]
        assert outcome.validator_verdict is None
        assert outcome.validator_task_type is None
