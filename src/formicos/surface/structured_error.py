"""Structured error model and surface mappers (Wave 32.5).

Foundation for unified error handling across MCP, A2A, AG-UI, WebSocket,
and REST surfaces. This module defines the model and mappers — wiring
into actual surface handlers happens in a future pass.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class ErrorSeverity(StrEnum):
    transient = "transient"
    permanent = "permanent"
    degraded = "degraded"


class ErrorCategory(StrEnum):
    validation = "validation"
    authentication = "authentication"
    rate_limit = "rate_limit"
    not_found = "not_found"
    conflict = "conflict"
    upstream = "upstream"
    internal = "internal"
    input_required = "input_required"


class SuggestedAction(BaseModel):
    description: str
    tool_name: str | None = None
    parameter_fixes: dict[str, Any] | None = None


class StructuredError(BaseModel):
    error_code: str
    message: str
    severity: ErrorSeverity
    category: ErrorCategory
    recovery_hint: str
    suggested_action: SuggestedAction | None = None
    retry_after_s: float | None = Field(default=None, ge=0)
    requires_human: bool = False
    escalation_type: str | None = None
    details: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# Surface mappers
# ---------------------------------------------------------------------------


def to_mcp_tool_error(err: StructuredError) -> dict[str, Any]:
    """Format for MCP tool error return (isError + dual content channels)."""
    return {
        "isError": True,
        "content": [
            {
                "type": "text",
                "text": f"Error: {err.message}. {err.recovery_hint}",
            },
        ],
        "structuredContent": {
            "error_code": err.error_code,
            "message": err.message,
            "severity": err.severity.value,
            "category": err.category.value,
            "recovery_hint": err.recovery_hint,
            "suggested_action": err.suggested_action.model_dump() if err.suggested_action else None,
            "retry_after_s": err.retry_after_s,
            "requires_human": err.requires_human,
        },
    }


def to_mcp_protocol_error(err: StructuredError) -> dict[str, Any]:
    """Format for MCP protocol-level error (JSON-RPC error object)."""
    code_map: dict[ErrorCategory, int] = {
        ErrorCategory.validation: -32602,
        ErrorCategory.not_found: -32602,
        ErrorCategory.conflict: -32600,
        ErrorCategory.internal: -32603,
    }
    return {
        "code": code_map.get(err.category, -32603),
        "message": err.message,
        "data": err.model_dump(exclude_none=True),
    }


_HTTP_STATUS: dict[ErrorCategory, int] = {
    ErrorCategory.validation: 400,
    ErrorCategory.authentication: 401,
    ErrorCategory.rate_limit: 429,
    ErrorCategory.not_found: 404,
    ErrorCategory.conflict: 409,
    ErrorCategory.upstream: 502,
    ErrorCategory.internal: 500,
    ErrorCategory.input_required: 422,
}


def to_http_error(err: StructuredError) -> tuple[int, dict[str, Any], dict[str, str]]:
    """Format for HTTP JSON error response."""
    status = _HTTP_STATUS.get(err.category, 500)
    body = err.model_dump(exclude_none=True)
    headers: dict[str, str] = {}
    if err.retry_after_s is not None and err.retry_after_s > 0:
        headers["Retry-After"] = str(int(err.retry_after_s))
    return (status, body, headers)


def to_a2a_task_status(err: StructuredError, task_id: str) -> dict[str, Any]:
    """Format for A2A task status update on error."""
    if err.requires_human:
        state = "INPUT_REQUIRED"
    elif err.category == ErrorCategory.authentication:
        state = "AUTH_REQUIRED"
    else:
        state = "FAILED"
    return {
        "task_id": task_id,
        "state": state,
        "error": err.model_dump(exclude_none=True),
    }


def to_ws_error(err: StructuredError) -> dict[str, Any]:
    """Format for WebSocket error frame."""
    return {
        "type": "error",
        **err.model_dump(exclude_none=True),
    }


# ---------------------------------------------------------------------------
# Known error registry
# ---------------------------------------------------------------------------

KNOWN_ERRORS: dict[str, StructuredError] = {
    "WORKSPACE_NOT_FOUND": StructuredError(
        error_code="WORKSPACE_NOT_FOUND",
        message="Workspace not found",
        severity=ErrorSeverity.permanent,
        category=ErrorCategory.not_found,
        recovery_hint="Check workspace ID with list_workspaces",
        suggested_action=SuggestedAction(
            description="List available workspaces", tool_name="list_workspaces"
        ),
    ),
    "TEMPLATE_NOT_FOUND": StructuredError(
        error_code="TEMPLATE_NOT_FOUND",
        message="Template not found",
        severity=ErrorSeverity.permanent,
        category=ErrorCategory.not_found,
        recovery_hint="Check template ID with list_templates",
        suggested_action=SuggestedAction(
            description="List available templates", tool_name="list_templates"
        ),
    ),
    "SERVICE_UNAVAILABLE": StructuredError(
        error_code="SERVICE_UNAVAILABLE",
        message="Service not available",
        severity=ErrorSeverity.transient,
        category=ErrorCategory.upstream,
        recovery_hint="Service dependency not started; retry after initialization",
    ),
    "INVALID_SERVICE_TYPE": StructuredError(
        error_code="INVALID_SERVICE_TYPE",
        message="Invalid service type",
        severity=ErrorSeverity.permanent,
        category=ErrorCategory.validation,
        recovery_hint="Check valid service types",
    ),
    "SERVICE_TIMEOUT": StructuredError(
        error_code="SERVICE_TIMEOUT",
        message="Service query timed out",
        severity=ErrorSeverity.transient,
        category=ErrorCategory.upstream,
        recovery_hint="Service took too long; retry with longer timeout or narrower scope",
        suggested_action=SuggestedAction(
            description="Retry with increased timeout", tool_name="query_service"
        ),
        retry_after_s=5.0,
    ),
    "COLONY_NOT_FOUND": StructuredError(
        error_code="COLONY_NOT_FOUND",
        message="Colony not found",
        severity=ErrorSeverity.permanent,
        category=ErrorCategory.not_found,
        recovery_hint="Colony may have completed or been killed",
        suggested_action=SuggestedAction(
            description="Check workspace status", tool_name="get_status"
        ),
    ),
    "INVALID_REQUEST": StructuredError(
        error_code="INVALID_REQUEST",
        message="Invalid request body",
        severity=ErrorSeverity.permanent,
        category=ErrorCategory.validation,
        recovery_hint="Send valid JSON request body",
    ),
    "MISSING_FIELD": StructuredError(
        error_code="MISSING_FIELD",
        message="Required field missing",
        severity=ErrorSeverity.permanent,
        category=ErrorCategory.validation,
        recovery_hint="Provide all required fields",
    ),
    "INVALID_PARAMETER": StructuredError(
        error_code="INVALID_PARAMETER",
        message="Invalid parameter value",
        severity=ErrorSeverity.permanent,
        category=ErrorCategory.validation,
        recovery_hint="Check parameter constraints",
    ),
    "TASK_NOT_FOUND": StructuredError(
        error_code="TASK_NOT_FOUND",
        message="Task not found",
        severity=ErrorSeverity.permanent,
        category=ErrorCategory.not_found,
        recovery_hint="Task ID may be wrong or colony never existed",
        suggested_action=SuggestedAction(description="List tasks", tool_name=None),
    ),
    "TASK_NOT_TERMINAL": StructuredError(
        error_code="TASK_NOT_TERMINAL",
        message="Task still running",
        severity=ErrorSeverity.transient,
        category=ErrorCategory.conflict,
        recovery_hint="Poll status or attach to event stream",
        retry_after_s=5.0,
    ),
    "TASK_ALREADY_TERMINAL": StructuredError(
        error_code="TASK_ALREADY_TERMINAL",
        message="Task already finished",
        severity=ErrorSeverity.permanent,
        category=ErrorCategory.conflict,
        recovery_hint="Task finished; retrieve result instead",
    ),
    "SERVICE_NOT_READY": StructuredError(
        error_code="SERVICE_NOT_READY",
        message="System component not initialized",
        severity=ErrorSeverity.transient,
        category=ErrorCategory.upstream,
        recovery_hint="Service dependency not loaded at startup",
        requires_human=True,
    ),
    "MODEL_NOT_FOUND": StructuredError(
        error_code="MODEL_NOT_FOUND",
        message="Model not found in registry",
        severity=ErrorSeverity.permanent,
        category=ErrorCategory.not_found,
        recovery_hint="Check model address with health inventory",
    ),
    "INVALID_STATE": StructuredError(
        error_code="INVALID_STATE",
        message="Operation not valid in current state",
        severity=ErrorSeverity.permanent,
        category=ErrorCategory.conflict,
        recovery_hint="Resource is in an incompatible state for this operation",
    ),
    "UNKNOWN_COMMAND": StructuredError(
        error_code="UNKNOWN_COMMAND",
        message="Unknown command",
        severity=ErrorSeverity.permanent,
        category=ErrorCategory.validation,
        recovery_hint="Check available commands",
    ),
    "INTERNAL_ERROR": StructuredError(
        error_code="INTERNAL_ERROR",
        message="Unexpected server error",
        severity=ErrorSeverity.transient,
        category=ErrorCategory.internal,
        recovery_hint="Unexpected error; check server logs",
    ),
    # Wave 33 B4: extended registry (35+ total)
    "THREAD_NOT_FOUND": StructuredError(
        error_code="THREAD_NOT_FOUND",
        message="Thread not found",
        severity=ErrorSeverity.permanent,
        category=ErrorCategory.not_found,
        recovery_hint="Check thread ID with get_status",
        suggested_action=SuggestedAction(
            description="Get workspace status", tool_name="get_status",
        ),
    ),
    "COLONY_RUNNING": StructuredError(
        error_code="COLONY_RUNNING",
        message="Colony is still running",
        severity=ErrorSeverity.transient,
        category=ErrorCategory.conflict,
        recovery_hint="Wait for colony to complete or kill it",
        retry_after_s=5.0,
    ),
    "COLONY_MANAGER_UNAVAILABLE": StructuredError(
        error_code="COLONY_MANAGER_UNAVAILABLE",
        message="Colony manager not available",
        severity=ErrorSeverity.transient,
        category=ErrorCategory.upstream,
        recovery_hint="System still initializing; retry shortly",
        retry_after_s=3.0,
    ),
    "BUDGET_EXCEEDED": StructuredError(
        error_code="BUDGET_EXCEEDED",
        message="Budget limit exceeded",
        severity=ErrorSeverity.permanent,
        category=ErrorCategory.validation,
        recovery_hint="Increase budget_limit or reduce scope",
    ),
    "INVALID_CASTES": StructuredError(
        error_code="INVALID_CASTES",
        message="Invalid caste configuration",
        severity=ErrorSeverity.permanent,
        category=ErrorCategory.validation,
        recovery_hint="Provide valid castes list with caste, tier, count",
    ),
    "MODEL_NOT_AVAILABLE": StructuredError(
        error_code="MODEL_NOT_AVAILABLE",
        message="Model not available",
        severity=ErrorSeverity.transient,
        category=ErrorCategory.upstream,
        recovery_hint="Model provider may be down; check health inventory",
        retry_after_s=10.0,
    ),
    "EMBEDDING_UNAVAILABLE": StructuredError(
        error_code="EMBEDDING_UNAVAILABLE",
        message="Embedding service not available",
        severity=ErrorSeverity.transient,
        category=ErrorCategory.upstream,
        recovery_hint="Qwen3 sidecar or sentence-transformers not loaded",
    ),
    "APPROVAL_NOT_FOUND": StructuredError(
        error_code="APPROVAL_NOT_FOUND",
        message="Approval request not found",
        severity=ErrorSeverity.permanent,
        category=ErrorCategory.not_found,
        recovery_hint="Check request_id; it may have expired or been handled",
    ),
    "STEP_NOT_FOUND": StructuredError(
        error_code="STEP_NOT_FOUND",
        message="Workflow step not found",
        severity=ErrorSeverity.permanent,
        category=ErrorCategory.not_found,
        recovery_hint="Check step index against thread workflow steps",
    ),
    "RATE_LIMITED": StructuredError(
        error_code="RATE_LIMITED",
        message="Rate limit exceeded",
        severity=ErrorSeverity.transient,
        category=ErrorCategory.rate_limit,
        recovery_hint="Too many requests; wait before retrying",
        retry_after_s=30.0,
    ),
    "CONTEXT_TOO_LARGE": StructuredError(
        error_code="CONTEXT_TOO_LARGE",
        message="Context exceeds model capacity",
        severity=ErrorSeverity.permanent,
        category=ErrorCategory.validation,
        recovery_hint="Reduce task scope, colony history, or knowledge context",
    ),
    "VECTOR_STORE_UNAVAILABLE": StructuredError(
        error_code="VECTOR_STORE_UNAVAILABLE",
        message="Vector store not available",
        severity=ErrorSeverity.transient,
        category=ErrorCategory.upstream,
        recovery_hint="Qdrant may not be running; check docker compose",
        retry_after_s=5.0,
    ),
    "KNOWLEDGE_CATALOG_UNAVAILABLE": StructuredError(
        error_code="KNOWLEDGE_CATALOG_UNAVAILABLE",
        message="Knowledge catalog not available",
        severity=ErrorSeverity.transient,
        category=ErrorCategory.upstream,
        recovery_hint="Knowledge system not initialized",
    ),
    "KNOWLEDGE_ITEM_NOT_FOUND": StructuredError(
        error_code="KNOWLEDGE_ITEM_NOT_FOUND",
        message="Knowledge entry not found",
        severity=ErrorSeverity.permanent,
        category=ErrorCategory.not_found,
        recovery_hint="Check item ID; entry may have been rejected or swept",
    ),
    "ALREADY_WORKSPACE_WIDE": StructuredError(
        error_code="ALREADY_WORKSPACE_WIDE",
        message="Entry is already workspace-wide",
        severity=ErrorSeverity.permanent,
        category=ErrorCategory.conflict,
        recovery_hint="Entry has no thread scope to promote from",
    ),
    "ARTIFACT_NOT_FOUND": StructuredError(
        error_code="ARTIFACT_NOT_FOUND",
        message="Artifact not found",
        severity=ErrorSeverity.permanent,
        category=ErrorCategory.not_found,
        recovery_hint="Check artifact ID; colony may have no artifacts",
    ),
    "FILE_NOT_FOUND": StructuredError(
        error_code="FILE_NOT_FOUND",
        message="File not found",
        severity=ErrorSeverity.permanent,
        category=ErrorCategory.not_found,
        recovery_hint="Check file name in workspace listing",
    ),
    "AST_BLOCKED": StructuredError(
        error_code="AST_BLOCKED",
        message="Code blocked by AST safety screen",
        severity=ErrorSeverity.permanent,
        category=ErrorCategory.validation,
        recovery_hint="Code contains patterns flagged as dangerous",
    ),
    "QUEEN_UNAVAILABLE": StructuredError(
        error_code="QUEEN_UNAVAILABLE",
        message="Queen agent not available",
        severity=ErrorSeverity.transient,
        category=ErrorCategory.upstream,
        recovery_hint="Queen not initialized; check startup logs",
    ),
    "CREDENTIAL_DETECTED": StructuredError(
        error_code="CREDENTIAL_DETECTED",
        message="Credential detected in content",
        severity=ErrorSeverity.permanent,
        category=ErrorCategory.validation,
        recovery_hint="Content contains embedded secrets; remove before retrying",
    ),
    "INVALID_JSON": StructuredError(
        error_code="INVALID_JSON",
        message="Invalid JSON in request body",
        severity=ErrorSeverity.permanent,
        category=ErrorCategory.validation,
        recovery_hint="Send a valid JSON request body",
    ),
    "QUERY_REQUIRED": StructuredError(
        error_code="QUERY_REQUIRED",
        message="Query parameter required",
        severity=ErrorSeverity.permanent,
        category=ErrorCategory.validation,
        recovery_hint="Provide the required query parameter",
    ),
    "LIMIT_INVALID": StructuredError(
        error_code="LIMIT_INVALID",
        message="Limit parameter must be an integer",
        severity=ErrorSeverity.permanent,
        category=ErrorCategory.validation,
        recovery_hint="Provide an integer value for limit",
    ),
    "DESCRIPTION_REQUIRED": StructuredError(
        error_code="DESCRIPTION_REQUIRED",
        message="Description is required",
        severity=ErrorSeverity.permanent,
        category=ErrorCategory.validation,
        recovery_hint="Provide a non-empty description field",
    ),
    "TASK_REQUIRED": StructuredError(
        error_code="TASK_REQUIRED",
        message="Task field is required",
        severity=ErrorSeverity.permanent,
        category=ErrorCategory.validation,
        recovery_hint="Provide a non-empty task field",
    ),
    "SPAWN_FAILED": StructuredError(
        error_code="SPAWN_FAILED",
        message="Colony spawn failed",
        severity=ErrorSeverity.transient,
        category=ErrorCategory.internal,
        recovery_hint="Check server logs; retry with simpler parameters",
    ),
    "NO_CASTES_LOADED": StructuredError(
        error_code="NO_CASTES_LOADED",
        message="No caste recipes loaded",
        severity=ErrorSeverity.permanent,
        category=ErrorCategory.internal,
        recovery_hint="Check caste_recipes.yaml exists and is valid",
        requires_human=True,
    ),
    "VALIDATION_FAILED": StructuredError(
        error_code="VALIDATION_FAILED",
        message="Request validation failed",
        severity=ErrorSeverity.permanent,
        category=ErrorCategory.validation,
        recovery_hint="Check request body against parameter constraints",
    ),
    # Wave 38: external specialist errors
    "EXTERNAL_SPECIALIST_UNAVAILABLE": StructuredError(
        error_code="EXTERNAL_SPECIALIST_UNAVAILABLE",
        message="External specialist service not configured or unreachable",
        severity=ErrorSeverity.transient,
        category=ErrorCategory.upstream,
        recovery_hint="Check NEMOCLAW_ENDPOINT environment variable and service availability",
        retry_after_s=10.0,
    ),
    "EXTERNAL_SPECIALIST_TIMEOUT": StructuredError(
        error_code="EXTERNAL_SPECIALIST_TIMEOUT",
        message="External specialist timed out",
        severity=ErrorSeverity.transient,
        category=ErrorCategory.upstream,
        recovery_hint="External specialist took too long; retry or increase timeout",
        retry_after_s=5.0,
    ),
    # Wave 38: A2A protocol consistency
    "A2A_METHOD_NOT_ALLOWED": StructuredError(
        error_code="A2A_METHOD_NOT_ALLOWED",
        message="HTTP method not supported for this A2A endpoint",
        severity=ErrorSeverity.permanent,
        category=ErrorCategory.validation,
        recovery_hint="Check A2A-TASKS.md for supported methods per endpoint",
    ),
}
