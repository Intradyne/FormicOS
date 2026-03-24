"""Tests for StructuredError wiring across all 5 API surfaces (Wave 33 B4)."""

from __future__ import annotations

import pytest

from formicos.surface.structured_error import (
    KNOWN_ERRORS,
    ErrorCategory,
    ErrorSeverity,
    StructuredError,
    to_a2a_task_status,
    to_http_error,
    to_mcp_protocol_error,
    to_mcp_tool_error,
    to_ws_error,
)


class TestKnownErrorsRegistry:
    """Verify KNOWN_ERRORS has 35+ entries and all are valid."""

    def test_minimum_count(self) -> None:
        assert len(KNOWN_ERRORS) >= 35, (
            f"Expected 35+ KNOWN_ERRORS, got {len(KNOWN_ERRORS)}"
        )

    def test_all_entries_are_structured_errors(self) -> None:
        for key, err in KNOWN_ERRORS.items():
            assert isinstance(err, StructuredError), f"{key} is not StructuredError"

    def test_all_codes_match_keys(self) -> None:
        for key, err in KNOWN_ERRORS.items():
            assert err.error_code == key, f"Key {key} != error_code {err.error_code}"

    def test_all_have_recovery_hints(self) -> None:
        for key, err in KNOWN_ERRORS.items():
            assert err.recovery_hint, f"{key} missing recovery_hint"


class TestMCPToolErrorFormat:
    """Verify to_mcp_tool_error output format."""

    def test_has_is_error_and_content(self) -> None:
        err = KNOWN_ERRORS["WORKSPACE_NOT_FOUND"]
        result = to_mcp_tool_error(err)
        assert result["isError"] is True
        assert isinstance(result["content"], list)
        assert result["content"][0]["type"] == "text"
        assert "structuredContent" in result

    def test_structured_content_has_required_fields(self) -> None:
        err = KNOWN_ERRORS["COLONY_NOT_FOUND"]
        result = to_mcp_tool_error(err)
        sc = result["structuredContent"]
        assert sc["error_code"] == "COLONY_NOT_FOUND"
        assert sc["severity"] == "permanent"
        assert sc["category"] == "not_found"


class TestHTTPErrorFormat:
    """Verify to_http_error output format."""

    @pytest.mark.parametrize(
        ("err_key", "expected_status"),
        [
            ("WORKSPACE_NOT_FOUND", 404),
            ("INVALID_JSON", 400),
            ("INTERNAL_ERROR", 500),
            ("TASK_NOT_TERMINAL", 409),
            ("SERVICE_TIMEOUT", 502),
            ("RATE_LIMITED", 429),
        ],
    )
    def test_status_codes(self, err_key: str, expected_status: int) -> None:
        status, body, headers = to_http_error(KNOWN_ERRORS[err_key])
        assert status == expected_status
        assert "error_code" in body

    def test_retry_after_header(self) -> None:
        status, body, headers = to_http_error(KNOWN_ERRORS["SERVICE_TIMEOUT"])
        assert "Retry-After" in headers


class TestWSErrorFormat:
    """Verify to_ws_error output format."""

    def test_has_type_error(self) -> None:
        err = KNOWN_ERRORS["UNKNOWN_COMMAND"]
        result = to_ws_error(err)
        assert result["type"] == "error"
        assert result["error_code"] == "UNKNOWN_COMMAND"


class TestA2ATaskStatus:
    """Verify to_a2a_task_status output format."""

    def test_failed_state(self) -> None:
        err = KNOWN_ERRORS["INTERNAL_ERROR"]
        result = to_a2a_task_status(err, "task-123")
        assert result["task_id"] == "task-123"
        assert result["state"] == "FAILED"

    def test_input_required_state(self) -> None:
        err = StructuredError(
            error_code="TEST",
            message="test",
            severity=ErrorSeverity.permanent,
            category=ErrorCategory.validation,
            recovery_hint="test",
            requires_human=True,
        )
        result = to_a2a_task_status(err, "task-456")
        assert result["state"] == "INPUT_REQUIRED"
