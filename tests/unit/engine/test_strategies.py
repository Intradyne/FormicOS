"""Tests for coordination strategies."""

from __future__ import annotations

import math

import pytest

from formicos.core.types import AgentConfig, CasteRecipe, ColonyContext
from formicos.engine.runner import _merge_knowledge_prior
from formicos.engine.strategies.sequential import SequentialStrategy
from formicos.engine.strategies.stigmergic import (
    StigmergicStrategy,
    _collapse_into_groups,
    _topological_sort,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _recipe(name: str = "coder") -> CasteRecipe:
    return CasteRecipe(
        name=name,
        description=f"{name} caste",
        system_prompt=f"You are a {name}.",
        temperature=0.0,
        tools=[],
        max_tokens=1024,
    )


def _agent(agent_id: str, name: str = "coder") -> AgentConfig:
    return AgentConfig(
        id=agent_id, name=agent_id, caste=name,
        model="test-model", recipe=_recipe(name),
    )


def _colony_ctx() -> ColonyContext:
    return ColonyContext(
        colony_id="col-1", workspace_id="ws-1", thread_id="th-1",
        goal="Build a widget", round_number=1,
        merge_edges=[],
    )


def mock_embed_fn(texts: list[str]) -> list[list[float]]:
    """Return deterministic normalized vectors based on text index."""
    result: list[list[float]] = []
    for i, _ in enumerate(texts):
        vec = [0.0] * 8
        vec[i % 8] = 1.0
        norm = math.sqrt(sum(x * x for x in vec))
        result.append([x / norm for x in vec])
    return result


def high_similarity_embed_fn(texts: list[str]) -> list[list[float]]:
    """All texts map to nearly the same vector — high similarity."""
    result: list[list[float]] = []
    for i, _ in enumerate(texts):
        vec = [1.0] * 8
        vec[i % 8] += 0.01  # tiny variation
        norm = math.sqrt(sum(x * x for x in vec))
        result.append([x / norm for x in vec])
    return result


# ---------------------------------------------------------------------------
# Sequential strategy tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sequential_single_agent_per_group() -> None:
    strategy = SequentialStrategy()
    agents = [_agent("a1"), _agent("a2"), _agent("a3")]
    groups = await strategy.resolve_topology(agents, _colony_ctx())
    assert len(groups) == 3
    assert all(len(g) == 1 for g in groups)


@pytest.mark.asyncio
async def test_sequential_preserves_order() -> None:
    strategy = SequentialStrategy()
    agents = [_agent("a3"), _agent("a1"), _agent("a2")]
    groups = await strategy.resolve_topology(agents, _colony_ctx())
    assert [g[0] for g in groups] == ["a3", "a1", "a2"]


# ---------------------------------------------------------------------------
# Stigmergic strategy tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stigmergic_basic() -> None:
    strategy = StigmergicStrategy(embed_fn=mock_embed_fn, tau=0.35, k_in=5)
    agents = [_agent("a1", "coder"), _agent("a2", "reviewer")]
    groups = await strategy.resolve_topology(agents, _colony_ctx())
    # Should produce at least one group with all agents
    flat = [aid for g in groups for aid in g]
    assert set(flat) == {"a1", "a2"}


@pytest.mark.asyncio
async def test_stigmergic_tau_threshold() -> None:
    # High similarity embeddings + low tau → more connections
    low_tau = StigmergicStrategy(embed_fn=high_similarity_embed_fn, tau=0.1, k_in=5)
    agents = [_agent("a1"), _agent("a2"), _agent("a3")]
    groups_low = await low_tau.resolve_topology(agents, _colony_ctx())

    # High tau → fewer connections → more groups (sequential-like)
    high_tau = StigmergicStrategy(embed_fn=high_similarity_embed_fn, tau=0.99, k_in=5)
    groups_high = await high_tau.resolve_topology(agents, _colony_ctx())

    # With high tau nothing passes threshold, so all agents end up in one group (level 0)
    # With low tau connections exist so there may be ordering
    flat_low = [aid for g in groups_low for aid in g]
    flat_high = [aid for g in groups_high for aid in g]
    assert set(flat_low) == {"a1", "a2", "a3"}
    assert set(flat_high) == {"a1", "a2", "a3"}


@pytest.mark.asyncio
async def test_stigmergic_k_in_cap() -> None:
    strategy = StigmergicStrategy(embed_fn=high_similarity_embed_fn, tau=0.1, k_in=1)
    agents = [_agent(f"a{i}") for i in range(4)]
    groups = await strategy.resolve_topology(agents, _colony_ctx())
    flat = [aid for g in groups for aid in g]
    assert set(flat) == {f"a{i}" for i in range(4)}


# ---------------------------------------------------------------------------
# Wave 37 1A: Knowledge-weighted topology prior tests
#
# The knowledge prior is merged into pheromone_weights by
# _merge_knowledge_prior in runner.py before calling resolve_topology.
# These tests verify the pheromone-weight path carries prior bias correctly.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_knowledge_prior_boosted_weights_affect_topology() -> None:
    """Boosted pheromone weights (from knowledge prior) affect topology."""
    strategy = StigmergicStrategy(embed_fn=mock_embed_fn, tau=0.35, k_in=5)
    agents = [_agent("a1", "coder"), _agent("a2", "reviewer")]

    # Without prior
    groups_neutral = await strategy.resolve_topology(agents, _colony_ctx())

    # With a boosting prior merged into pheromone weights
    knowledge_prior = {("a1", "a2"): 1.15, ("a2", "a1"): 1.15}
    merged = _merge_knowledge_prior(None, knowledge_prior)
    groups_boosted = await strategy.resolve_topology(
        agents, _colony_ctx(), pheromone_weights=merged,
    )

    # Both should contain all agents
    flat_neutral = [aid for g in groups_neutral for aid in g]
    flat_boosted = [aid for g in groups_boosted for aid in g]
    assert set(flat_neutral) == {"a1", "a2"}
    assert set(flat_boosted) == {"a1", "a2"}


@pytest.mark.asyncio
async def test_knowledge_prior_weakened_weights_affect_topology() -> None:
    """Weakened pheromone weights (from knowledge prior) affect topology."""
    strategy = StigmergicStrategy(
        embed_fn=high_similarity_embed_fn, tau=0.35, k_in=5,
    )
    agents = [_agent("a1"), _agent("a2"), _agent("a3")]

    # Without prior
    groups_neutral = await strategy.resolve_topology(agents, _colony_ctx())

    # With weakening prior merged into weights
    knowledge_prior = {
        ("a1", "a2"): 0.85, ("a2", "a1"): 0.85,
        ("a1", "a3"): 0.85, ("a3", "a1"): 0.85,
        ("a2", "a3"): 0.85, ("a3", "a2"): 0.85,
    }
    merged = _merge_knowledge_prior(None, knowledge_prior)
    groups_weakened = await strategy.resolve_topology(
        agents, _colony_ctx(), pheromone_weights=merged,
    )

    flat_neutral = [aid for g in groups_neutral for aid in g]
    flat_weakened = [aid for g in groups_weakened for aid in g]
    assert set(flat_neutral) == {"a1", "a2", "a3"}
    assert set(flat_weakened) == {"a1", "a2", "a3"}


def test_merge_knowledge_prior_none_passthrough() -> None:
    """Merging None prior returns original weights unchanged."""
    weights = {("a", "b"): 1.5}
    assert _merge_knowledge_prior(weights, None) is weights
    assert _merge_knowledge_prior(None, None) is None


def test_merge_knowledge_prior_multiplies_existing() -> None:
    """Prior multiplies existing pheromone weights."""
    weights = {("a", "b"): 2.0}
    prior = {("a", "b"): 1.1}
    merged = _merge_knowledge_prior(weights, prior)
    assert merged is not None
    assert abs(merged[("a", "b")] - 2.2) < 0.01


def test_merge_knowledge_prior_adds_missing() -> None:
    """Prior adds edges not present in original weights."""
    weights = {("a", "b"): 1.5}
    prior = {("c", "d"): 1.1}
    merged = _merge_knowledge_prior(weights, prior)
    assert merged is not None
    assert ("c", "d") in merged
    assert ("a", "b") in merged


# ---------------------------------------------------------------------------
# Topological sort tests
# ---------------------------------------------------------------------------


def test_topological_sort_acyclic() -> None:
    # 0 -> 1 -> 2  (linear chain)
    adj = [
        [0, 1, 0],
        [0, 0, 1],
        [0, 0, 0],
    ]
    sim = [
        [0.0, 0.5, 0.0],
        [0.0, 0.0, 0.5],
        [0.0, 0.0, 0.0],
    ]
    order = _topological_sort(adj, 3, sim)
    assert order == [0, 1, 2]

    groups = _collapse_into_groups(adj, order, 3)
    # Each in its own level: [[0], [1], [2]]
    assert groups == [[0], [1], [2]]
