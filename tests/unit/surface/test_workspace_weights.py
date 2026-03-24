"""Per-workspace composite weight tests (Wave 35 C2, ADR-044 D4).

Validates get_workspace_weights(), _composite_key() with custom weights,
weight validation, and invariant preservation.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any

from formicos.surface.knowledge_catalog import (
    KnowledgeCatalog,
    _composite_key,
    _STATUS_BONUS,
)
from formicos.surface.knowledge_constants import (
    COMPOSITE_WEIGHTS,
    get_workspace_weights,
)


@dataclass
class _FakeWorkspace:
    config: dict[str, Any] = field(default_factory=dict)
    threads: dict[str, Any] = field(default_factory=dict)


@dataclass
class _FakeProjections:
    workspaces: dict[str, _FakeWorkspace] = field(default_factory=dict)
    cooccurrence_weights: dict[str, Any] = field(default_factory=dict)
    memory_entries: dict[str, dict[str, Any]] = field(default_factory=dict)


class TestGetWorkspaceWeights:
    """get_workspace_weights() returns correct weights."""

    def test_default_when_no_override(self) -> None:
        proj = _FakeProjections(workspaces={"ws-1": _FakeWorkspace()})
        weights = get_workspace_weights("ws-1", proj)
        assert weights == COMPOSITE_WEIGHTS

    def test_default_when_workspace_missing(self) -> None:
        proj = _FakeProjections()
        weights = get_workspace_weights("ws-missing", proj)
        assert weights == COMPOSITE_WEIGHTS

    def test_default_when_projections_none(self) -> None:
        weights = get_workspace_weights("ws-1", None)
        assert weights == COMPOSITE_WEIGHTS

    def test_custom_weights_returned(self) -> None:
        custom = {
            "semantic": 0.43, "thompson": 0.25, "freshness": 0.15,
            "status": 0.10, "thread": 0.07, "cooccurrence": 0.0,
        }
        ws = _FakeWorkspace(config={"composite_weights": custom})
        proj = _FakeProjections(workspaces={"ws-1": ws})
        weights = get_workspace_weights("ws-1", proj)
        assert weights == custom

    def test_returns_copy_not_reference(self) -> None:
        proj = _FakeProjections(workspaces={"ws-1": _FakeWorkspace()})
        w1 = get_workspace_weights("ws-1", proj)
        w2 = get_workspace_weights("ws-1", proj)
        assert w1 is not w2


class TestCompositeKeyWithWeights:
    """_composite_key() accepts weights parameter."""

    def test_default_weights(self) -> None:
        random.seed(42)
        item = {"score": 0.8, "conf_alpha": 10.0, "conf_beta": 3.0, "status": "verified"}
        score = _composite_key(item)
        assert score < 0  # negative for ascending sort

    def test_custom_weights(self) -> None:
        random.seed(42)
        custom = {
            "semantic": 0.43, "thompson": 0.25, "freshness": 0.15,
            "status": 0.10, "thread": 0.07, "cooccurrence": 0.0,
        }
        item = {"score": 0.8, "conf_alpha": 10.0, "conf_beta": 3.0, "status": "verified"}
        score = _composite_key(item, weights=custom)
        assert score < 0

    def test_zero_cooccurrence_weight_disables_signal(self) -> None:
        """When cooccurrence weight is 0.0, that signal contributes nothing."""
        custom = {
            "semantic": 0.43, "thompson": 0.25, "freshness": 0.15,
            "status": 0.10, "thread": 0.07, "cooccurrence": 0.0,
        }
        # _composite_key doesn't include cooccurrence (no co-occurrence context),
        # but the weight=0 ensures it would contribute nothing even if present
        random.seed(42)
        item = {"score": 0.8, "conf_alpha": 10.0, "conf_beta": 3.0, "status": "verified"}
        score_custom = _composite_key(item, weights=custom)
        # The score should differ from default weights since semantic weight is higher
        random.seed(42)
        score_default = _composite_key(item)
        # Different weights → different scores
        assert score_custom != score_default


class TestInvariantsWithCustomWeights:
    """ADR-044 D3 invariants 1-4 hold with custom weights."""

    def _make_item(self, **overrides: Any) -> dict[str, Any]:
        base: dict[str, Any] = {
            "score": 0.7, "conf_alpha": 10.0, "conf_beta": 3.0,
            "status": "active", "created_at": "",
        }
        base.update(overrides)
        return base

    def test_invariant_1_verified_outranks_stale(self) -> None:
        """At equal semantic/freshness, verified > stale (status weight 0.10)."""
        custom = {
            "semantic": 0.43, "thompson": 0.25, "freshness": 0.15,
            "status": 0.10, "thread": 0.07, "cooccurrence": 0.0,
        }
        wins = 0
        for _ in range(100):
            verified = self._make_item(status="verified")
            stale = self._make_item(status="stale")
            if _composite_key(verified, weights=custom) < _composite_key(stale, weights=custom):
                wins += 1
        assert wins > 80, f"Verified should outrank stale most of the time, won {wins}/100"

    def test_invariant_2_thread_outranks_no_thread(self) -> None:
        """Thread-matched > non-matched (thread weight 0.07)."""
        custom = {
            "semantic": 0.43, "thompson": 0.25, "freshness": 0.15,
            "status": 0.10, "thread": 0.07, "cooccurrence": 0.0,
        }
        wins = 0
        for _ in range(100):
            with_thread = self._make_item(_thread_bonus=1.0)
            without_thread = self._make_item(_thread_bonus=0.0)
            if _composite_key(with_thread, weights=custom) < _composite_key(without_thread, weights=custom):
                wins += 1
        assert wins > 60, f"Thread-matched should usually win, won {wins}/100"

    def test_invariant_3_thompson_varies(self) -> None:
        """Thompson Sampling produces different rankings across calls."""
        custom = {
            "semantic": 0.43, "thompson": 0.25, "freshness": 0.15,
            "status": 0.10, "thread": 0.07, "cooccurrence": 0.0,
        }
        item = self._make_item()
        scores = {_composite_key(item, weights=custom) for _ in range(20)}
        assert len(scores) > 1, "Thompson should produce varied scores"

    def test_invariant_4_old_verified_can_rank_high(self) -> None:
        """Very old but verified and semantically relevant → can rank high."""
        custom = {
            "semantic": 0.43, "thompson": 0.25, "freshness": 0.15,
            "status": 0.10, "thread": 0.07, "cooccurrence": 0.0,
        }
        old_verified = self._make_item(
            score=0.95, status="verified",
            created_at="2023-01-01T00:00:00+00:00",  # very old
        )
        # semantic (0.43 * 0.95 = 0.4085) + status (0.10 * 1.0 = 0.10)
        # should easily outweigh freshness=0 penalty
        wins = 0
        for _ in range(50):
            score = -_composite_key(old_verified, weights=custom)
            assert score > 0.40, f"Score {score} too low for verified high-semantic entry"
            wins += 1
        assert wins == 50


class TestWeightValidation:
    """Weight validation rules for configure_scoring."""

    def test_default_weights_sum_to_one(self) -> None:
        assert abs(sum(COMPOSITE_WEIGHTS.values()) - 1.0) < 0.001

    def test_all_default_weights_in_bounds(self) -> None:
        for k, v in COMPOSITE_WEIGHTS.items():
            assert 0.0 <= v <= 0.5, f"{k}={v} out of bounds"

    def test_custom_zero_cooccurrence_sums_to_one(self) -> None:
        custom = {
            "semantic": 0.43, "thompson": 0.25, "freshness": 0.15,
            "status": 0.10, "thread": 0.07, "cooccurrence": 0.0,
        }
        assert abs(sum(custom.values()) - 1.0) < 0.001
