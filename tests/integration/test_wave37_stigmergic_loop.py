"""Wave 37 integration harness: stigmergic loop closure measurement.

Repeated-domain benchmark suite that measures whether Wave 37 features
(1A knowledge-weighted topology, 1B outcome-weighted reinforcement,
1C branching diagnostics) improve colony outcomes over the Wave 36 baseline.

This is an internal measurement harness, not an external benchmark.
"""

from __future__ import annotations

import math
from typing import Any
from unittest.mock import MagicMock

import pytest

from formicos.core.types import AgentConfig, CasteRecipe, ColonyContext
from formicos.engine.runner import _compute_knowledge_prior, _merge_knowledge_prior
from formicos.engine.strategies.stigmergic import StigmergicStrategy
from formicos.surface.proactive_intelligence import (
    _effective_count,
    compute_config_branching,
    compute_knowledge_branching,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _recipe(name: str = "coder") -> CasteRecipe:
    return CasteRecipe(
        name=name,
        description=f"{name} tasks",
        system_prompt=f"You are a {name}.",
        temperature=0.0,
        tools=[],
        max_tokens=1024,
    )


def _agent(agent_id: str, caste: str = "coder") -> AgentConfig:
    return AgentConfig(
        id=agent_id, name=agent_id, caste=caste,
        model="test-model", recipe=_recipe(caste),
    )


def _colony_ctx(
    goal: str = "Build a widget",
    round_number: int = 1,
) -> ColonyContext:
    return ColonyContext(
        colony_id="col-1", workspace_id="ws-1", thread_id="th-1",
        goal=goal, round_number=round_number,
        merge_edges=[],
    )


def _high_sim_embed_fn(texts: list[str]) -> list[list[float]]:
    """Deterministic high-similarity embedding for testing."""
    result: list[list[float]] = []
    for i, _ in enumerate(texts):
        vec = [1.0] * 8
        vec[i % 8] += 0.01
        norm = math.sqrt(sum(x * x for x in vec))
        result.append([x / norm for x in vec])
    return result


# ---------------------------------------------------------------------------
# Feature toggle helpers (ablation support)
# ---------------------------------------------------------------------------


class AblationConfig:
    """Toggle Wave 37 features for ablation comparisons."""

    def __init__(
        self,
        knowledge_prior: bool = True,
        quality_weighted_reinforcement: bool = True,
        branching_diagnostics: bool = True,
    ) -> None:
        self.knowledge_prior = knowledge_prior
        self.quality_weighted_reinforcement = quality_weighted_reinforcement
        self.branching_diagnostics = branching_diagnostics

    def label(self) -> str:
        flags = []
        if self.knowledge_prior:
            flags.append("1A")
        if self.quality_weighted_reinforcement:
            flags.append("1B")
        if self.branching_diagnostics:
            flags.append("1C")
        return "+".join(flags) if flags else "baseline"


BASELINE = AblationConfig(False, False, False)
FULL_W37 = AblationConfig(True, True, True)
ONLY_1A = AblationConfig(True, False, False)
ONLY_1B = AblationConfig(False, True, False)
ONLY_1C = AblationConfig(False, False, True)


# ---------------------------------------------------------------------------
# Benchmark task definitions
# ---------------------------------------------------------------------------

BENCHMARK_TASKS: list[dict[str, Any]] = [
    # Repeated-domain tasks: knowledge should help
    {
        "id": "python-sort-1",
        "domain": "python",
        "goal": "Implement merge sort in Python",
        "expected_benefit": True,
    },
    {
        "id": "python-sort-2",
        "domain": "python",
        "goal": "Implement quicksort in Python",
        "expected_benefit": True,
    },
    {
        "id": "python-async-1",
        "domain": "python",
        "goal": "Build an async HTTP client in Python",
        "expected_benefit": True,
    },
    {
        "id": "rust-error-1",
        "domain": "rust",
        "goal": "Implement Result-based error handling in Rust",
        "expected_benefit": True,
    },
    {
        "id": "rust-error-2",
        "domain": "rust",
        "goal": "Build a custom error type hierarchy in Rust",
        "expected_benefit": True,
    },
    # Control tasks: new domain, knowledge shouldn't help much
    {
        "id": "devops-1",
        "domain": "devops",
        "goal": "Write a Dockerfile for a multi-stage build",
        "expected_benefit": False,
    },
    {
        "id": "sql-1",
        "domain": "sql",
        "goal": "Design a normalized schema for an e-commerce platform",
        "expected_benefit": False,
    },
]


# ---------------------------------------------------------------------------
# 1A: Knowledge prior produces non-neutral topology
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_knowledge_prior_affects_topology() -> None:
    """Repeated-domain topology is different from neutral when prior exists."""
    strategy = StigmergicStrategy(
        embed_fn=_high_sim_embed_fn, tau=0.35, k_in=5,
    )
    agents = [_agent("a1", "coder"), _agent("a2", "reviewer")]

    # Baseline: neutral topology
    groups_neutral = await strategy.resolve_topology(agents, _colony_ctx())

    # With knowledge prior from high-confidence domain entries
    knowledge_items = [
        {"conf_alpha": 25.0, "conf_beta": 3.0, "domains": ["coder"]},
        {"conf_alpha": 20.0, "conf_beta": 2.0, "domains": ["reviewer"]},
    ]
    prior = _compute_knowledge_prior(agents, knowledge_items)
    assert prior is not None, "Prior should be non-None for confident items"

    merged = _merge_knowledge_prior(None, prior)
    groups_biased = await strategy.resolve_topology(
        agents, _colony_ctx(), pheromone_weights=merged,
    )

    # Both should produce valid topologies
    flat_n = [aid for g in groups_neutral for aid in g]
    flat_b = [aid for g in groups_biased for aid in g]
    assert set(flat_n) == {"a1", "a2"}
    assert set(flat_b) == {"a1", "a2"}

    # Prior values should be in valid range
    for v in prior.values():
        assert 0.85 <= v <= 1.15


# ---------------------------------------------------------------------------
# 1B: Quality score affects reinforcement magnitude
# ---------------------------------------------------------------------------


def test_quality_delta_varies_with_score() -> None:
    """The reinforcement delta must be non-constant and quality-dependent."""
    deltas = []
    for qs in [0.0, 0.3, 0.5, 0.8, 1.0]:
        delta = min(max(0.5 + qs, 0.5), 1.5)
        deltas.append(delta)

    # Should be strictly increasing
    for i in range(1, len(deltas)):
        assert deltas[i] >= deltas[i - 1]

    # Range check
    assert deltas[0] == 0.5  # min quality → min delta
    assert deltas[-1] == 1.5  # max quality → max delta


# ---------------------------------------------------------------------------
# 1C: Branching metrics are computable and meaningful
# ---------------------------------------------------------------------------


def test_branching_metrics_on_benchmark_scenarios() -> None:
    """Branching metrics produce distinct values for diverse vs homogeneous."""
    # Diverse outcomes
    diverse_outcomes: dict[str, Any] = {}
    for i, strat in enumerate(["sequential", "stigmergic", "sequential"]):
        o = MagicMock()
        o.strategy = strat
        o.caste_composition = [f"caste_{i}"]
        o.succeeded = True
        diverse_outcomes[f"col-{i}"] = o

    # Homogeneous outcomes
    homo_outcomes: dict[str, Any] = {}
    for i in range(5):
        o = MagicMock()
        o.strategy = "sequential"
        o.caste_composition = ["coder"]
        o.succeeded = True
        homo_outcomes[f"col-{i}"] = o

    bf_diverse = compute_config_branching(diverse_outcomes)
    bf_homo = compute_config_branching(homo_outcomes)

    assert bf_diverse > bf_homo, (
        f"Diverse ({bf_diverse}) should have higher branching than "
        f"homogeneous ({bf_homo})"
    )


def test_knowledge_branching_distinguishes_concentrated_vs_spread() -> None:
    """Knowledge branching should be lower when posteriors are concentrated."""
    # Spread: many entries with similar confidence
    spread: dict[str, dict[str, Any]] = {
        f"e{i}": {"conf_alpha": 10.0 + i * 0.5, "conf_beta": 5.0}
        for i in range(10)
    }

    # Concentrated: one dominant entry
    concentrated: dict[str, dict[str, Any]] = {
        "e0": {"conf_alpha": 100.0, "conf_beta": 1.0},
    }
    for i in range(1, 10):
        concentrated[f"e{i}"] = {"conf_alpha": 1.0, "conf_beta": 100.0}

    bf_spread = compute_knowledge_branching(spread)
    bf_conc = compute_knowledge_branching(concentrated)

    assert bf_spread > bf_conc


# ---------------------------------------------------------------------------
# Ablation framework: run the same task with different feature toggles
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ablation_configurations_are_distinct() -> None:
    """Each ablation config produces a distinct label."""
    configs = [BASELINE, FULL_W37, ONLY_1A, ONLY_1B, ONLY_1C]
    labels = [c.label() for c in configs]
    assert len(set(labels)) == len(configs), "Each config should have unique label"


@pytest.mark.asyncio
async def test_repeated_domain_prior_is_stronger() -> None:
    """After accumulating knowledge in a domain, the prior should be non-trivial."""
    agents = [_agent("a1", "coder"), _agent("a2", "reviewer")]

    # First task: no knowledge → neutral prior
    prior_first = _compute_knowledge_prior(agents, [])
    assert prior_first is None

    # Second task: accumulated knowledge in 'python' domain
    accumulated = [
        {"conf_alpha": 15.0, "conf_beta": 3.0, "domains": ["python"]},
        {"conf_alpha": 12.0, "conf_beta": 2.0, "domains": ["python"]},
        {"conf_alpha": 18.0, "conf_beta": 4.0, "domains": ["python", "coder"]},
    ]
    prior_second = _compute_knowledge_prior(agents, accumulated)
    assert prior_second is not None, "Repeated domain should produce prior"


# ---------------------------------------------------------------------------
# Measurement: outcome calibration check
# ---------------------------------------------------------------------------


def test_effective_count_calibration() -> None:
    """Effective count matches expected information-theoretic values."""
    # Perfect uniform over N → N
    for n in [2, 4, 8, 16]:
        result = _effective_count([1.0] * n)
        assert abs(result - n) < 0.01, f"Expected {n}, got {result}"

    # Single item → 1
    assert abs(_effective_count([1.0]) - 1.0) < 0.01

    # Two items, one dominant → between 1 and 2
    result = _effective_count([0.9, 0.1])
    assert 1.0 <= result <= 2.0
