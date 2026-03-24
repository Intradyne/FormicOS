"""Shared deterministic task classifier (Wave 25 B1).

Consumed by Queen (queen_runtime.py) and A2A (routes/a2a.py).
Does NOT live in queen_runtime.py to avoid wrong dependency direction.

Classification is keyword-based: no LLM calls, fully deterministic.
The Queen's explicit choices (castes, rounds, budget) override these defaults.
"""

from __future__ import annotations

from typing import Any

TASK_CATEGORIES: dict[str, dict[str, Any]] = {
    "code_implementation": {
        "keywords": {
            "implement", "write", "build", "create", "code", "function",
            "script", "program", "develop", "fix", "debug",
        },
        "default_castes": ["coder", "reviewer"],
        "default_outputs": ["code", "test"],
        "default_rounds": 10,
        "default_budget": 2.0,
        "default_strategy": "stigmergic",
    },
    "code_review": {
        "keywords": {"review", "audit", "check", "inspect", "evaluate"},
        "default_castes": ["reviewer"],
        "default_outputs": ["report"],
        "default_rounds": 5,
        "default_budget": 1.0,
        "default_strategy": "sequential",
    },
    "research": {
        "keywords": {
            "research", "summarize", "analyze", "explain", "compare",
            "investigate", "describe",
        },
        "default_castes": ["researcher"],
        "default_outputs": ["document"],
        "default_rounds": 8,
        "default_budget": 1.0,
        "default_strategy": "sequential",
    },
    "design": {
        "keywords": {"design", "architect", "plan", "schema", "api", "structure"},
        "default_castes": ["coder", "reviewer"],
        "default_outputs": ["schema", "document"],
        "default_rounds": 10,
        "default_budget": 2.0,
        "default_strategy": "stigmergic",
    },
    "creative": {
        "keywords": {"haiku", "poem", "story", "essay", "translate"},
        "default_castes": ["researcher"],
        "default_outputs": ["document"],
        "default_rounds": 3,
        "default_budget": 0.5,
        "default_strategy": "sequential",
    },
}

_GENERIC_CATEGORY: dict[str, Any] = {
    "default_castes": ["coder", "reviewer"],
    "default_outputs": ["generic"],
    "default_rounds": 10,
    "default_budget": 2.0,
    "default_strategy": "stigmergic",
}


def classify_task(description: str) -> tuple[str, dict[str, Any]]:
    """Classify a task by keyword matching.

    Returns ``(category_name, category_dict)`` where *category_dict*
    contains ``default_castes``, ``default_outputs``, ``default_rounds``,
    ``default_budget``, and ``default_strategy``.
    """
    words = set(description.lower().split())
    best_name = "generic"
    best_cat = _GENERIC_CATEGORY
    best_overlap = 0
    for name, cat in TASK_CATEGORIES.items():
        overlap = len(words & cat["keywords"])
        if overlap > best_overlap:
            best_name, best_cat, best_overlap = name, cat, overlap
    return best_name, best_cat


__all__ = ["TASK_CATEGORIES", "classify_task"]
