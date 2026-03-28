"""Dynamic Queen context budget (ADR-051).

Proportional slot budgeting derived from the model's context window, with
current defaults as the floor.  Every slot uses ``max(fallback, proportional)``
so proportional scaling may grow budgets but never shrinks them below today's
effective defaults.

Wave 71.0: expanded from 7 to 9 slots — added ``operating_procedures`` and
``queen_journal`` for durable operational memory.
"""

from __future__ import annotations

from dataclasses import dataclass

import structlog

log = structlog.get_logger()

# Approximate chars-per-token ratio for budget estimation.
_CHARS_PER_TOKEN = 4

# ---------------------------------------------------------------------------
# Slot fractions (sum to 1.0) and fallback floors
# ---------------------------------------------------------------------------

_FRACTIONS = {
    "system_prompt": 0.15,
    "memory_retrieval": 0.13,
    "project_context": 0.08,
    "project_plan": 0.05,
    "operating_procedures": 0.05,
    "queen_journal": 0.04,
    "thread_context": 0.13,
    "tool_memory": 0.09,
    "conversation_history": 0.28,
}

_FALLBACKS = {
    "system_prompt": 2000,
    "memory_retrieval": 1500,
    "project_context": 500,
    "project_plan": 400,
    "operating_procedures": 400,
    "queen_journal": 300,
    "thread_context": 1500,
    "tool_memory": 4000,
    "conversation_history": 6000,
}


@dataclass(frozen=True)
class QueenContextBudget:
    """Token budget for each Queen context slot."""

    system_prompt: int
    memory_retrieval: int
    project_context: int
    project_plan: int
    operating_procedures: int
    queen_journal: int
    thread_context: int
    tool_memory: int
    conversation_history: int


# Singleton fallback budget matching current hardcoded defaults.
FALLBACK_BUDGET = QueenContextBudget(**_FALLBACKS)


def compute_queen_budget(
    context_window: int | None,
    output_reserve: int,
) -> QueenContextBudget:
    """Compute proportional token budgets from the model's context window.

    Returns the fallback budget unchanged when *context_window* is missing,
    invalid, or too small to produce any proportional gain.
    """
    if context_window is None or context_window <= 0:
        return FALLBACK_BUDGET

    available = max(0, context_window - output_reserve)
    if available <= 0:
        return FALLBACK_BUDGET

    slots = {
        name: max(_FALLBACKS[name], int(available * frac))
        for name, frac in _FRACTIONS.items()
    }

    budget = QueenContextBudget(**slots)

    log.debug(
        "queen_budget.computed",
        context_window=context_window,
        output_reserve=output_reserve,
        available=available,
        slots={
            "system_prompt": budget.system_prompt,
            "memory_retrieval": budget.memory_retrieval,
            "project_context": budget.project_context,
            "project_plan": budget.project_plan,
            "operating_procedures": budget.operating_procedures,
            "queen_journal": budget.queen_journal,
            "thread_context": budget.thread_context,
            "tool_memory": budget.tool_memory,
            "conversation_history": budget.conversation_history,
        },
    )

    return budget
