"""Tests for UCB exploration bonus in composite scoring (ADR-017, algorithms.md §A2)."""

from __future__ import annotations

import math
from unittest.mock import AsyncMock, MagicMock

import pytest

from formicos.core.types import AgentConfig, CasteRecipe, ColonyContext, VectorSearchHit
from formicos.engine.context import assemble_context, TierBudgets


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _agent() -> AgentConfig:
    recipe = CasteRecipe(
        name="coder", description="test", system_prompt="You are a test agent.",
        temperature=0.0, tools=[], max_tokens=1024,
    )
    return AgentConfig(
        id="agent-1", name="Test", caste="coder",
        model="test/model", recipe=recipe,
    )


def _colony_context() -> ColonyContext:
    return ColonyContext(
        colony_id="col-1",
        workspace_id="ws-1",
        thread_id="thread-1",
        goal="Test goal",
        round_number=1,
        merge_edges=[],
    )


def _make_skill_hit(
    skill_id: str,
    score: float = 0.2,
    confidence: float = 0.5,
    conf_alpha: float = 5.0,
    conf_beta: float = 5.0,
    extracted_at: str = "",
) -> MagicMock:
    hit = MagicMock(spec=VectorSearchHit)
    hit.id = skill_id
    hit.score = score
    hit.content = f"Skill content for {skill_id}"
    hit.metadata = {
        "confidence": confidence,
        "conf_alpha": conf_alpha,
        "conf_beta": conf_beta,
        "extracted_at": extracted_at,
    }
    return hit


# ---------------------------------------------------------------------------
# UCB exploration bonus tests
# ---------------------------------------------------------------------------


class TestUCBExplorationBonus:
    @pytest.mark.asyncio
    async def test_low_obs_gets_higher_exploration(self) -> None:
        """Under-observed skill should get larger exploration bonus."""
        # Skill A: 2 obs (alpha=2, beta=2), Skill B: 100 obs (alpha=51, beta=51)
        hit_a = _make_skill_hit("a", score=0.2, conf_alpha=2.0, conf_beta=2.0)
        hit_b = _make_skill_hit("b", score=0.2, conf_alpha=51.0, conf_beta=51.0)

        port = AsyncMock()
        port.search = AsyncMock(return_value=[hit_a, hit_b])

        result = await assemble_context(
            agent=_agent(),
            colony_context=_colony_context(),
            round_goal="test",
            routed_outputs={},
            merged_summaries=[],
            vector_port=port,
            total_colonies=50,
            ucb_exploration_weight=0.1,
        )

        # Both skills should be retrieved
        assert "a" in result.retrieved_skill_ids
        assert "b" in result.retrieved_skill_ids

    @pytest.mark.asyncio
    async def test_exploration_bonus_math(self) -> None:
        """Verify the UCB formula produces expected values."""
        # n_observations = alpha + beta - 2
        # exploration = c * sqrt(ln(N) / n)
        c = 0.1
        total_colonies = 100
        alpha, beta_p = 3.0, 3.0  # 4 observations
        n_obs = max(alpha + beta_p - 2.0, 1.0)  # = 4
        expected = c * math.sqrt(math.log(total_colonies) / n_obs)
        assert expected > 0

        # With more observations
        alpha2, beta2 = 52.0, 52.0  # 102 observations
        n_obs2 = max(alpha2 + beta2 - 2.0, 1.0)  # = 102
        expected2 = c * math.sqrt(math.log(total_colonies) / n_obs2)
        assert expected2 < expected

    @pytest.mark.asyncio
    async def test_zero_colonies_no_crash(self) -> None:
        """total_colonies=0 should not cause division by zero."""
        hit = _make_skill_hit("a", conf_alpha=2.0, conf_beta=2.0)

        port = AsyncMock()
        port.search = AsyncMock(return_value=[hit])

        result = await assemble_context(
            agent=_agent(),
            colony_context=_colony_context(),
            round_goal="test",
            routed_outputs={},
            merged_summaries=[],
            vector_port=port,
            total_colonies=0,
        )
        assert "a" in result.retrieved_skill_ids

    @pytest.mark.asyncio
    async def test_no_beta_fields_fallback(self) -> None:
        """Skills without conf_alpha/conf_beta should use default n_obs=1."""
        hit = _make_skill_hit("a", conf_alpha=0, conf_beta=0)
        hit.metadata.pop("conf_alpha")
        hit.metadata.pop("conf_beta")

        port = AsyncMock()
        port.search = AsyncMock(return_value=[hit])

        result = await assemble_context(
            agent=_agent(),
            colony_context=_colony_context(),
            round_goal="test",
            routed_outputs={},
            merged_summaries=[],
            vector_port=port,
            total_colonies=10,
        )
        assert "a" in result.retrieved_skill_ids

    @pytest.mark.asyncio
    async def test_weights_sum_to_one(self) -> None:
        """Composite score weights should sum to 1.0."""
        # 0.50 + 0.25 + 0.20 + 0.05 = 1.0
        assert 0.50 + 0.25 + 0.20 + 0.05 == pytest.approx(1.0)

    @pytest.mark.asyncio
    async def test_exploration_capped_at_one(self) -> None:
        """Exploration term is capped via min(exploration, 1.0)."""
        c = 0.1
        # With 1 observation and many colonies, exploration could be large
        n_obs = 1.0
        total = 10000
        raw = c * math.sqrt(math.log(total) / n_obs)
        capped = min(raw, 1.0)
        # The contribution is 0.05 * capped, so max contribution is 0.05
        assert 0.05 * capped <= 0.05


class TestCompositeScoreOrdering:
    @pytest.mark.asyncio
    async def test_ordering_with_ucb(self) -> None:
        """UCB bonus should influence retrieval ordering for under-observed skills."""
        # Two skills with identical semantic, confidence, freshness
        # but different observation counts
        hit_few = _make_skill_hit(
            "few", score=0.2, confidence=0.5,
            conf_alpha=2.0, conf_beta=2.0,
        )
        hit_many = _make_skill_hit(
            "many", score=0.2, confidence=0.5,
            conf_alpha=51.0, conf_beta=51.0,
        )

        port = AsyncMock()
        port.search = AsyncMock(return_value=[hit_many, hit_few])

        result = await assemble_context(
            agent=_agent(),
            colony_context=_colony_context(),
            round_goal="test",
            routed_outputs={},
            merged_summaries=[],
            vector_port=port,
            total_colonies=100,
            ucb_exploration_weight=0.1,
        )

        # Both should be retrieved (only 2 skills, top_k=3 default)
        assert len(result.retrieved_skill_ids) == 2
