"""Wave 41 Team 2: Execution surface tests.

Tests the production-grade execution surface (B1):
- Workspace command execution (separate from sandbox)
- Structured test output parsing (pytest, jest, cargo, go, xunit)
- WorkspaceExecutionResult type and structured failure information
- workspace_execute tool spec and category mapping
- workspace_execute handler wiring in runner._execute_tool
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from formicos.adapters.sandbox_manager import (
    execute_workspace_command,
    parse_test_output,
)
from formicos.core.types import (
    TestFailure,
    WorkspaceExecutionResult,
)
from formicos.engine.runner_types import (
    ToolExecutionResult,
    WorkspaceExecuteHandler,
)
from formicos.engine.tool_dispatch import (
    TOOL_CATEGORY_MAP,
    TOOL_SPECS,
)


# ---------------------------------------------------------------------------
# WorkspaceExecutionResult type tests
# ---------------------------------------------------------------------------


class TestWorkspaceExecutionResult:
    """Test the WorkspaceExecutionResult type carries structured information."""

    def test_basic_fields(self) -> None:
        result = WorkspaceExecutionResult(
            stdout="ok",
            stderr="",
            exit_code=0,
            command="pytest",
            working_dir="/tmp/test",
        )
        assert result.exit_code == 0
        assert result.command == "pytest"
        assert result.working_dir == "/tmp/test"
        assert result.timed_out is False
        assert result.files_created == []
        assert result.files_modified == []
        assert result.files_deleted == []
        assert result.warning == ""

    def test_test_failure_fields(self) -> None:
        result = WorkspaceExecutionResult(
            exit_code=1,
            command="pytest",
            working_dir="/tmp",
            tests_passed=5,
            tests_failed=2,
            tests_errored=1,
            language="python/pytest",
            test_failures=[
                TestFailure(
                    test_name="test_foo",
                    error_type="AssertionError",
                    message="Expected True",
                    file_path="tests/test_foo.py",
                    line_number=42,
                ),
            ],
        )
        assert result.tests_passed == 5
        assert result.tests_failed == 2
        assert result.tests_errored == 1
        assert result.language == "python/pytest"
        assert len(result.test_failures) == 1
        assert result.test_failures[0].test_name == "test_foo"

    def test_timeout_result(self) -> None:
        result = WorkspaceExecutionResult(
            exit_code=124,
            timed_out=True,
            command="sleep 999",
            working_dir="/tmp",
        )
        assert result.timed_out is True
        assert result.exit_code == 124

    def test_defaults(self) -> None:
        result = WorkspaceExecutionResult(exit_code=0)
        assert result.stdout == ""
        assert result.stderr == ""
        assert result.command == ""
        assert result.working_dir == ""
        assert result.files_created == []
        assert result.files_modified == []
        assert result.files_deleted == []
        assert result.warning == ""
        assert result.tests_passed == 0
        assert result.tests_failed == 0
        assert result.test_failures == []
        assert result.language == ""


class TestToolExecutionResultWorkspaceField:
    """ToolExecutionResult carries optional workspace_execute_result."""

    def test_default_none(self) -> None:
        r = ToolExecutionResult(content="ok")
        assert r.workspace_execute_result is None

    def test_with_workspace_result(self) -> None:
        ws = WorkspaceExecutionResult(exit_code=0, command="pytest")
        r = ToolExecutionResult(
            content="ok",
            workspace_execute_result=ws,
        )
        assert r.workspace_execute_result is not None
        assert r.workspace_execute_result.command == "pytest"


# ---------------------------------------------------------------------------
# Test output parser tests
# ---------------------------------------------------------------------------


class TestParseTestOutputPytest:
    """Test pytest output parsing."""

    def test_passing_suite(self) -> None:
        output = "========================= 5 passed in 1.23s ========================="
        result = parse_test_output(output)
        assert result["language"] == "python/pytest"
        assert result["tests_passed"] == 5
        assert result["tests_failed"] == 0
        assert result["tests_errored"] == 0

    def test_mixed_results(self) -> None:
        output = "========== 3 failed, 10 passed, 1 error in 5.67s =========="
        result = parse_test_output(output)
        assert result["language"] == "python/pytest"
        assert result["tests_passed"] == 10
        assert result["tests_failed"] == 3
        assert result["tests_errored"] == 1

    def test_failure_details_extracted(self) -> None:
        output = """
FAILED tests/test_foo.py::TestBar::test_baz - AssertionError: expected True
FAILED tests/test_qux.py::test_thing - ValueError: bad value
========== 2 failed, 5 passed in 2.34s ==========
"""
        result = parse_test_output(output)
        assert result["tests_failed"] == 2
        assert len(result["test_failures"]) == 2
        assert result["test_failures"][0].test_name == "TestBar::test_baz"
        assert result["test_failures"][0].file_path == "tests/test_foo.py"
        assert result["test_failures"][0].error_type == "AssertionError"
        assert result["test_failures"][1].test_name == "test_thing"

    def test_only_failed(self) -> None:
        output = "========== 2 failed in 1.00s =========="
        result = parse_test_output(output)
        assert result["tests_failed"] == 2
        assert result["tests_passed"] == 0


class TestParseTestOutputJest:
    """Test jest/node output parsing."""

    def test_jest_summary(self) -> None:
        output = "Tests: 2 failed, 8 passed, 10 total"
        result = parse_test_output(output)
        assert result["language"] == "javascript/jest"
        assert result["tests_passed"] == 8
        assert result["tests_failed"] == 2

    def test_jest_all_passed(self) -> None:
        output = "Tests: 10 passed, 10 total"
        result = parse_test_output(output)
        assert result["language"] == "javascript/jest"
        assert result["tests_passed"] == 10
        assert result["tests_failed"] == 0


class TestParseTestOutputCargo:
    """Test Rust/cargo test output parsing."""

    def test_cargo_mixed(self) -> None:
        output = "test result: FAILED. 3 passed; 1 failed; 0 ignored"
        result = parse_test_output(output)
        assert result["language"] == "rust/cargo"
        assert result["tests_passed"] == 3
        assert result["tests_failed"] == 1

    def test_cargo_all_pass(self) -> None:
        output = "test result: ok. 10 passed; 0 failed; 0 ignored"
        result = parse_test_output(output)
        assert result["language"] == "rust/cargo"
        assert result["tests_passed"] == 10


class TestParseTestOutputGo:
    """Test Go test output parsing."""

    def test_go_failures(self) -> None:
        output = """
--- PASS: TestAdd (0.00s)
--- PASS: TestSub (0.00s)
--- FAIL: TestDiv (0.01s)
FAIL
"""
        result = parse_test_output(output)
        assert result["language"] == "go/test"
        assert result["tests_passed"] == 2
        assert result["tests_failed"] == 1
        assert len(result["test_failures"]) == 1
        assert result["test_failures"][0].test_name == "TestDiv"


class TestParseTestOutputXunit:
    """Test xunit (Java/C#) output parsing."""

    def test_xunit_summary(self) -> None:
        output = "Tests run: 15, Failures: 2, Errors: 1, Skipped: 0"
        result = parse_test_output(output)
        assert result["language"] == "xunit"
        assert result["tests_passed"] == 12
        assert result["tests_failed"] == 2
        assert result["tests_errored"] == 1


class TestParseTestOutputUnrecognized:
    """Test unrecognized output format returns empty."""

    def test_no_match(self) -> None:
        output = "Hello world"
        result = parse_test_output(output)
        assert result["language"] == ""
        assert result["tests_passed"] == 0
        assert result["tests_failed"] == 0

    def test_empty(self) -> None:
        result = parse_test_output("")
        assert result["language"] == ""


# ---------------------------------------------------------------------------
# workspace_execute tool spec and category tests
# ---------------------------------------------------------------------------


class TestWorkspaceExecuteToolSpec:
    """Test that workspace_execute is properly registered."""

    def test_spec_exists(self) -> None:
        assert "workspace_execute" in TOOL_SPECS

    def test_spec_has_command_param(self) -> None:
        spec = TOOL_SPECS["workspace_execute"]
        props = spec["parameters"]["properties"]
        assert "command" in props
        assert "timeout_s" in props

    def test_command_is_required(self) -> None:
        spec = TOOL_SPECS["workspace_execute"]
        assert "command" in spec["parameters"]["required"]

    def test_category_is_exec_code(self) -> None:
        assert TOOL_CATEGORY_MAP["workspace_execute"].value == "exec_code"


class TestWorkspaceFileToolSpecs:
    """Test that workspace file tools are properly registered."""

    def test_list_workspace_files_spec(self) -> None:
        assert "list_workspace_files" in TOOL_SPECS
        assert TOOL_CATEGORY_MAP["list_workspace_files"].value == "read_fs"

    def test_read_workspace_file_spec(self) -> None:
        assert "read_workspace_file" in TOOL_SPECS
        spec = TOOL_SPECS["read_workspace_file"]
        assert "path" in spec["parameters"]["required"]
        assert TOOL_CATEGORY_MAP["read_workspace_file"].value == "read_fs"

    def test_write_workspace_file_spec(self) -> None:
        assert "write_workspace_file" in TOOL_SPECS
        spec = TOOL_SPECS["write_workspace_file"]
        assert "path" in spec["parameters"]["required"]
        assert "content" in spec["parameters"]["required"]
        assert TOOL_CATEGORY_MAP["write_workspace_file"].value == "write_fs"


# ---------------------------------------------------------------------------
# Workspace command execution (integration with real subprocess)
# ---------------------------------------------------------------------------


class TestExecuteWorkspaceCommand:
    """Test execute_workspace_command with real subprocess calls.

    Wave 43: These tests rely on host-shell execution with absolute paths,
    so workspace isolation must be disabled.
    """

    @pytest.fixture(autouse=True)
    def _disable_workspace_isolation(self, monkeypatch: Any) -> None:
        import formicos.adapters.sandbox_manager as sm
        monkeypatch.setattr(sm, "WORKSPACE_ISOLATION", False)

    @pytest.mark.asyncio
    async def test_simple_command(self, tmp_path: Any) -> None:
        result = await execute_workspace_command(
            "python -c \"print('hello')\"",
            str(tmp_path),
            timeout_s=10,
        )
        assert result.exit_code == 0
        assert "hello" in result.stdout
        assert result.working_dir == str(tmp_path)
        assert result.timed_out is False

    @pytest.mark.asyncio
    async def test_failing_command(self, tmp_path: Any) -> None:
        result = await execute_workspace_command(
            "python -c \"import sys; sys.exit(1)\"",
            str(tmp_path),
            timeout_s=10,
        )
        assert result.exit_code == 1

    @pytest.mark.asyncio
    async def test_nonexistent_dir(self) -> None:
        result = await execute_workspace_command(
            "echo test",
            "/nonexistent/path/xyz",
            timeout_s=10,
        )
        assert result.exit_code == 1
        assert "does not exist" in result.stderr

    @pytest.mark.asyncio
    async def test_command_with_pytest_output(self, tmp_path: Any) -> None:
        """Test that pytest-like output is parsed into structured results."""
        # Create a test file that produces pytest-like output
        test_script = tmp_path / "run_test.py"
        test_script.write_text(
            'print("========================= 3 passed in 0.50s '
            '=========================")\n'
        )
        result = await execute_workspace_command(
            f"python {test_script}",
            str(tmp_path),
            timeout_s=10,
        )
        assert result.exit_code == 0
        assert result.language == "python/pytest"
        assert result.tests_passed == 3

    @pytest.mark.asyncio
    async def test_timeout_enforced(self, tmp_path: Any) -> None:
        result = await execute_workspace_command(
            "python -c \"import time; time.sleep(30)\"",
            str(tmp_path),
            timeout_s=1,
        )
        assert result.timed_out is True
        assert result.exit_code == 124

    @pytest.mark.asyncio
    async def test_reports_created_files_for_mutating_command(self, tmp_path: Any) -> None:
        result = await execute_workspace_command(
            "python -c \"from pathlib import Path; Path('created.txt').write_text('hello', encoding='utf-8')\"",
            str(tmp_path),
            timeout_s=10,
        )

        assert result.exit_code == 0
        assert "created.txt" in result.files_created
        assert result.warning == ""
        assert (tmp_path / "created.txt").read_text(encoding="utf-8") == "hello"

    @pytest.mark.asyncio
    async def test_max_timeout_capped(self, tmp_path: Any) -> None:
        """Timeout is capped at WORKSPACE_MAX_TIMEOUT_S (120s)."""
        # Just verify it doesn't error with a huge timeout
        result = await execute_workspace_command(
            "python -c \"print('ok')\"",
            str(tmp_path),
            timeout_s=9999,  # will be capped to 120
        )
        assert result.exit_code == 0


# ---------------------------------------------------------------------------
# WorkspaceExecuteHandler type alias
# ---------------------------------------------------------------------------


class TestWorkspaceExecuteHandlerType:
    """Test that the handler type alias is usable."""

    def test_handler_signature(self) -> None:
        """WorkspaceExecuteHandler is a callable type alias."""
        async def fake_handler(
            command: str, working_dir: str, timeout_s: int,
        ) -> WorkspaceExecutionResult:
            return WorkspaceExecutionResult(exit_code=0)

        # Should be assignable to WorkspaceExecuteHandler
        handler: WorkspaceExecuteHandler = fake_handler
        assert callable(handler)
