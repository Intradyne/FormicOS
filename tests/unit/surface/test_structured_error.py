"""Tests for structured error model and surface mappers (Wave 32.5)."""

from __future__ import annotations

import pytest

from formicos.surface.structured_error import (
    ErrorCategory,
    ErrorSeverity,
    KNOWN_ERRORS,
    StructuredError,
    SuggestedAction,
    to_a2a_task_status,
    to_http_error,
    to_mcp_protocol_error,
    to_mcp_tool_error,
    to_ws_error,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_error(**kwargs: object) -> StructuredError:
    defaults: dict = {
        "error_code": "TEST_ERROR",
        "message": "Something went wrong",
        "severity": ErrorSeverity.transient,
        "category": ErrorCategory.internal,
        "recovery_hint": "Try again later",
    }
    defaults.update(kwargs)
    return StructuredError(**defaults)


# ---------------------------------------------------------------------------
# 1. Model validation and serialization round-trip
# ---------------------------------------------------------------------------

def test_model_round_trip() -> None:
    action = SuggestedAction(
        description="Retry the call",
        tool_name="retry_tool",
        parameter_fixes={"timeout": 30},
    )
    err = StructuredError(
        error_code="FULL_ERROR",
        message="Full error message",
        severity=ErrorSeverity.permanent,
        category=ErrorCategory.validation,
        recovery_hint="Fix the input",
        suggested_action=action,
        retry_after_s=10.0,
        requires_human=True,
        escalation_type="ops",
        details={"extra": "info"},
    )
    data = err.model_dump()
    restored = StructuredError.model_validate(data)
    assert restored.error_code == err.error_code
    assert restored.message == err.message
    assert restored.severity == err.severity
    assert restored.category == err.category
    assert restored.recovery_hint == err.recovery_hint
    assert restored.retry_after_s == err.retry_after_s
    assert restored.requires_human == err.requires_human
    assert restored.escalation_type == err.escalation_type
    assert restored.details == err.details
    assert restored.suggested_action is not None
    assert restored.suggested_action.tool_name == "retry_tool"
    assert restored.suggested_action.parameter_fixes == {"timeout": 30}


def test_retry_after_s_must_be_nonnegative() -> None:
    with pytest.raises(Exception):
        _make_error(retry_after_s=-1.0)


# ---------------------------------------------------------------------------
# 2. to_mcp_tool_error — basic
# ---------------------------------------------------------------------------

def test_to_mcp_tool_error_structure() -> None:
    err = _make_error(message="Oops", recovery_hint="Try harder")
    result = to_mcp_tool_error(err)

    assert result["isError"] is True
    assert isinstance(result["content"], list)
    assert len(result["content"]) == 1
    content_text: str = result["content"][0]["text"]
    assert "Oops" in content_text
    assert "Try harder" in content_text
    sc = result["structuredContent"]
    assert sc["error_code"] == "TEST_ERROR"
    assert sc["message"] == "Oops"
    assert sc["recovery_hint"] == "Try harder"
    assert sc["requires_human"] is False


# ---------------------------------------------------------------------------
# 3. to_mcp_tool_error — with suggested_action
# ---------------------------------------------------------------------------

def test_to_mcp_tool_error_with_suggested_action() -> None:
    action = SuggestedAction(
        description="Use the right tool",
        tool_name="correct_tool",
        parameter_fixes={"key": "value"},
    )
    err = _make_error(suggested_action=action)
    result = to_mcp_tool_error(err)
    sc = result["structuredContent"]
    assert sc["suggested_action"] is not None
    assert sc["suggested_action"]["tool_name"] == "correct_tool"
    assert sc["suggested_action"]["parameter_fixes"] == {"key": "value"}


def test_to_mcp_tool_error_without_suggested_action() -> None:
    err = _make_error()
    result = to_mcp_tool_error(err)
    assert result["structuredContent"]["suggested_action"] is None


# ---------------------------------------------------------------------------
# 4. to_mcp_protocol_error — JSON-RPC code mapping
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("category,expected_code", [
    (ErrorCategory.validation, -32602),
    (ErrorCategory.not_found, -32602),
    (ErrorCategory.conflict, -32600),
    (ErrorCategory.internal, -32603),
    (ErrorCategory.upstream, -32603),      # default
    (ErrorCategory.authentication, -32603), # default
    (ErrorCategory.rate_limit, -32603),     # default
    (ErrorCategory.input_required, -32603), # default
])
def test_to_mcp_protocol_error_code_mapping(
    category: ErrorCategory, expected_code: int
) -> None:
    err = _make_error(category=category)
    result = to_mcp_protocol_error(err)
    assert result["code"] == expected_code
    assert result["message"] == err.message
    assert "data" in result
    assert result["data"]["error_code"] == "TEST_ERROR"


# ---------------------------------------------------------------------------
# 5. to_http_error — status codes per category
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("category,expected_status", [
    (ErrorCategory.validation, 400),
    (ErrorCategory.authentication, 401),
    (ErrorCategory.rate_limit, 429),
    (ErrorCategory.not_found, 404),
    (ErrorCategory.conflict, 409),
    (ErrorCategory.upstream, 502),
    (ErrorCategory.internal, 500),
    (ErrorCategory.input_required, 422),
])
def test_to_http_error_status_codes(
    category: ErrorCategory, expected_status: int
) -> None:
    err = _make_error(category=category)
    status, body, headers = to_http_error(err)
    assert status == expected_status
    assert body["error_code"] == "TEST_ERROR"


# ---------------------------------------------------------------------------
# 6. to_http_error — Retry-After header
# ---------------------------------------------------------------------------

def test_to_http_error_retry_after_header_present() -> None:
    err = _make_error(retry_after_s=30.0, category=ErrorCategory.rate_limit)
    status, body, headers = to_http_error(err)
    assert "Retry-After" in headers
    assert headers["Retry-After"] == "30"


def test_to_http_error_retry_after_header_absent_when_none() -> None:
    err = _make_error()
    _, _, headers = to_http_error(err)
    assert "Retry-After" not in headers


def test_to_http_error_retry_after_header_absent_when_zero() -> None:
    err = _make_error(retry_after_s=0.0)
    _, _, headers = to_http_error(err)
    assert "Retry-After" not in headers


# ---------------------------------------------------------------------------
# 7. to_a2a_task_status — requires_human -> INPUT_REQUIRED
# ---------------------------------------------------------------------------

def test_to_a2a_task_status_requires_human() -> None:
    err = _make_error(requires_human=True)
    result = to_a2a_task_status(err, task_id="task-abc")
    assert result["state"] == "INPUT_REQUIRED"
    assert result["task_id"] == "task-abc"
    assert result["error"]["error_code"] == "TEST_ERROR"


# ---------------------------------------------------------------------------
# 8. to_a2a_task_status — authentication -> AUTH_REQUIRED
# ---------------------------------------------------------------------------

def test_to_a2a_task_status_authentication() -> None:
    err = _make_error(category=ErrorCategory.authentication, requires_human=False)
    result = to_a2a_task_status(err, task_id="task-xyz")
    assert result["state"] == "AUTH_REQUIRED"


# ---------------------------------------------------------------------------
# 9. to_a2a_task_status — default -> FAILED
# ---------------------------------------------------------------------------

def test_to_a2a_task_status_default_failed() -> None:
    err = _make_error(category=ErrorCategory.upstream, requires_human=False)
    result = to_a2a_task_status(err, task_id="task-123")
    assert result["state"] == "FAILED"


def test_to_a2a_task_status_requires_human_overrides_auth() -> None:
    """requires_human takes priority over authentication category."""
    err = _make_error(category=ErrorCategory.authentication, requires_human=True)
    result = to_a2a_task_status(err, task_id="task-999")
    assert result["state"] == "INPUT_REQUIRED"


# ---------------------------------------------------------------------------
# 10. to_ws_error
# ---------------------------------------------------------------------------

def test_to_ws_error_type_field() -> None:
    err = _make_error()
    result = to_ws_error(err)
    assert result["type"] == "error"


def test_to_ws_error_contains_error_fields() -> None:
    err = _make_error(message="WS failure", recovery_hint="Reconnect")
    result = to_ws_error(err)
    assert result["error_code"] == "TEST_ERROR"
    assert result["message"] == "WS failure"
    assert result["recovery_hint"] == "Reconnect"
    assert result["severity"] == ErrorSeverity.transient
    assert result["category"] == ErrorCategory.internal


def test_to_ws_error_excludes_none_fields() -> None:
    err = _make_error()
    result = to_ws_error(err)
    # optional fields with None values should be excluded (model_dump exclude_none=True)
    assert "suggested_action" not in result
    assert "retry_after_s" not in result
    assert "escalation_type" not in result
    assert "details" not in result


# ---------------------------------------------------------------------------
# 11. KNOWN_ERRORS registry
# ---------------------------------------------------------------------------

def test_known_errors_all_valid_structured_errors() -> None:
    for key, err in KNOWN_ERRORS.items():
        assert isinstance(err, StructuredError), f"{key} is not a StructuredError"
        assert err.error_code == key, (
            f"Key '{key}' does not match error_code '{err.error_code}'"
        )


def test_known_errors_has_expected_codes() -> None:
    # At least the original 17 + Wave 33 additions
    assert len(KNOWN_ERRORS) >= 35
    # Spot-check some critical entries
    for key in ("WORKSPACE_NOT_FOUND", "COLONY_NOT_FOUND", "INTERNAL_ERROR",
                "INVALID_JSON", "LIMIT_INVALID", "CREDENTIAL_DETECTED"):
        assert key in KNOWN_ERRORS, f"missing {key}"


def test_known_errors_required_fields_populated() -> None:
    for key, err in KNOWN_ERRORS.items():
        assert err.error_code, f"{key}: error_code is empty"
        assert err.message, f"{key}: message is empty"
        assert err.recovery_hint, f"{key}: recovery_hint is empty"
        assert isinstance(err.severity, ErrorSeverity), f"{key}: invalid severity"
        assert isinstance(err.category, ErrorCategory), f"{key}: invalid category"


# ---------------------------------------------------------------------------
# 12. ErrorSeverity and ErrorCategory enum values
# ---------------------------------------------------------------------------

def test_error_severity_string_values() -> None:
    assert ErrorSeverity.transient == "transient"
    assert ErrorSeverity.permanent == "permanent"
    assert ErrorSeverity.degraded == "degraded"
    for member in ErrorSeverity:
        assert isinstance(member.value, str)


def test_error_category_string_values() -> None:
    assert ErrorCategory.validation == "validation"
    assert ErrorCategory.authentication == "authentication"
    assert ErrorCategory.rate_limit == "rate_limit"
    assert ErrorCategory.not_found == "not_found"
    assert ErrorCategory.conflict == "conflict"
    assert ErrorCategory.upstream == "upstream"
    assert ErrorCategory.internal == "internal"
    assert ErrorCategory.input_required == "input_required"
    for member in ErrorCategory:
        assert isinstance(member.value, str)
