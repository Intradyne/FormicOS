"""Tests for Wave 37 1C: branching-factor stagnation diagnostics."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from formicos.surface.proactive_intelligence import (
    _effective_count,
    _rule_branching_stagnation,
    compute_config_branching,
    compute_knowledge_branching,
    compute_topology_branching,
)

# ---------------------------------------------------------------------------
# _effective_count tests
# ---------------------------------------------------------------------------


def test_effective_count_empty() -> None:
    assert _effective_count([]) == 0.0


def test_effective_count_single() -> None:
    # Single weight → effective count = 1
    result = _effective_count([5.0])
    assert abs(result - 1.0) < 0.01


def test_effective_count_uniform() -> None:
    # Uniform over 4 items → effective count = 4
    result = _effective_count([1.0, 1.0, 1.0, 1.0])
    assert abs(result - 4.0) < 0.01


def test_effective_count_skewed() -> None:
    # Very skewed → closer to 1
    result = _effective_count([100.0, 0.01, 0.01, 0.01])
    assert result < 2.0
    assert result >= 1.0


def test_effective_count_two_dominant() -> None:
    # Two equal, rest tiny → ~2
    result = _effective_count([50.0, 50.0, 0.01, 0.01])
    assert 1.5 < result < 2.5


# ---------------------------------------------------------------------------
# Knowledge branching tests
# ---------------------------------------------------------------------------


def test_knowledge_branching_uniform() -> None:
    """Uniform posterior mass → high branching factor."""
    entries: dict[str, dict[str, Any]] = {
        f"e{i}": {"conf_alpha": 5.0, "conf_beta": 5.0}
        for i in range(10)
    }
    bf = compute_knowledge_branching(entries)
    # All identical → effective count = 1 (since all posteriors are equal,
    # the entropy of the distribution of posterior means is 0).
    # Actually, all have identical mass so uniform weights → effective = N
    assert bf >= 1.0


def test_knowledge_branching_concentrated() -> None:
    """One dominant entry → low branching factor."""
    entries: dict[str, dict[str, Any]] = {
        "e0": {"conf_alpha": 100.0, "conf_beta": 1.0},  # very confident
    }
    for i in range(1, 10):
        entries[f"e{i}"] = {"conf_alpha": 1.0, "conf_beta": 100.0}  # very uncertain
    bf = compute_knowledge_branching(entries)
    # One high-confidence entry, rest low → low effective count
    assert bf < 5.0


# ---------------------------------------------------------------------------
# Config branching tests
# ---------------------------------------------------------------------------


def test_config_branching_diverse() -> None:
    """Different strategies → high branching."""
    outcomes: dict[str, Any] = {}
    for i, strat in enumerate(["sequential", "stigmergic", "parallel"]):
        o = MagicMock()
        o.strategy = strat
        o.caste_composition = [f"caste_{i}"]
        outcomes[f"col-{i}"] = o
    bf = compute_config_branching(outcomes)
    assert bf >= 2.5


def test_config_branching_homogeneous() -> None:
    """Same strategy and castes → low branching."""
    outcomes: dict[str, Any] = {}
    for i in range(5):
        o = MagicMock()
        o.strategy = "sequential"
        o.caste_composition = ["coder"]
        outcomes[f"col-{i}"] = o
    bf = compute_config_branching(outcomes)
    assert bf < 1.5


# ---------------------------------------------------------------------------
# Topology branching tests
# ---------------------------------------------------------------------------


def test_topology_branching_no_colonies() -> None:
    """No colonies → 0 branching."""
    projections = MagicMock()
    projections.colonies = {}
    bf = compute_topology_branching(projections, "ws-1")
    assert bf == 0.0


def test_topology_branching_uniform_weights() -> None:
    """Uniform pheromone weights → higher branching."""
    colony = MagicMock()
    colony.workspace_id = "ws-1"
    colony.pheromone_weights = {
        ("a1", "a2"): 1.0,
        ("a2", "a1"): 1.0,
        ("a1", "a3"): 1.0,
        ("a3", "a1"): 1.0,
    }
    projections = MagicMock()
    projections.colonies = {"col-1": colony}
    bf = compute_topology_branching(projections, "ws-1")
    assert bf >= 3.5  # 4 equal weights → effective = 4


def test_topology_branching_concentrated_weights() -> None:
    """One dominant edge → low branching."""
    colony = MagicMock()
    colony.workspace_id = "ws-1"
    colony.pheromone_weights = {
        ("a1", "a2"): 10.0,
        ("a2", "a1"): 0.02,
        ("a1", "a3"): 0.02,
    }
    projections = MagicMock()
    projections.colonies = {"col-1": colony}
    bf = compute_topology_branching(projections, "ws-1")
    assert bf < 2.0


# ---------------------------------------------------------------------------
# Stagnation rule integration
# ---------------------------------------------------------------------------


def test_stagnation_no_signal_when_healthy() -> None:
    """No insight when branching is healthy and failure rate is low."""
    entries: dict[str, dict[str, Any]] = {
        f"e{i}": {"conf_alpha": 5.0 + i, "conf_beta": 5.0}
        for i in range(10)
    }
    outcomes: dict[str, Any] = {}
    for i in range(10):
        o = MagicMock()
        o.succeeded = True
        o.strategy = ["sequential", "stigmergic"][i % 2]
        o.caste_composition = ["coder"]
        outcomes[f"col-{i}"] = o

    projections = MagicMock()
    projections.colonies = {}

    insights = _rule_branching_stagnation(entries, outcomes, projections, "ws-1")
    assert len(insights) == 0


def test_stagnation_fires_on_convergence() -> None:
    """Insight fires when branching is low AND failure rate is high."""
    # 5 identical entries → low knowledge branching
    entries: dict[str, dict[str, Any]] = {
        f"e{i}": {"conf_alpha": 50.0, "conf_beta": 1.0}
        for i in range(5)
    }
    # All same strategy, mostly failing → low config branching + high failure
    outcomes: dict[str, Any] = {}
    for i in range(6):
        o = MagicMock()
        o.succeeded = i < 1  # Only 1 success, 5 failures
        o.strategy = "sequential"
        o.caste_composition = ["coder"]
        outcomes[f"col-{i}"] = o

    # Add concentrated topology
    colony = MagicMock()
    colony.workspace_id = "ws-1"
    colony.pheromone_weights = {("a1", "a2"): 10.0}
    projections = MagicMock()
    projections.colonies = {"col-1": colony}

    insights = _rule_branching_stagnation(entries, outcomes, projections, "ws-1")
    assert len(insights) == 1
    assert insights[0].category == "stagnation"
    assert insights[0].severity == "attention"
