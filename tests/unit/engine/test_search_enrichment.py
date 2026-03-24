"""Tests for confidence tier and annotation helpers (Wave 33.5 Team 2)."""

from __future__ import annotations

from formicos.engine.runner import _confidence_tier, _format_confidence_annotation


class TestConfidenceTier:
    """Verify _confidence_tier classification logic."""

    def test_high_tier_with_strong_posterior(self) -> None:
        item = {"conf_alpha": 20.0, "conf_beta": 5.0, "status": "stable"}
        assert _confidence_tier(item) == "HIGH"

    def test_exploratory_tier_with_few_observations(self) -> None:
        item = {"conf_alpha": 2.0, "conf_beta": 2.0, "status": "candidate"}
        assert _confidence_tier(item) == "EXPLORATORY"

    def test_stale_tier_from_status(self) -> None:
        item = {"conf_alpha": 20.0, "conf_beta": 5.0, "status": "stale"}
        assert _confidence_tier(item) == "STALE"

    def test_moderate_tier(self) -> None:
        item = {"conf_alpha": 8.0, "conf_beta": 7.0, "status": "candidate"}
        assert _confidence_tier(item) == "MODERATE"

    def test_low_tier(self) -> None:
        item = {"conf_alpha": 4.0, "conf_beta": 12.0, "status": "candidate"}
        assert _confidence_tier(item) == "LOW"

    def test_fallback_from_scalar_confidence(self) -> None:
        """When conf_alpha/conf_beta are absent, use scalar confidence."""
        item = {"confidence": 0.8}
        tier = _confidence_tier(item)
        assert tier in ("HIGH", "MODERATE", "EXPLORATORY")


class TestFormatConfidenceAnnotation:
    """Verify _format_confidence_annotation output."""

    def test_includes_tier_and_observations(self) -> None:
        item = {"conf_alpha": 20.0, "conf_beta": 5.0, "status": "stable"}
        annotation = _format_confidence_annotation(item)
        assert "HIGH" in annotation
        assert "23 observations" in annotation
        assert "stable" in annotation

    def test_decay_class_displayed(self) -> None:
        item = {"conf_alpha": 20.0, "conf_beta": 5.0, "status": "stale"}
        annotation = _format_confidence_annotation(item)
        assert "decaying" in annotation

    def test_federation_source_shown(self) -> None:
        item = {
            "conf_alpha": 10.0, "conf_beta": 3.0,
            "status": "candidate", "source_peer": "peer-42",
        }
        annotation = _format_confidence_annotation(item)
        assert "via peer-42" in annotation

    def test_exploratory_no_observations(self) -> None:
        item = {"conf_alpha": 1.5, "conf_beta": 1.5, "status": "candidate"}
        annotation = _format_confidence_annotation(item)
        assert "EXPLORATORY" in annotation

    def test_ephemeral_item_minimal_annotation(self) -> None:
        """Item with no alpha/beta and no status still produces output."""
        item: dict[str, object] = {}
        annotation = _format_confidence_annotation(item)
        assert "Confidence:" in annotation
