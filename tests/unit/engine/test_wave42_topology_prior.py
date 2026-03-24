"""Tests for Wave 42 structural topology prior (Pillar 2)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from formicos.engine.runner import (
    _PRIOR_MAX,
    _PRIOR_MIN,
    _compute_domain_affinity,
    _compute_knowledge_prior,
    _compute_structural_affinity,
    _uniform_knowledge_fallback,
)


def _make_agent(agent_id: str, caste: str = "coder") -> MagicMock:
    agent = MagicMock()
    agent.id = agent_id
    agent.caste = caste
    recipe = MagicMock()
    recipe.name = caste
    agent.recipe = recipe
    return agent


def _make_knowledge_item(
    domains: list[str],
    alpha: float = 8.0,
    beta: float = 2.0,
) -> dict:
    return {
        "domains": domains,
        "conf_alpha": alpha,
        "conf_beta": beta,
    }


class TestComputeKnowledgePrior:
    """Tests for the unified prior computation."""

    def test_no_items_returns_none(self) -> None:
        agents = [_make_agent("a1"), _make_agent("a2")]
        assert _compute_knowledge_prior(agents, None) is None
        assert _compute_knowledge_prior(agents, []) is None

    def test_structural_deps_produce_prior(self) -> None:
        agents = [_make_agent("a1"), _make_agent("a2")]
        structural_deps = {
            "src/auth.py": ["src/db.py"],
            "src/db.py": [],
        }
        prior = _compute_knowledge_prior(
            agents, None,
            structural_deps=structural_deps,
            target_files=["src/auth.py"],
        )
        assert prior is not None
        for edge, val in prior.items():
            assert _PRIOR_MIN <= val <= _PRIOR_MAX

    def test_structural_deps_without_target_files_neutral(self) -> None:
        agents = [_make_agent("a1"), _make_agent("a2")]
        structural_deps = {"src/a.py": ["src/b.py"]}
        # No target_files → structural affinity is empty → falls back
        prior = _compute_knowledge_prior(
            agents, None,
            structural_deps=structural_deps,
            target_files=[],
        )
        assert prior is None

    def test_both_signals_blend(self) -> None:
        agents = [_make_agent("a1", "coder"), _make_agent("a2", "reviewer")]
        items = [_make_knowledge_item(["coder"], alpha=9.0, beta=1.0)]
        structural_deps = {"src/a.py": ["src/b.py"]}
        target_files = ["src/a.py"]

        prior = _compute_knowledge_prior(
            agents, items,
            structural_deps=structural_deps,
            target_files=target_files,
        )
        assert prior is not None
        # With both signals, prior should be non-neutral
        vals = list(prior.values())
        assert any(v > _PRIOR_MIN for v in vals)

    def test_fallback_to_domain_only(self) -> None:
        """Without structural deps, falls back to domain affinity."""
        agents = [_make_agent("a1", "coder"), _make_agent("a2", "reviewer")]
        items = [_make_knowledge_item(["coder"], alpha=9.0, beta=1.0)]

        prior = _compute_knowledge_prior(agents, items)
        assert prior is not None
        # Coder agent should have higher affinity edge
        assert prior[("a1", "a2")] > _PRIOR_MIN or prior[("a2", "a1")] > _PRIOR_MIN

    def test_prior_values_bounded(self) -> None:
        agents = [_make_agent("a1"), _make_agent("a2"), _make_agent("a3")]
        items = [_make_knowledge_item(["testing"], alpha=20.0, beta=1.0)]
        structural_deps = {
            "src/a.py": ["src/b.py", "src/c.py"],
            "src/b.py": ["src/c.py"],
        }
        prior = _compute_knowledge_prior(
            agents, items,
            structural_deps=structural_deps,
            target_files=["src/a.py", "src/b.py"],
        )
        assert prior is not None
        for val in prior.values():
            assert _PRIOR_MIN <= val <= _PRIOR_MAX


class TestStructuralAffinity:
    def test_connected_files_boost(self) -> None:
        agents = [_make_agent("a1"), _make_agent("a2")]
        deps = {"src/auth.py": ["src/db.py", "src/utils.py"]}
        result = _compute_structural_affinity(
            agents, deps, ["src/auth.py"],
        )
        assert len(result) == 2
        for v in result.values():
            assert v > 0.0

    def test_no_deps_empty(self) -> None:
        agents = [_make_agent("a1")]
        result = _compute_structural_affinity(agents, None, ["src/a.py"])
        assert result == {}

    def test_no_target_files_empty(self) -> None:
        agents = [_make_agent("a1")]
        result = _compute_structural_affinity(agents, {"a": ["b"]}, [])
        assert result == {}

    def test_unconnected_target(self) -> None:
        agents = [_make_agent("a1")]
        deps = {"src/other.py": ["src/unrelated.py"]}
        result = _compute_structural_affinity(agents, deps, ["src/target.py"])
        assert all(v == 0.0 for v in result.values()) or result == {}


class TestDomainAffinity:
    def test_caste_overlap(self) -> None:
        agents = [_make_agent("a1", "coder")]
        items = [_make_knowledge_item(["coder"], alpha=9.0, beta=1.0)]
        result = _compute_domain_affinity(agents, items)
        assert result["a1"] > 0.5

    def test_no_overlap(self) -> None:
        agents = [_make_agent("a1", "coder")]
        items = [_make_knowledge_item(["security"], alpha=9.0, beta=1.0)]
        result = _compute_domain_affinity(agents, items)
        assert result["a1"] < 0.01

    def test_no_items(self) -> None:
        agents = [_make_agent("a1")]
        result = _compute_domain_affinity(agents, None)
        assert result == {}

    def test_low_certainty_filtered(self) -> None:
        agents = [_make_agent("a1", "coder")]
        items = [_make_knowledge_item(["coder"], alpha=1.0, beta=1.0)]  # alpha+beta=2 < 3
        result = _compute_domain_affinity(agents, items)
        assert result.get("a1", 0.0) < 0.01


class TestUniformFallback:
    def test_high_confidence_uniform(self) -> None:
        agents = [_make_agent("a1"), _make_agent("a2")]
        items = [_make_knowledge_item(["unknown_domain"], alpha=9.0, beta=1.0)]
        result = _uniform_knowledge_fallback(agents, items)
        assert result is not None
        assert len(result) == 2  # 2 edges (2 agents, exclude self)
        for v in result.values():
            assert _PRIOR_MIN <= v <= _PRIOR_MAX

    def test_low_confidence_returns_none(self) -> None:
        agents = [_make_agent("a1"), _make_agent("a2")]
        items = [_make_knowledge_item(["x"], alpha=3.0, beta=7.0)]  # mean=0.3 < 0.6
        result = _uniform_knowledge_fallback(agents, items)
        assert result is None

    def test_no_items_returns_none(self) -> None:
        agents = [_make_agent("a1")]
        assert _uniform_knowledge_fallback(agents, None) is None
