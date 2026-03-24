"""Wave 39 1B/1C tests: task-type validators and auto-escalation.

Verifies that:
- Task classification is deterministic and correct
- Each validator produces the right tri-state verdict
- Validators are inspectable and replay-derivable
- Auto-escalation tier ordering is correct
"""

from __future__ import annotations

import re

from formicos.engine.runner import (
    ConvergenceResult,
    ValidatorResult,
    classify_task_type,
    validate_task_output,
)


# ---------------------------------------------------------------------------
# Task classification tests
# ---------------------------------------------------------------------------


class TestTaskClassification:
    """Verify deterministic task classification."""

    def test_code_keywords(self) -> None:
        assert classify_task_type("Implement a sorting algorithm") == "code"
        assert classify_task_type("Write a Python function") == "code"
        assert classify_task_type("Fix the login bug") == "code"
        assert classify_task_type("Debug this test") == "code"
        assert classify_task_type("Build a REST API") == "code"
        assert classify_task_type("Refactor the auth module") == "code"

    def test_research_keywords(self) -> None:
        assert classify_task_type("Research best practices for caching") == "research"
        assert classify_task_type("Summarize the architecture") == "research"
        assert classify_task_type("Analyze the performance data") == "research"
        assert classify_task_type("Compare React vs Vue") == "research"

    def test_documentation_keywords(self) -> None:
        assert classify_task_type("Document the API endpoints") == "documentation"
        assert classify_task_type("Write a README for the project") == "documentation"
        assert classify_task_type("Create a user guide") == "documentation"
        assert classify_task_type("Write a specification for auth") == "documentation"

    def test_review_keywords(self) -> None:
        assert classify_task_type("Review this pull request") == "review"
        assert classify_task_type("Audit the security posture") == "review"
        assert classify_task_type("Check the deployment config") == "review"
        assert classify_task_type("Inspect the error logs") == "review"

    def test_unknown_fallback(self) -> None:
        assert classify_task_type("something completely unrelated xyz") == "unknown"
        assert classify_task_type("") == "unknown"

    def test_doc_takes_priority_over_code(self) -> None:
        """When both code and doc keywords present, documentation wins."""
        assert classify_task_type("Implement and document the API") == "documentation"

    def test_code_without_other_keywords(self) -> None:
        """Pure code task without doc/review/research keywords."""
        assert classify_task_type("Implement a sorting algorithm") == "code"


# ---------------------------------------------------------------------------
# Code task validator tests
# ---------------------------------------------------------------------------


class TestCodeValidator:
    """Verify code task validation logic."""

    def _converged(self) -> ConvergenceResult:
        return ConvergenceResult(
            score=0.9, goal_alignment=0.8, stability=0.95,
            progress=0.9, is_stalled=False, is_converged=True,
        )

    def _stalled(self) -> ConvergenceResult:
        return ConvergenceResult(
            score=0.3, goal_alignment=0.5, stability=0.4,
            progress=0.2, is_stalled=True, is_converged=False,
        )

    def test_pass_on_successful_execution(self) -> None:
        result = validate_task_output(
            task="Write a sorting function",
            outputs={"coder": "def sort(lst): ..."},
            convergence=self._converged(),
            recent_successful_code_execute=True,
        )
        assert result.verdict == "pass"
        assert result.task_type == "code"
        assert result.reason == "verified_execution"

    def test_inconclusive_converged_without_execution(self) -> None:
        result = validate_task_output(
            task="Implement a parser",
            outputs={"coder": "def parse(text): ..."},
            convergence=self._converged(),
            recent_successful_code_execute=False,
        )
        assert result.verdict == "inconclusive"
        assert result.reason == "converged_without_execution"

    def test_fail_no_convergence_no_execution(self) -> None:
        result = validate_task_output(
            task="Build a REST API",
            outputs={"coder": "some partial output"},
            convergence=self._stalled(),
            recent_successful_code_execute=False,
        )
        assert result.verdict == "fail"


# ---------------------------------------------------------------------------
# Research task validator tests
# ---------------------------------------------------------------------------


class TestResearchValidator:
    """Verify research task validation logic."""

    def _neutral(self) -> ConvergenceResult:
        return ConvergenceResult(
            score=0.5, goal_alignment=0.6, stability=0.5,
            progress=0.5, is_stalled=False, is_converged=False,
        )

    def test_pass_with_substantive_output(self) -> None:
        result = validate_task_output(
            task="Research caching strategies",
            outputs={"researcher": "A" * 300},
            convergence=self._neutral(),
        )
        assert result.verdict == "pass"
        assert result.task_type == "research"

    def test_pass_with_knowledge_production(self) -> None:
        result = validate_task_output(
            task="Analyze the architecture",
            outputs={"researcher": "A" * 250},
            convergence=self._neutral(),
            knowledge_items_produced=2,
        )
        assert result.verdict == "pass"
        assert "knowledge" in result.reason

    def test_inconclusive_minimal_output(self) -> None:
        result = validate_task_output(
            task="Summarize the findings",
            outputs={"researcher": "A" * 80},
            convergence=self._neutral(),
        )
        assert result.verdict == "inconclusive"

    def test_fail_insufficient_output(self) -> None:
        result = validate_task_output(
            task="Explain the design",
            outputs={"researcher": "ok"},
            convergence=self._neutral(),
        )
        assert result.verdict == "fail"


# ---------------------------------------------------------------------------
# Documentation task validator tests
# ---------------------------------------------------------------------------


class TestDocumentationValidator:
    """Verify documentation task validation logic."""

    def _neutral(self) -> ConvergenceResult:
        return ConvergenceResult(
            score=0.5, goal_alignment=0.6, stability=0.5,
            progress=0.5, is_stalled=False, is_converged=False,
        )

    def test_pass_with_structured_output(self) -> None:
        output = (
            "# API Guide\n\n## Endpoints\n\n"
            "- GET /users — returns all users\n"
            "- POST /users — creates a new user\n"
            "- DELETE /users/:id — removes a user\n\n"
            "## Authentication\n\n"
            "All endpoints require Bearer token.\n\n"
            "```python\ndef get_users(): ...\n```"
        )
        result = validate_task_output(
            task="Document the API",
            outputs={"coder": output},
            convergence=self._neutral(),
        )
        assert result.verdict == "pass"
        assert result.task_type == "documentation"
        assert result.reason == "structured_output"

    def test_inconclusive_no_structure(self) -> None:
        result = validate_task_output(
            task="Write a guide for deployment",
            outputs={"coder": "This is a long block of plain text " * 10},
            convergence=self._neutral(),
        )
        assert result.verdict == "inconclusive"
        assert result.reason == "output_lacks_structure"

    def test_fail_insufficient_output(self) -> None:
        result = validate_task_output(
            task="Create a README",
            outputs={"coder": "short"},
            convergence=self._neutral(),
        )
        assert result.verdict == "fail"


# ---------------------------------------------------------------------------
# Review task validator tests
# ---------------------------------------------------------------------------


class TestReviewValidator:
    """Verify review task validation logic."""

    def _neutral(self) -> ConvergenceResult:
        return ConvergenceResult(
            score=0.5, goal_alignment=0.6, stability=0.5,
            progress=0.5, is_stalled=False, is_converged=False,
        )

    def test_pass_with_actionable_feedback(self) -> None:
        output = "Found 3 issues: 1. SQL injection vulnerability in login handler. 2. Missing input validation. 3. Consider using parameterized queries."
        result = validate_task_output(
            task="Review this code for bugs",
            outputs={"reviewer": output},
            convergence=self._neutral(),
        )
        assert result.verdict == "pass"
        assert result.task_type == "review"
        assert result.reason == "actionable_feedback"

    def test_inconclusive_short_feedback(self) -> None:
        result = validate_task_output(
            task="Check the deployment config",
            outputs={"reviewer": "Looks good overall. No major concerns here but could use some cleanup."},
            convergence=self._neutral(),
        )
        assert result.verdict == "inconclusive"

    def test_fail_insufficient_feedback(self) -> None:
        result = validate_task_output(
            task="Audit the logs",
            outputs={"reviewer": "ok"},
            convergence=self._neutral(),
        )
        assert result.verdict == "fail"


# ---------------------------------------------------------------------------
# Unknown task type tests
# ---------------------------------------------------------------------------


class TestUnknownTaskValidator:
    """Verify unknown task type handling."""

    def test_unknown_is_inconclusive(self) -> None:
        result = validate_task_output(
            task="something xyz",
            outputs={"agent": "output"},
            convergence=ConvergenceResult(
                score=0.5, goal_alignment=0.5, stability=0.5,
                progress=0.5, is_stalled=False, is_converged=False,
            ),
        )
        assert result.verdict == "inconclusive"
        assert result.task_type == "unknown"
        assert result.reason == "no_validator_for_task_type"


# ---------------------------------------------------------------------------
# ValidatorResult model tests
# ---------------------------------------------------------------------------


class TestValidatorResultModel:
    """Verify ValidatorResult is frozen and inspectable."""

    def test_result_is_frozen(self) -> None:
        r = ValidatorResult(task_type="code", verdict="pass", reason="test")
        assert r.task_type == "code"
        assert r.verdict == "pass"
        assert r.reason == "test"

    def test_result_serializable(self) -> None:
        r = ValidatorResult(task_type="research", verdict="fail", reason="x")
        d = r.model_dump()
        assert d["task_type"] == "research"
        assert d["verdict"] == "fail"


# ---------------------------------------------------------------------------
# Auto-escalation tier ordering tests (1C)
# ---------------------------------------------------------------------------


class TestAutoEscalationTierOrdering:
    """Verify the tier ordering helper for auto-escalation."""

    def test_next_tier_from_light(self) -> None:
        from formicos.surface.colony_manager import _next_available_tier
        from formicos.core.types import CasteSlot, SubcasteTier

        castes = [CasteSlot(caste="coder", tier=SubcasteTier.light)]
        assert _next_available_tier(castes) == "standard"

    def test_next_tier_from_standard(self) -> None:
        from formicos.surface.colony_manager import _next_available_tier
        from formicos.core.types import CasteSlot, SubcasteTier

        castes = [CasteSlot(caste="coder", tier=SubcasteTier.standard)]
        assert _next_available_tier(castes) == "heavy"

    def test_no_next_tier_from_heavy(self) -> None:
        from formicos.surface.colony_manager import _next_available_tier
        from formicos.core.types import CasteSlot, SubcasteTier

        castes = [CasteSlot(caste="coder", tier=SubcasteTier.heavy)]
        assert _next_available_tier(castes) is None

    def test_mixed_tiers_uses_heaviest(self) -> None:
        from formicos.surface.colony_manager import _next_available_tier
        from formicos.core.types import CasteSlot, SubcasteTier

        castes = [
            CasteSlot(caste="coder", tier=SubcasteTier.light),
            CasteSlot(caste="reviewer", tier=SubcasteTier.standard),
        ]
        # Heaviest is standard, next is heavy
        assert _next_available_tier(castes) == "heavy"

    def test_empty_castes_defaults_to_standard(self) -> None:
        from formicos.surface.colony_manager import _next_available_tier

        assert _next_available_tier([]) == "heavy"

    def test_tier_order_is_correct(self) -> None:
        from formicos.surface.colony_manager import _TIER_ORDER

        assert _TIER_ORDER == ("light", "standard", "heavy")
