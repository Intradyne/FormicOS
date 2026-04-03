"""Wave 80 Track B: Playbook decomposition hints tests."""

from __future__ import annotations

from formicos.engine.playbook_loader import (
    clear_cache,
    get_decomposition_hints,
)


def setup_function() -> None:
    clear_cache()


def test_code_implementation_hint() -> None:
    hint = get_decomposition_hints("implement the auth module with tests")
    assert hint is not None
    assert "code_implementation" in hint
    assert "3-5" in hint
    assert "coder" in hint
    assert "stigmergic" in hint


def test_code_review_hint() -> None:
    hint = get_decomposition_hints("review the latest PR changes")
    assert hint is not None
    assert "code_review" in hint
    assert "reviewer" in hint


def test_design_hint() -> None:
    hint = get_decomposition_hints("design the new component architecture")
    assert hint is not None
    assert "design" in hint
    assert "2-3" in hint


def test_research_hint() -> None:
    hint = get_decomposition_hints("research best practices for caching")
    assert hint is not None
    assert "research" in hint
    assert "researcher" in hint


def test_generic_task_returns_hint_with_low_confidence() -> None:
    """Generic tasks should return a hint (conf >= 0.5) or None."""
    hint = get_decomposition_hints("do something general")
    # generic playbook has conf=0.5, so it should return a hint
    if hint is not None:
        assert "generic" in hint
        assert "conf=" in hint


def test_completely_unknown_returns_none_or_generic() -> None:
    hint = get_decomposition_hints("xyzzy")
    # Could be None (no keywords match) or generic
    if hint is not None:
        assert "conf=" in hint


def test_hint_includes_confidence() -> None:
    hint = get_decomposition_hints("implement the login feature")
    assert hint is not None
    assert "conf=1.00" in hint


def test_caching_returns_same_result() -> None:
    hint1 = get_decomposition_hints("implement feature X")
    hint2 = get_decomposition_hints("implement feature X")
    assert hint1 == hint2


def test_explicit_decomposition_takes_precedence() -> None:
    """The curated YAML decomposition block should be used, not defaults."""
    hint = get_decomposition_hints("implement file parser")
    assert hint is not None
    # code_implementation.yaml has explicit conf=1.0
    assert "conf=1.00" in hint
    # and explicit "group semantically related files"
    assert "group semantically related files" in hint
