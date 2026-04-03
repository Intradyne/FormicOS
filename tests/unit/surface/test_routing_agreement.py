"""Wave 84.5 Track B: Routing drift golden tests.

Deterministic golden-test suite for the routing classifiers. No LLM needed.
These catch regressions when classifier keywords or thresholds change.
"""

from __future__ import annotations

import pytest

from formicos.surface.planning_policy import decide_planning_route
from formicos.surface.queen_runtime import (
    _looks_like_colony_work,
    _prefer_single_colony_route,
    classify_complexity,
)
from formicos.surface.task_classifier import classify_task

# ── Golden route expectations ──
# (prompt, task_class, complexity, is_colony_work, prefers_single)

GOLDEN_ROUTES = [
    # Simple single-file tasks → fast_path candidates
    (
        "Write tests for checkpoint.py",
        "code_implementation", "simple", True, True,
    ),
    (
        "Fix the typo in README.md",
        "code_implementation", "simple", True, True,
    ),
    (
        "Fix the SSRF validator to block RFC 1918 ranges",
        "code_implementation", "simple", True, True,
    ),
    (
        "Add a docstring to the save_pattern function",
        "code_implementation", "simple", True, True,
    ),

    # Multi-file / complex tasks
    # Note: "multi-file" is simple by word count/length; classifier
    # keywords matter more than human intuition about complexity.
    (
        "Build a multi-file addon with scanner, coverage, quality, handlers, and tests",
        "code_implementation", "simple", True, True,
    ),
    (
        "Refactor the auth module across runner.py, types.py, colony_manager.py, and runtime.py",
        "generic", "complex", True, False,
    ),
    (
        "Implement a new federation protocol with push, pull, and conflict resolution",
        "code_implementation", "complex", True, False,
    ),

    # Research / design tasks — these don't trigger colony_work
    # markers because the strong markers are implementation-focused.
    (
        "Research best practices for async event-loop debugging",
        "research", "complex", False, False,
    ),
    (
        "Design the architecture for a new plugin system",
        "design", "complex", False, False,
    ),

    # Review tasks
    (
        "Review the latest changes to queen_tools.py",
        "code_review", "complex", True, False,
    ),

    # Q&A / status tasks — "colony" keyword triggers complex
    (
        "What is the status of colony X?",
        "generic", "complex", False, False,
    ),
    (
        "How many events are in the union?",
        "generic", "simple", False, False,
    ),
    (
        "Hello",
        "generic", "simple", False, False,
    ),

    # Ambiguous but actionable — "improve" triggers colony_work
    (
        "Improve the auth module",
        "generic", "simple", True, True,
    ),
    # "strengthen" + "test" trigger colony_work, "knowledge" triggers complex
    (
        "Strengthen test coverage for the knowledge catalog",
        "generic", "complex", True, False,
    ),
]


@pytest.mark.parametrize(
    "prompt,expected_task_class,expected_complexity,expected_colony_work,expected_single",
    GOLDEN_ROUTES,
    ids=[r[0][:50] for r in GOLDEN_ROUTES],
)
def test_routing_agreement(
    prompt: str,
    expected_task_class: str,
    expected_complexity: str,
    expected_colony_work: bool,
    expected_single: bool,
) -> None:
    """Each golden prompt should produce consistent routing signals."""
    task_class, _cat = classify_task(prompt)
    assert task_class == expected_task_class, (
        f"classify_task({prompt!r}) = {task_class!r}, expected {expected_task_class!r}"
    )

    complexity = classify_complexity(prompt)
    assert complexity == expected_complexity, (
        f"classify_complexity({prompt!r}) = {complexity!r}, expected {expected_complexity!r}"
    )

    colony_work = _looks_like_colony_work(prompt)
    assert colony_work == expected_colony_work, (
        f"_looks_like_colony_work({prompt!r}) = {colony_work!r}, expected {expected_colony_work!r}"
    )

    single = _prefer_single_colony_route(prompt)
    assert single == expected_single, (
        f"_prefer_single_colony_route({prompt!r}) = {single!r}, expected {expected_single!r}"
    )


class TestClassifierCoherence:
    """Cross-classifier invariant tests."""

    def test_simple_non_colony_never_prefers_single(self) -> None:
        """If it's not colony work, single-colony preference must be False."""
        for prompt, _, _, colony_work, single in GOLDEN_ROUTES:
            if not colony_work:
                assert not single, (
                    f"Non-colony prompt {prompt!r} should not prefer single"
                )

    def test_complex_never_prefers_single(self) -> None:
        """Complex tasks should never prefer single-colony fast path."""
        for prompt, _, complexity, _, single in GOLDEN_ROUTES:
            if complexity == "complex":
                assert not single, (
                    f"Complex prompt {prompt!r} should not prefer single"
                )

    def test_playbook_hints_produce_valid_output(self) -> None:
        """Playbook hints should return valid structured text or None."""
        from formicos.engine.playbook_loader import (
            clear_cache,
            get_decomposition_hints,
        )

        clear_cache()
        for prompt, _task_class, *_ in GOLDEN_ROUTES:
            hint = get_decomposition_hints(prompt)
            if hint is not None:
                # Hint should be a structured line with conf=
                assert "conf=" in hint, (
                    f"Hint for {prompt!r} missing confidence: {hint!r}"
                )
                assert "colonies" in hint, (
                    f"Hint for {prompt!r} missing colony guidance: {hint!r}"
                )


# -- Wave 85 Track B: policy-level golden tests --


class TestPolicyGoldenRoutes:
    """Verify planning_policy produces consistent routes for golden prompts."""

    def test_fast_path_prompts(self) -> None:
        """Q&A and status prompts should route to fast_path."""
        for prompt in ["How many events are in the union?", "Hello"]:
            d = decide_planning_route(prompt)
            assert d.route == "fast_path", (
                f"Expected fast_path for {prompt!r}, got {d.route}"
            )

    def test_colony_work_routes_colony(self) -> None:
        """Implementation prompts should route to colony paths."""
        for prompt in [
            "Write tests for checkpoint.py",
            "Fix the typo in README.md",
        ]:
            d = decide_planning_route(prompt)
            assert d.route in ("single_colony", "parallel_dag"), (
                f"Expected colony route for {prompt!r}, got {d.route}"
            )

    def test_complex_colony_routes_dag(self) -> None:
        """Complex multi-file prompts should route to parallel_dag."""
        d = decide_planning_route(
            "Implement federation push, pull, and conflict resolution",
        )
        assert d.route == "parallel_dag"

    def test_policy_route_matches_classifier_trio(self) -> None:
        """Policy route should be consistent with the underlying classifiers."""
        for prompt, _, _, colony_work, single in GOLDEN_ROUTES:
            d = decide_planning_route(prompt)
            if not colony_work:
                # Non-colony-work should be fast_path
                assert d.route == "fast_path", (
                    f"Non-colony {prompt!r}: policy={d.route}"
                )
            if single:
                # Single-colony preference should produce single_colony
                assert d.route in ("single_colony", "parallel_dag"), (
                    f"Single-preferred {prompt!r}: policy={d.route}"
                )
