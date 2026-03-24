"""Tests for DecayClass StrEnum and gamma hardening (Wave 33 A4)."""

from __future__ import annotations

import pytest

from formicos.core.types import DecayClass, MemoryEntry
from formicos.surface.knowledge_constants import (
    GAMMA_PER_DAY,
    GAMMA_RATES,
    MAX_ELAPSED_DAYS,
)


class TestDecayClass:
    def test_values(self) -> None:
        assert DecayClass.ephemeral == "ephemeral"
        assert DecayClass.stable == "stable"
        assert DecayClass.permanent == "permanent"

    def test_from_string(self) -> None:
        assert DecayClass("ephemeral") is DecayClass.ephemeral
        assert DecayClass("stable") is DecayClass.stable
        assert DecayClass("permanent") is DecayClass.permanent

    def test_invalid_raises(self) -> None:
        with pytest.raises(ValueError):
            DecayClass("invalid")


class TestGammaRates:
    def test_ephemeral_matches_legacy(self) -> None:
        assert GAMMA_RATES["ephemeral"] == GAMMA_PER_DAY

    def test_stable_slower(self) -> None:
        assert GAMMA_RATES["stable"] > GAMMA_RATES["ephemeral"]
        assert GAMMA_RATES["stable"] < 1.0

    def test_permanent_no_decay(self) -> None:
        assert GAMMA_RATES["permanent"] == 1.0

    def test_all_classes_covered(self) -> None:
        for dc in DecayClass:
            assert dc.value in GAMMA_RATES


class TestMaxElapsedDays:
    def test_value(self) -> None:
        assert MAX_ELAPSED_DAYS == 180.0

    def test_ephemeral_converges_at_cap(self) -> None:
        gamma = GAMMA_RATES["ephemeral"]
        gamma_eff = gamma ** MAX_ELAPSED_DAYS
        # At 180 days, gamma_eff < 0.03 -- effectively at prior
        assert gamma_eff < 0.03

    def test_365_days_same_as_180(self) -> None:
        gamma = GAMMA_RATES["ephemeral"]
        capped = min(365, MAX_ELAPSED_DAYS)
        assert capped == MAX_ELAPSED_DAYS
        # The cap means 365 days produces the same result as 180
        gamma_180 = gamma ** 180.0
        gamma_capped = gamma ** capped
        assert gamma_180 == gamma_capped

    def test_permanent_ignores_cap(self) -> None:
        gamma = GAMMA_RATES["permanent"]
        # permanent gamma = 1.0, so any exponent = 1.0
        assert gamma ** MAX_ELAPSED_DAYS == 1.0
        assert gamma ** 365 == 1.0

    def test_stable_half_life(self) -> None:
        gamma = GAMMA_RATES["stable"]
        import math

        half_life = -math.log(2) / math.log(gamma)
        assert 130 < half_life < 150  # ~139 days


class TestMemoryEntryDecayClass:
    def test_default_is_ephemeral(self) -> None:
        entry = MemoryEntry(
            id="test-1",
            entry_type="skill",
            title="test",
            content="test content here long enough",
            source_colony_id="col-1",
            source_artifact_ids=[],
        )
        assert entry.decay_class == DecayClass.ephemeral

    def test_explicit_stable(self) -> None:
        entry = MemoryEntry(
            id="test-1",
            entry_type="skill",
            title="test",
            content="test content here long enough",
            source_colony_id="col-1",
            source_artifact_ids=[],
            decay_class=DecayClass.stable,
        )
        assert entry.decay_class == DecayClass.stable

    def test_roundtrip_via_model_dump(self) -> None:
        entry = MemoryEntry(
            id="test-1",
            entry_type="skill",
            title="test",
            content="test content here long enough",
            source_colony_id="col-1",
            source_artifact_ids=[],
            decay_class=DecayClass.permanent,
        )
        dumped = entry.model_dump()
        assert dumped["decay_class"] == "permanent"
