"""Wave 64 Track 7: Cron/event/webhook trigger dispatcher for addon services.

Evaluates addon triggers on a schedule and fires service colonies when due.
Cron parsing is a simple built-in matcher (no external dependency).
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from formicos.surface.addon_loader import AddonTriggerSpec

log = structlog.get_logger()

# ---------------------------------------------------------------------------
# Minimal cron matcher (minute hour day-of-month month day-of-week)
# ---------------------------------------------------------------------------

_CRON_FIELD_RE = re.compile(r"^(\*|[0-9]+(?:-[0-9]+)?(?:,[0-9]+(?:-[0-9]+)?)*)(?:/([0-9]+))?$")


def _parse_cron_field(field: str, min_val: int, max_val: int) -> set[int]:
    """Parse a single cron field into a set of matching values."""
    m = _CRON_FIELD_RE.match(field)
    if not m:
        raise ValueError(f"Invalid cron field: {field}")
    base, step_str = m.group(1), m.group(2)
    step = int(step_str) if step_str else 1
    if base == "*":
        values = set(range(min_val, max_val + 1))
    else:
        values: set[int] = set()
        for part in base.split(","):
            if "-" in part:
                lo, hi = part.split("-", 1)
                lo_i, hi_i = int(lo), int(hi)
                if lo_i < min_val or hi_i > max_val:
                    raise ValueError(f"Cron range {lo}-{hi} out of bounds [{min_val}, {max_val}]")
                values.update(range(lo_i, hi_i + 1))
            else:
                val = int(part)
                if val < min_val or val > max_val:
                    raise ValueError(f"Cron value {val} out of bounds [{min_val}, {max_val}]")
                values.add(val)
    if step > 1:
        # Apply step filter: keep only values where (val - min_val) % step == 0
        values = {v for v in values if (v - min_val) % step == 0}
    return values


def cron_matches(schedule: str, now: datetime) -> bool:
    """Check whether a 5-field cron schedule matches the given time.

    Format: ``minute hour day-of-month month day-of-week``
    Supports ``*``, ranges (``1-5``), lists (``1,3,5``), and steps (``*/5``).
    """
    parts = schedule.strip().split()
    if len(parts) != 5:
        raise ValueError(f"Cron schedule must have 5 fields, got {len(parts)}: {schedule!r}")
    minute_set = _parse_cron_field(parts[0], 0, 59)
    hour_set = _parse_cron_field(parts[1], 0, 23)
    dom_set = _parse_cron_field(parts[2], 1, 31)
    month_set = _parse_cron_field(parts[3], 1, 12)
    dow_set = _parse_cron_field(parts[4], 0, 6)
    return (
        now.minute in minute_set
        and now.hour in hour_set
        and now.day in dom_set
        and now.month in month_set
        and (now.weekday() + 1) % 7 in dow_set  # Convert Python Mon=0 to cron Sun=0
    )


# ---------------------------------------------------------------------------
# Trigger dispatcher
# ---------------------------------------------------------------------------

class TriggerDispatcher:
    """Evaluates addon triggers and fires service colonies when due."""

    def __init__(self) -> None:
        self._triggers: list[tuple[str, AddonTriggerSpec]] = []
        self._last_fired: dict[str, datetime] = {}

    def register_triggers(self, addon_name: str, triggers: list[AddonTriggerSpec]) -> None:
        """Register an addon's triggers for evaluation."""
        for trigger in triggers:
            self._triggers.append((addon_name, trigger))
            log.info(
                "trigger_dispatch.registered",
                addon=addon_name,
                trigger_type=trigger.type,
                schedule=trigger.schedule,
            )

    def evaluate_cron_triggers(self, now: datetime | None = None) -> list[dict[str, Any]]:
        """Check all cron triggers and return list of fired trigger descriptors.

        Each descriptor has: addon_name, trigger_type, handler, schedule.
        """
        if now is None:
            now = datetime.now(UTC)
        fired: list[dict[str, Any]] = []
        for addon_name, trigger in self._triggers:
            if trigger.type != "cron" or not trigger.schedule:
                continue
            key = f"{addon_name}:{trigger.handler}"
            # Prevent double-fire within the same minute
            last = self._last_fired.get(key)
            last_trunc = last.replace(second=0, microsecond=0) if last else None
            if last_trunc == now.replace(second=0, microsecond=0):
                continue
            try:
                if cron_matches(trigger.schedule, now):
                    fired.append({
                        "addon_name": addon_name,
                        "trigger_type": "cron",
                        "handler": trigger.handler,
                        "schedule": trigger.schedule,
                    })
                    self._last_fired[key] = now
                    log.info(
                        "trigger_dispatch.cron_fired",
                        addon=addon_name,
                        handler=trigger.handler,
                    )
            except ValueError:
                log.warning(
                    "trigger_dispatch.invalid_schedule",
                    addon=addon_name,
                    schedule=trigger.schedule,
                )
        return fired

    def fire_manual(self, addon_name: str, handler_ref: str) -> dict[str, Any] | None:
        """Fire a manual trigger for the given addon and handler."""
        for a_name, trigger in self._triggers:
            if a_name == addon_name and trigger.handler == handler_ref and trigger.type == "manual":
                return {
                    "addon_name": addon_name,
                    "trigger_type": "manual",
                    "handler": trigger.handler,
                }
        return None


__all__ = ["TriggerDispatcher", "cron_matches"]
