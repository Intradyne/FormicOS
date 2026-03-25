"""Tests for Wave 64 Track 7 — trigger dispatcher."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from formicos.surface.trigger_dispatch import TriggerDispatcher, cron_matches
from formicos.surface.addon_loader import AddonTriggerSpec


# ---------------------------------------------------------------------------
# Cron matcher tests
# ---------------------------------------------------------------------------

class TestCronMatches:
    """Test the built-in cron matcher."""

    def test_every_minute(self) -> None:
        dt = datetime(2026, 3, 24, 10, 30, tzinfo=timezone.utc)
        assert cron_matches("* * * * *", dt) is True

    def test_specific_minute(self) -> None:
        dt = datetime(2026, 3, 24, 10, 30, tzinfo=timezone.utc)
        assert cron_matches("30 * * * *", dt) is True
        assert cron_matches("15 * * * *", dt) is False

    def test_specific_hour(self) -> None:
        dt = datetime(2026, 3, 24, 3, 0, tzinfo=timezone.utc)
        assert cron_matches("0 3 * * *", dt) is True
        assert cron_matches("0 4 * * *", dt) is False

    def test_step_syntax(self) -> None:
        dt = datetime(2026, 3, 24, 10, 15, tzinfo=timezone.utc)
        assert cron_matches("*/15 * * * *", dt) is True
        dt2 = datetime(2026, 3, 24, 10, 7, tzinfo=timezone.utc)
        assert cron_matches("*/15 * * * *", dt2) is False

    def test_range_syntax(self) -> None:
        dt = datetime(2026, 3, 24, 10, 30, tzinfo=timezone.utc)
        assert cron_matches("25-35 * * * *", dt) is True
        assert cron_matches("0-5 * * * *", dt) is False

    def test_list_syntax(self) -> None:
        dt = datetime(2026, 3, 24, 10, 30, tzinfo=timezone.utc)
        assert cron_matches("0,15,30,45 * * * *", dt) is True
        assert cron_matches("0,15,45 * * * *", dt) is False

    def test_day_of_week(self) -> None:
        # 2026-03-24 is Tuesday — standard cron: Sun=0, Mon=1, Tue=2
        dt = datetime(2026, 3, 24, 10, 0, tzinfo=timezone.utc)
        assert cron_matches("0 10 * * 2", dt) is True  # Tuesday
        assert cron_matches("0 10 * * 5", dt) is False  # Friday

    def test_invalid_schedule_raises(self) -> None:
        dt = datetime(2026, 3, 24, 10, 0, tzinfo=timezone.utc)
        with pytest.raises(ValueError, match="5 fields"):
            cron_matches("* * *", dt)


# ---------------------------------------------------------------------------
# Trigger dispatcher tests
# ---------------------------------------------------------------------------

class TestTriggerDispatcher:
    """Test the trigger dispatcher."""

    def test_register_and_fire_cron(self) -> None:
        dispatcher = TriggerDispatcher()
        trigger = AddonTriggerSpec(
            type="cron",
            schedule="0 3 * * *",
            handler="indexer.py::full_reindex",
        )
        dispatcher.register_triggers("codebase-index", [trigger])

        # At 3:00 UTC — should fire
        now = datetime(2026, 3, 24, 3, 0, tzinfo=timezone.utc)
        fired = dispatcher.evaluate_cron_triggers(now)
        assert len(fired) == 1
        assert fired[0]["addon_name"] == "codebase-index"
        assert fired[0]["trigger_type"] == "cron"

    def test_cron_does_not_double_fire_same_minute(self) -> None:
        dispatcher = TriggerDispatcher()
        trigger = AddonTriggerSpec(
            type="cron",
            schedule="0 3 * * *",
            handler="indexer.py::full_reindex",
        )
        dispatcher.register_triggers("codebase-index", [trigger])

        now = datetime(2026, 3, 24, 3, 0, 0, tzinfo=timezone.utc)
        fired1 = dispatcher.evaluate_cron_triggers(now)
        assert len(fired1) == 1

        # Same minute, different second — should NOT fire again
        now2 = datetime(2026, 3, 24, 3, 0, 30, tzinfo=timezone.utc)
        fired2 = dispatcher.evaluate_cron_triggers(now2)
        assert len(fired2) == 0

    def test_cron_fires_next_matching_minute(self) -> None:
        dispatcher = TriggerDispatcher()
        trigger = AddonTriggerSpec(
            type="cron",
            schedule="*/30 * * * *",
            handler="indexer.py::full_reindex",
        )
        dispatcher.register_triggers("codebase-index", [trigger])

        # Fire at :00
        now = datetime(2026, 3, 24, 10, 0, tzinfo=timezone.utc)
        fired = dispatcher.evaluate_cron_triggers(now)
        assert len(fired) == 1

        # Fire again at :30
        now2 = datetime(2026, 3, 24, 10, 30, tzinfo=timezone.utc)
        fired2 = dispatcher.evaluate_cron_triggers(now2)
        assert len(fired2) == 1

    def test_fire_manual_trigger(self) -> None:
        dispatcher = TriggerDispatcher()
        trigger = AddonTriggerSpec(
            type="manual",
            handler="indexer.py::incremental_reindex",
        )
        dispatcher.register_triggers("codebase-index", [trigger])

        result = dispatcher.fire_manual("codebase-index", "indexer.py::incremental_reindex")
        assert result is not None
        assert result["trigger_type"] == "manual"

    def test_fire_manual_unknown_returns_none(self) -> None:
        dispatcher = TriggerDispatcher()
        result = dispatcher.fire_manual("nope", "nope.py::nope")
        assert result is None

    def test_non_cron_trigger_not_fired_by_cron_eval(self) -> None:
        dispatcher = TriggerDispatcher()
        trigger = AddonTriggerSpec(
            type="manual",
            handler="indexer.py::incremental_reindex",
        )
        dispatcher.register_triggers("codebase-index", [trigger])

        now = datetime(2026, 3, 24, 3, 0, tzinfo=timezone.utc)
        fired = dispatcher.evaluate_cron_triggers(now)
        assert len(fired) == 0
