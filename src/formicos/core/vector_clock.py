# pyright: reportUnknownVariableType=false
"""Vector clocks for causal ordering in federated FormicOS instances (Wave 33).

At 2-10 instances: 160-240 bytes per clock, nanosecond comparison.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class VectorClock:
    clock: dict[str, int] = field(default_factory=dict)

    def increment(self, instance_id: str) -> VectorClock:
        new_clock = dict(self.clock)
        new_clock[instance_id] = new_clock.get(instance_id, 0) + 1
        return VectorClock(clock=new_clock)

    def merge(self, other: VectorClock) -> VectorClock:
        all_keys = set(self.clock) | set(other.clock)
        return VectorClock(clock={
            k: max(self.clock.get(k, 0), other.clock.get(k, 0))
            for k in all_keys
        })

    def happens_before(self, other: VectorClock) -> bool:
        """True if self strictly happens-before other."""
        all_keys = set(self.clock) | set(other.clock)
        at_least_one_less = False
        for k in all_keys:
            s = self.clock.get(k, 0)
            o = other.clock.get(k, 0)
            if s > o:
                return False
            if s < o:
                at_least_one_less = True
        return at_least_one_less

    def is_concurrent(self, other: VectorClock) -> bool:
        """True if neither happens-before the other."""
        return not self.happens_before(other) and not other.happens_before(self)


__all__ = ["VectorClock"]
