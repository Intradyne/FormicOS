"""Round-result data models extracted from runner.py for navigability.

All models are frozen Pydantic BaseModels used as return types from the
round execution pipeline.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from pydantic import BaseModel, ConfigDict

from formicos.core.events import FormicOSEvent
from formicos.core.types import KnowledgeAccessItem, WorkspaceExecutionResult

_FrozenCfg = ConfigDict(frozen=True)


class ToolExecutionResult(BaseModel):
    """Internal tool execution result used for round-level governance signals."""

    model_config = _FrozenCfg

    content: str
    code_execute_succeeded: bool = False
    code_execute_failed: bool = False
    workspace_execute_result: WorkspaceExecutionResult | None = None


# Type alias for injectable code_execute handler (avoids engine->adapters import)
CodeExecuteHandler = Callable[
    [dict[str, Any], str, str, str, Callable[[FormicOSEvent], Any]],
    Awaitable[ToolExecutionResult],
]

# Type alias for injectable workspace_execute handler (Wave 41 B1)
WorkspaceExecuteHandler = Callable[
    [str, str, int],  # command, working_dir, timeout_s
    Awaitable[WorkspaceExecutionResult],
]


class ConvergenceResult(BaseModel):
    model_config = _FrozenCfg
    score: float
    goal_alignment: float
    stability: float
    progress: float
    is_stalled: bool
    is_converged: bool


class GovernanceDecision(BaseModel):
    model_config = _FrozenCfg
    action: str  # "continue" | "complete" | "warn" | "halt" | "force_halt"
    reason: str


class ValidatorResult(BaseModel):
    """Wave 39 1B: deterministic task-type validation result."""

    model_config = _FrozenCfg
    task_type: str  # "code" | "research" | "documentation" | "review" | "unknown"
    verdict: str  # "pass" | "fail" | "inconclusive"
    reason: str


class CrossFileValidationResult(BaseModel):
    """Wave 41 B3: cross-file consistency validation for multi-file changes."""

    model_config = _FrozenCfg
    verdict: str  # "pass" | "fail" | "inconclusive" | "not_applicable"
    reason: str
    files_checked: list[str] = []
    issues: list[str] = []


class RoundResult(BaseModel):
    model_config = _FrozenCfg
    round_number: int
    convergence: ConvergenceResult
    governance: GovernanceDecision
    cost: float
    duration_ms: int
    round_summary: str
    outputs: dict[str, str]
    updated_weights: dict[tuple[str, str], float]
    retrieved_skill_ids: list[str] = []
    knowledge_items_used: list[KnowledgeAccessItem] = []  # Wave 28
    stall_count: int = 0  # accumulated stall streak (passed back for next round)
    recent_successful_code_execute: bool = False
    recent_productive_action: bool = False  # Wave 55: broader than code_execute
    productive_calls: int = 0  # Wave 54.5: count of productive tool calls
    total_calls: int = 0  # Wave 54.5: count of all tool calls
    validator: ValidatorResult | None = None  # Wave 39 1B
    cross_file_validation: CrossFileValidationResult | None = None  # Wave 41 B3
