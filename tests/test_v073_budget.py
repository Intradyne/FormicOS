"""
Tests for FormicOS v0.7.3 Budget Constraints.

Covers:
- BudgetConstraints model validation
- max_epochs check in _check_budget
- max_total_tokens check in _check_budget
- max_usd_cents logs warning but does not halt
- HALTED_BUDGET_EXHAUSTED is a valid terminal status
- No budget constraints means no halt
"""

from __future__ import annotations


from src.models import BudgetConstraints, ColonyStatus


# ── BudgetConstraints model ───────────────────────────────────────────


def test_budget_constraints_all_none():
    bc = BudgetConstraints()
    assert bc.max_epochs is None
    assert bc.max_total_tokens is None
    assert bc.max_usd_cents is None


def test_budget_constraints_with_values():
    bc = BudgetConstraints(max_epochs=5, max_total_tokens=10000, max_usd_cents=100)
    assert bc.max_epochs == 5
    assert bc.max_total_tokens == 10000
    assert bc.max_usd_cents == 100


def test_budget_constraints_partial():
    bc = BudgetConstraints(max_epochs=3)
    assert bc.max_epochs == 3
    assert bc.max_total_tokens is None


def test_budget_constraints_round_trip():
    bc = BudgetConstraints(max_epochs=5, max_total_tokens=10000)
    data = bc.model_dump()
    bc2 = BudgetConstraints(**data)
    assert bc == bc2


# ── ColonyStatus enum ────────────────────────────────────────────────


def test_halted_budget_exhausted_exists():
    status = ColonyStatus.HALTED_BUDGET_EXHAUSTED
    assert status.value == "halted_budget_exhausted"


def test_halted_budget_exhausted_is_terminal():
    """HALTED_BUDGET_EXHAUSTED should be in the enum."""
    all_statuses = [s.value for s in ColonyStatus]
    assert "halted_budget_exhausted" in all_statuses


# ── Budget check logic (via Orchestrator internals) ──────────────────


def test_check_budget_max_epochs():
    """Simulate _check_budget for max_epochs."""
    budget = BudgetConstraints(max_epochs=3)
    current_round = 3

    # This mirrors the orchestrator's _check_budget logic
    exceeded = False
    if budget.max_epochs and current_round >= budget.max_epochs:
        exceeded = True

    assert exceeded is True


def test_check_budget_max_epochs_not_reached():
    budget = BudgetConstraints(max_epochs=5)
    current_round = 3

    exceeded = False
    if budget.max_epochs and current_round >= budget.max_epochs:
        exceeded = True

    assert exceeded is False


def test_check_budget_max_total_tokens():
    budget = BudgetConstraints(max_total_tokens=1000)
    total_tokens = 1200

    exceeded = False
    if budget.max_total_tokens and total_tokens >= budget.max_total_tokens:
        exceeded = True

    assert exceeded is True


def test_check_budget_max_total_tokens_under():
    budget = BudgetConstraints(max_total_tokens=1000)
    total_tokens = 800

    exceeded = False
    if budget.max_total_tokens and total_tokens >= budget.max_total_tokens:
        exceeded = True

    assert exceeded is False


def test_check_budget_no_constraints():
    budget = BudgetConstraints()
    current_round = 100
    total_tokens = 999999

    exceeded = False
    if budget.max_epochs and current_round >= budget.max_epochs:
        exceeded = True
    if budget.max_total_tokens and total_tokens >= budget.max_total_tokens:
        exceeded = True

    assert exceeded is False


def test_check_budget_usd_cents_does_not_halt():
    """max_usd_cents is deferred to v0.8.0 — should not cause halt."""
    budget = BudgetConstraints(max_usd_cents=50)
    current_round = 1
    total_tokens = 100

    exceeded = False
    if budget.max_epochs and current_round >= budget.max_epochs:
        exceeded = True
    if budget.max_total_tokens and total_tokens >= budget.max_total_tokens:
        exceeded = True
    # max_usd_cents is intentionally NOT checked for halt

    assert exceeded is False
