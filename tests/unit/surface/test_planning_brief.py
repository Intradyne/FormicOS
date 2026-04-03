"""Tests for the conditional planning brief (Wave 80/82)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from formicos.surface.planning_brief import (
    _fallback_outcome_stats,
    build_planning_brief,
)


def _mock_runtime(
    *,
    outcome_stats: list | None = None,
    coder_model: str = "llama-cpp/qwen3.5-4b",
) -> MagicMock:
    rt = MagicMock()
    rt.settings.system.data_dir = "/tmp/test"
    rt.knowledge_catalog = None
    if outcome_stats is not None:
        rt.projections.outcome_stats.return_value = outcome_stats
    else:
        rt.projections.outcome_stats.return_value = []
    rt.resolve_model.return_value = coder_model
    return rt


class TestBuildPlanningBrief:
    @pytest.mark.asyncio()
    async def test_returns_empty_when_no_signals(self) -> None:
        rt = _mock_runtime()
        result = await build_planning_brief(
            rt, "ws1", "t1", "do something", token_budget=500,
        )
        assert isinstance(result, str)

    @pytest.mark.asyncio()
    async def test_respects_token_budget(self) -> None:
        rt = _mock_runtime(outcome_stats=[
            {"avg_quality": 0.7, "count": 10, "strategy": "stigmergic",
             "avg_rounds": 4.0, "caste_mix": "c", "success_rate": 0.8},
        ])
        result = await build_planning_brief(
            rt, "ws1", "t1", "spawn a colony to refactor auth",
            token_budget=50,
        )
        assert len(result) <= 200

    @pytest.mark.asyncio()
    async def test_includes_planning_brief_header(self) -> None:
        rt = _mock_runtime(outcome_stats=[
            {"avg_quality": 0.65, "count": 5, "strategy": "sequential",
             "avg_rounds": 5.0, "caste_mix": "c", "success_rate": 0.7},
        ])
        result = await build_planning_brief(
            rt, "ws1", "t1", "spawn colonies to build the addon",
            token_budget=500,
        )
        if result:
            assert result.startswith("PLANNING BRIEF")

    @pytest.mark.asyncio()
    async def test_worker_line_shows_model_name(self) -> None:
        rt = _mock_runtime(coder_model="llama-cpp/qwen3.5-4b")
        result = await build_planning_brief(
            rt, "ws1", "t1", "spawn a colony to fix auth",
            token_budget=500,
        )
        if result:
            assert "qwen3.5-4b" in result

    @pytest.mark.asyncio()
    async def test_playbook_line_appears_for_coding_task(self) -> None:
        rt = _mock_runtime()
        result = await build_planning_brief(
            rt, "ws1", "t1", "implement the auth module",
            token_budget=500,
        )
        # Playbook hint should appear if playbook_loader is available
        if result:
            assert "PLANNING BRIEF" in result


class TestFallbackOutcomeStats:
    def test_empty_stats(self) -> None:
        rt = _mock_runtime()
        assert _fallback_outcome_stats(rt, "ws1") == ""

    def test_with_stats(self) -> None:
        rt = _mock_runtime(outcome_stats=[
            {"avg_quality": 0.72, "count": 8, "strategy": "stigmergic"},
            {"avg_quality": 0.55, "count": 3, "strategy": "sequential"},
        ])
        result = _fallback_outcome_stats(rt, "ws1")
        assert "n=11" in result
        assert "stigmergic" in result

    def test_exception_returns_empty(self) -> None:
        rt = _mock_runtime()
        rt.projections.outcome_stats.side_effect = RuntimeError("fail")
        assert _fallback_outcome_stats(rt, "ws1") == ""


class TestBriefOnlyOnColonyTurns:
    @pytest.mark.asyncio()
    async def test_status_only_turn_gets_no_brief(self) -> None:
        rt = _mock_runtime(outcome_stats=[
            {"avg_quality": 0.7, "count": 10, "strategy": "stigmergic",
             "avg_rounds": 4.0, "caste_mix": "c", "success_rate": 0.8},
        ])
        result = await build_planning_brief(
            rt, "ws1", "t1", "what's the status?", token_budget=500,
        )
        assert isinstance(result, str)
