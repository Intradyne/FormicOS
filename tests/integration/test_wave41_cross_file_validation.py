"""Wave 41 Team 2: Cross-file validation tests.

Tests the cross-file consistency validation (B3):
- CrossFileValidationResult type
- validate_cross_file_consistency function behavior
- File coverage detection across agent outputs
- Integration with workspace execution results
- Round result carries cross_file_validation field
"""

from __future__ import annotations

from typing import Any

import pytest

from formicos.core.types import WorkspaceExecutionResult
from formicos.engine.runner import validate_cross_file_consistency
from formicos.engine.runner_types import (
    CrossFileValidationResult,
    RoundResult,
    ConvergenceResult,
    GovernanceDecision,
    ToolExecutionResult,
    ValidatorResult,
)


# ---------------------------------------------------------------------------
# CrossFileValidationResult type tests
# ---------------------------------------------------------------------------


class TestCrossFileValidationResult:
    """Test the CrossFileValidationResult type."""

    def test_basic_pass(self) -> None:
        r = CrossFileValidationResult(
            verdict="pass",
            reason="all_clean",
            files_checked=["a.py", "b.py"],
        )
        assert r.verdict == "pass"
        assert r.files_checked == ["a.py", "b.py"]
        assert r.issues == []

    def test_fail_with_issues(self) -> None:
        r = CrossFileValidationResult(
            verdict="fail",
            reason="test_failures",
            files_checked=["a.py"],
            issues=["test_a failed", "lint error"],
        )
        assert r.verdict == "fail"
        assert len(r.issues) == 2

    def test_not_applicable(self) -> None:
        r = CrossFileValidationResult(
            verdict="not_applicable",
            reason="single_file",
        )
        assert r.verdict == "not_applicable"


# ---------------------------------------------------------------------------
# validate_cross_file_consistency — core behavior
# ---------------------------------------------------------------------------


class TestCrossFileValidationSingleFile:
    """Cross-file validation is not_applicable for single files."""

    def test_empty_target_files(self) -> None:
        result = validate_cross_file_consistency(
            target_files=[],
            outputs={"a1": "some output"},
            workspace_execute_results=[],
        )
        assert result.verdict == "not_applicable"

    def test_single_target_file(self) -> None:
        result = validate_cross_file_consistency(
            target_files=["main.py"],
            outputs={"a1": "modified main.py"},
            workspace_execute_results=[],
        )
        assert result.verdict == "not_applicable"
        assert result.reason == "single_file_or_no_targets"


class TestCrossFileValidationCoverage:
    """Cross-file validation checks that target files are addressed."""

    def test_all_files_addressed_passes(self) -> None:
        result = validate_cross_file_consistency(
            target_files=["main.py", "utils.py"],
            outputs={"a1": "Updated main.py and utils.py with new logic"},
            workspace_execute_results=[],
        )
        assert result.verdict == "pass"
        assert result.reason == "all_targets_addressed_and_execution_clean"

    def test_partial_coverage_is_inconclusive(self) -> None:
        result = validate_cross_file_consistency(
            target_files=["main.py", "utils.py", "config.py"],
            outputs={"a1": "Updated main.py with new handler"},
            workspace_execute_results=[],
        )
        assert result.verdict == "inconclusive"
        assert result.reason == "partial_file_coverage"
        assert any("utils.py" in issue for issue in result.issues)
        assert any("config.py" in issue for issue in result.issues)

    def test_basename_matching(self) -> None:
        """Files are matched by basename, not full path."""
        result = validate_cross_file_consistency(
            target_files=["src/main.py", "src/utils.py"],
            outputs={"a1": "Changed main.py and utils.py"},
            workspace_execute_results=[],
        )
        assert result.verdict == "pass"

    def test_case_insensitive_matching(self) -> None:
        result = validate_cross_file_consistency(
            target_files=["Main.py", "Utils.py"],
            outputs={"a1": "Updated main.py and utils.py"},
            workspace_execute_results=[],
        )
        assert result.verdict == "pass"

    def test_multiple_agent_outputs_combined(self) -> None:
        result = validate_cross_file_consistency(
            target_files=["main.py", "utils.py"],
            outputs={
                "a1": "Modified main.py",
                "a2": "Modified utils.py",
            },
            workspace_execute_results=[],
        )
        assert result.verdict == "pass"


class TestCrossFileValidationExecution:
    """Cross-file validation checks workspace execution results."""

    def test_execution_failure_causes_fail(self) -> None:
        ws_result = WorkspaceExecutionResult(
            exit_code=1,
            command="pytest",
            tests_failed=3,
        )
        result = validate_cross_file_consistency(
            target_files=["main.py", "utils.py"],
            outputs={"a1": "Modified main.py and utils.py"},
            workspace_execute_results=[
                ToolExecutionResult(
                    content="tests failed",
                    code_execute_failed=True,
                    workspace_execute_result=ws_result,
                ),
            ],
        )
        assert result.verdict == "fail"
        assert any("Test failures" in issue for issue in result.issues)

    def test_execution_success_with_full_coverage_passes(self) -> None:
        ws_result = WorkspaceExecutionResult(
            exit_code=0,
            command="pytest",
            tests_passed=5,
        )
        result = validate_cross_file_consistency(
            target_files=["main.py", "utils.py"],
            outputs={"a1": "Modified main.py and utils.py"},
            workspace_execute_results=[
                ToolExecutionResult(
                    content="ok",
                    code_execute_succeeded=True,
                    workspace_execute_result=ws_result,
                ),
            ],
        )
        assert result.verdict == "pass"

    def test_non_zero_exit_without_test_count(self) -> None:
        """Non-zero exit code without test count → command failed."""
        ws_result = WorkspaceExecutionResult(
            exit_code=2,
            command="ruff check .",
        )
        result = validate_cross_file_consistency(
            target_files=["main.py", "utils.py"],
            outputs={"a1": "Modified main.py and utils.py"},
            workspace_execute_results=[
                ToolExecutionResult(
                    content="lint errors",
                    code_execute_failed=True,
                    workspace_execute_result=ws_result,
                ),
            ],
        )
        assert result.verdict == "fail"
        assert any("exit 2" in issue for issue in result.issues)

    def test_mixed_coverage_and_execution_failure(self) -> None:
        """Both partial coverage and execution failures → fail."""
        ws_result = WorkspaceExecutionResult(
            exit_code=1,
            command="pytest",
            tests_failed=1,
        )
        result = validate_cross_file_consistency(
            target_files=["main.py", "utils.py", "config.py"],
            outputs={"a1": "Modified main.py"},
            workspace_execute_results=[
                ToolExecutionResult(
                    content="failed",
                    code_execute_failed=True,
                    workspace_execute_result=ws_result,
                ),
            ],
        )
        assert result.verdict == "fail"
        # Should have both coverage and execution issues
        assert len(result.issues) >= 2

    def test_no_workspace_results_ignored(self) -> None:
        """Tool results without workspace_execute_result are not checked."""
        result = validate_cross_file_consistency(
            target_files=["main.py", "utils.py"],
            outputs={"a1": "Modified main.py and utils.py"},
            workspace_execute_results=[
                ToolExecutionResult(content="code ok", code_execute_succeeded=True),
            ],
        )
        assert result.verdict == "pass"


# ---------------------------------------------------------------------------
# RoundResult cross_file_validation field
# ---------------------------------------------------------------------------


class TestRoundResultCrossFileField:
    """Test that RoundResult carries cross_file_validation."""

    def test_default_none(self) -> None:
        rr = RoundResult(
            round_number=1,
            convergence=ConvergenceResult(
                score=0.5, goal_alignment=0.7,
                stability=0.5, progress=0.5,
                is_stalled=False, is_converged=False,
            ),
            governance=GovernanceDecision(action="continue", reason="ok"),
            cost=0.1,
            duration_ms=100,
            round_summary="test",
            outputs={"a1": "output"},
            updated_weights={},
        )
        assert rr.cross_file_validation is None

    def test_with_validation_result(self) -> None:
        cfv = CrossFileValidationResult(
            verdict="pass",
            reason="clean",
            files_checked=["a.py", "b.py"],
        )
        rr = RoundResult(
            round_number=1,
            convergence=ConvergenceResult(
                score=0.5, goal_alignment=0.7,
                stability=0.5, progress=0.5,
                is_stalled=False, is_converged=False,
            ),
            governance=GovernanceDecision(action="continue", reason="ok"),
            cost=0.1,
            duration_ms=100,
            round_summary="test",
            outputs={"a1": "output"},
            updated_weights={},
            cross_file_validation=cfv,
        )
        assert rr.cross_file_validation is not None
        assert rr.cross_file_validation.verdict == "pass"
        assert rr.cross_file_validation.files_checked == ["a.py", "b.py"]


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestCrossFileValidationEdgeCases:
    """Edge cases for cross-file validation."""

    def test_files_with_special_characters(self) -> None:
        result = validate_cross_file_consistency(
            target_files=["my file.py", "test-utils.py"],
            outputs={"a1": "Updated my file.py and test-utils.py"},
            workspace_execute_results=[],
        )
        assert result.verdict == "pass"

    def test_many_target_files(self) -> None:
        """Large number of target files still works."""
        files = [f"module_{i}.py" for i in range(20)]
        output = " ".join(files)
        result = validate_cross_file_consistency(
            target_files=files,
            outputs={"a1": output},
            workspace_execute_results=[],
        )
        assert result.verdict == "pass"
        assert len(result.files_checked) == 20

    def test_files_checked_always_populated(self) -> None:
        """files_checked always contains the target files."""
        result = validate_cross_file_consistency(
            target_files=["a.py", "b.py"],
            outputs={"a1": "nothing relevant"},
            workspace_execute_results=[],
        )
        assert result.files_checked == ["a.py", "b.py"]
