"""Tests for budget-aware context assembly (Wave 34 A2)."""

from __future__ import annotations

from typing import Any

from formicos.engine.runner import (
    SCOPE_BUDGETS,
    _budget_aware_assembly,
    _format_result,
)


class TestScopeBudgets:
    def test_budgets_sum_to_one(self) -> None:
        total = sum(SCOPE_BUDGETS.values())
        assert abs(total - 1.0) < 1e-9

    def test_five_scopes(self) -> None:
        expected = {
            "task_knowledge", "observations", "structured_facts",
            "round_history", "scratch_memory",
        }
        assert set(SCOPE_BUDGETS.keys()) == expected

    def test_task_knowledge_is_largest(self) -> None:
        assert SCOPE_BUDGETS["task_knowledge"] == max(SCOPE_BUDGETS.values())


class TestBudgetAwareAssembly:
    def test_no_scope_exceeds_allocation(self) -> None:
        """4000-token budget → no scope exceeds its percentage allocation."""
        total = 4000
        # Create items that are ~200 tokens each (800 chars)
        task_results = [
            {"title": f"Entry {i}", "summary": "S" * 400, "content_preview": "C" * 400}
            for i in range(10)
        ]
        observations = [f"Observation {'O' * 800}" for _ in range(5)]
        facts = [f"Fact {'F' * 800}" for _ in range(5)]
        history = [f"Round {'R' * 800}" for _ in range(5)]
        scratch = [f"Scratch {'S' * 800}" for _ in range(5)]

        assembled = _budget_aware_assembly(
            total, task_results, observations, facts, history, scratch,
        )

        for scope_name, text in assembled.items():
            tokens = len(text) // 4
            budget = int(total * SCOPE_BUDGETS[scope_name])
            assert tokens <= budget, (
                f"{scope_name}: {tokens} tokens > {budget} budget"
            )

    def test_task_knowledge_early_exit(self) -> None:
        """10 results at ~200 tokens each → early-exit around 7 (35% of 4000=1400)."""
        total = 4000
        # Each item ~200 tokens = ~800 chars
        task_results = [
            {"title": f"Entry {i}", "summary": "S" * 350, "content_preview": "C" * 400}
            for i in range(10)
        ]
        assembled = _budget_aware_assembly(
            total, task_results, [], [], [], [],
        )
        # Count items by splitting on newlines
        task_text = assembled["task_knowledge"]
        items_included = 0 if not task_text else len(task_text.split("\n"))
        # Budget is 1400 tokens, each ~200 tokens → ~7 items
        assert items_included < 10, f"Expected early-exit but got {items_included}/10"
        assert items_included > 0, "Should include at least some items"

    def test_empty_scope_no_error(self) -> None:
        """Empty scopes produce empty strings, no errors."""
        assembled = _budget_aware_assembly(4000, [], [], [], [], [])
        assert all(v == "" for v in assembled.values())

    def test_all_scopes_fit_within_total(self) -> None:
        """Small items that all fit → total assembled tokens ≤ total budget."""
        total = 4000
        task_results = [{"title": "T", "summary": "S", "content_preview": "C"}]
        observations = ["obs"]
        facts = ["fact"]
        history = ["round"]
        scratch = ["scratch"]

        assembled = _budget_aware_assembly(
            total, task_results, observations, facts, history, scratch,
        )
        total_tokens = sum(len(v) // 4 for v in assembled.values())
        assert total_tokens <= total

    def test_zero_budget_produces_empty_or_minimal(self) -> None:
        """Zero budget → task knowledge empty (items have >0 tokens)."""
        task_results = [
            {"title": "Entry", "summary": "Summary text", "content_preview": "Content"},
        ]
        assembled = _budget_aware_assembly(
            0, task_results, [], [], [], [],
        )
        assert assembled["task_knowledge"] == ""


class TestFormatResult:
    def test_formats_title_summary_content(self) -> None:
        r = {"title": "My Title", "summary": "My Summary", "content_preview": "Full text"}
        text = _format_result(r)
        assert "My Title" in text
        assert "My Summary" in text
        assert "Full text" in text

    def test_content_truncated_to_400(self) -> None:
        r = {"title": "T", "summary": "", "content_preview": "X" * 1000}
        text = _format_result(r)
        # Content portion should be at most 400 chars
        parts = text.split(" | ")
        content_part = parts[-1]
        assert len(content_part) <= 400

    def test_empty_result(self) -> None:
        r: dict[str, Any] = {}
        text = _format_result(r)
        assert text == ""
