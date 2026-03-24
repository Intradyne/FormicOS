"""Tests for Wave 58 specificity gate in context assembly."""

from __future__ import annotations

from formicos.engine import context as ctx


def test_should_inject_knowledge_skip_general() -> None:
    """General task + low similarity + no trajectories → skip."""
    result = ctx._should_inject_knowledge(
        round_goal="implement a token bucket rate limiter",
        knowledge_items=[
            {"similarity": 0.41, "title": "Email Validation", "sub_type": "technique"},
        ],
    )
    assert result is False


def test_should_inject_knowledge_inject_project() -> None:
    """Project-specific signal in goal → inject."""
    result = ctx._should_inject_knowledge(
        round_goal="fix our auth middleware token refresh",
        knowledge_items=[
            {"similarity": 0.35, "title": "Auth Patterns", "sub_type": "technique"},
        ],
    )
    assert result is True


def test_should_inject_knowledge_inject_high_similarity() -> None:
    """High similarity entry → inject even for general task."""
    result = ctx._should_inject_knowledge(
        round_goal="parse CSV and compute statistics",
        knowledge_items=[
            {"similarity": 0.67, "title": "CSV Parsing Patterns", "sub_type": "technique"},
        ],
    )
    assert result is True


def test_specificity_gate_env_disable(monkeypatch: object) -> None:
    """Gate disabled via env var → always inject."""
    import pytest  # noqa: PLC0415

    mp = pytest.MonkeyPatch() if not hasattr(monkeypatch, "setattr") else monkeypatch  # type: ignore[union-attr]
    mp.setattr(ctx, "_SPECIFICITY_GATE_ENABLED", False)  # type: ignore[union-attr]
    try:
        result = ctx._should_inject_knowledge(
            round_goal="implement a rate limiter",
            knowledge_items=[
                {"similarity": 0.30, "sub_type": "technique"},
            ],
        )
        assert result is True
    finally:
        mp.undo()  # type: ignore[union-attr]


def test_should_inject_knowledge_inject_trajectory() -> None:
    """Trajectory entry present → always inject."""
    result = ctx._should_inject_knowledge(
        round_goal="write a haiku about spring",
        knowledge_items=[
            {"similarity": 0.30, "title": "Trajectory: creative", "sub_type": "trajectory"},
        ],
    )
    assert result is True
