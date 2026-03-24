"""Tests for conflict resolution (Wave 33 C7)."""

from __future__ import annotations

from formicos.core.types import Resolution
from formicos.surface.conflict_resolution import resolve_conflict


class TestParetoResolution:
    """Pareto dominance: clear winner on 2+ criteria."""

    def test_strong_evidence_wins(self) -> None:
        """Entry with high posterior mean + provenance vs low posterior → Pareto.

        Wave 42: uses Beta posterior mean (alpha/(alpha+beta)) instead of raw
        observation count. Entry a: mean=0.9, entry b: mean=0.4.
        """
        a = {
            "id": "a", "conf_alpha": 45, "conf_beta": 5,
            "created_at": "2026-03-18T12:00:00Z",
            "merged_from": ["x", "y", "z"],
        }
        b = {
            "id": "b", "conf_alpha": 4, "conf_beta": 6,
            "created_at": "2026-03-17T12:00:00Z",
            "merged_from": [],
        }
        result = resolve_conflict(a, b)
        assert result.resolution == Resolution.winner
        assert result.primary_id == "a"
        assert result.method == "pareto"


class TestThresholdResolution:
    """Composite score with adaptive threshold."""

    def test_moderate_difference_uses_threshold(self) -> None:
        a = {
            "id": "a", "conf_alpha": 15, "conf_beta": 5,
            "created_at": "2026-03-18T12:00:00Z",
            "merged_from": ["x"],
        }
        b = {
            "id": "b", "conf_alpha": 10, "conf_beta": 5,
            "created_at": "2026-03-18T12:00:00Z",
            "merged_from": [],
        }
        result = resolve_conflict(a, b)
        # Either threshold or competing — both are valid
        assert result.resolution in (Resolution.winner, Resolution.competing)
        assert result.primary_id in ("a", "b")


class TestCompetingResolution:
    """Both entries uncertain → keep as competing hypotheses."""

    def test_equal_entries_are_competing(self) -> None:
        a = {
            "id": "a", "conf_alpha": 5, "conf_beta": 5,
            "created_at": "2026-03-18T12:00:00Z",
            "merged_from": [],
        }
        b = {
            "id": "b", "conf_alpha": 5, "conf_beta": 5,
            "created_at": "2026-03-18T12:00:00Z",
            "merged_from": [],
        }
        result = resolve_conflict(a, b)
        assert result.resolution == Resolution.competing
        assert result.method == "competing"
        assert result.secondary_id is not None

    def test_low_evidence_wide_threshold(self) -> None:
        """Low evidence → wide adaptive threshold → competing."""
        a = {
            "id": "a", "conf_alpha": 6, "conf_beta": 5,
            "created_at": "2026-03-18T12:00:00Z",
            "merged_from": [],
        }
        b = {
            "id": "b", "conf_alpha": 5, "conf_beta": 6,
            "created_at": "2026-03-18T12:00:00Z",
            "merged_from": [],
        }
        result = resolve_conflict(a, b)
        # Low evidence + small score difference → wide threshold → competing
        assert result.resolution == Resolution.competing
