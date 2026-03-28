"""Tests for queen_budget.py (Wave 68 Track 3, ADR-051; Wave 71.0 9-slot expansion)."""

from __future__ import annotations

from formicos.surface.queen_budget import (
    FALLBACK_BUDGET,
    QueenContextBudget,
    compute_queen_budget,
)


class TestQueenContextBudget:
    """QueenContextBudget dataclass basics."""

    def test_frozen(self) -> None:
        b = QueenContextBudget(
            system_prompt=100,
            memory_retrieval=100,
            project_context=100,
            project_plan=100,
            operating_procedures=100,
            queen_journal=100,
            thread_context=100,
            tool_memory=100,
            conversation_history=100,
        )
        assert b.system_prompt == 100
        assert b.operating_procedures == 100
        assert b.queen_journal == 100

    def test_fallback_values(self) -> None:
        assert FALLBACK_BUDGET.system_prompt == 2000
        assert FALLBACK_BUDGET.memory_retrieval == 1500
        assert FALLBACK_BUDGET.project_context == 500
        assert FALLBACK_BUDGET.operating_procedures == 400
        assert FALLBACK_BUDGET.queen_journal == 300
        assert FALLBACK_BUDGET.thread_context == 1500
        assert FALLBACK_BUDGET.tool_memory == 4000
        assert FALLBACK_BUDGET.conversation_history == 6000


class TestComputeQueenBudget:
    """compute_queen_budget proportional scaling."""

    def test_none_context_window_returns_fallback(self) -> None:
        result = compute_queen_budget(None, 4096)
        assert result is FALLBACK_BUDGET

    def test_zero_context_window_returns_fallback(self) -> None:
        result = compute_queen_budget(0, 4096)
        assert result is FALLBACK_BUDGET

    def test_negative_context_window_returns_fallback(self) -> None:
        result = compute_queen_budget(-1, 4096)
        assert result is FALLBACK_BUDGET

    def test_small_window_uses_floors(self) -> None:
        """8K model with 4096 reserve -> available=4096, all floors."""
        result = compute_queen_budget(8192, 4096)
        assert result.system_prompt == 2000
        assert result.memory_retrieval == 1500
        assert result.project_context == 500
        assert result.operating_procedures == 400
        assert result.queen_journal == 300
        assert result.thread_context == 1500
        assert result.tool_memory == 4000
        assert result.conversation_history == 6000

    def test_large_window_scales_up(self) -> None:
        """200K model -> proportional values exceed floors."""
        result = compute_queen_budget(200_000, 4096)
        # available = 200_000 - 4096 = 195904
        # conversation_history = 28% of 195904 = 54853
        assert result.conversation_history >= 54000
        assert result.conversation_history > 6000
        # thread_context = 13% of 195904 = 25467
        assert result.thread_context >= 25000
        assert result.thread_context > 1500

    def test_no_regression_guarantee(self) -> None:
        """Every slot must use max(fallback, proportional)."""
        result = compute_queen_budget(32768, 4096)
        assert result.system_prompt >= 2000
        assert result.memory_retrieval >= 1500
        assert result.project_context >= 500
        assert result.operating_procedures >= 400
        assert result.queen_journal >= 300
        assert result.thread_context >= 1500
        assert result.tool_memory >= 4000
        assert result.conversation_history >= 6000

    def test_output_reserve_exceeds_window(self) -> None:
        """When reserve >= window, available=0 -> fallback."""
        result = compute_queen_budget(4096, 4096)
        assert result is FALLBACK_BUDGET

    def test_32k_model_example(self) -> None:
        """ADR-051 example: 32K model, 4096 reserve."""
        result = compute_queen_budget(32768, 4096)
        available = 32768 - 4096  # 28672
        # conversation_history = 28% of 28672 = 8028
        assert result.conversation_history == max(
            6000, int(available * 0.28),
        )
        # thread_context = 13% of 28672 = 3727
        assert result.thread_context == max(
            1500, int(available * 0.13),
        )
        # tool_memory = 9% of 28672 = 2580 < 4000 floor
        assert result.tool_memory == 4000
