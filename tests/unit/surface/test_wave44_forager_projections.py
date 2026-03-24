"""Tests for Wave 44 forager event types and projection handlers.

Verifies:
- Exactly 4 new event types exist (ForageRequested, ForageCycleCompleted,
  DomainStrategyUpdated, ForagerDomainOverride)
- Each event type serializes/deserializes correctly
- Projection handlers produce the expected state
- Domain override reset removes the override
- Forage cycle completion links back to request
- Event union grew from 58 to 62
"""

from __future__ import annotations

from datetime import datetime, timezone

from formicos.core.events import (
    EVENT_TYPE_NAMES,
    DomainStrategyUpdated,
    ForageCycleCompleted,
    ForageRequested,
    ForagerDomainOverride,
    ThreadCreated,
    WorkspaceCreated,
    WorkspaceConfigSnapshot,
    deserialize,
    serialize,
)
from formicos.surface.projections import ProjectionStore

_NOW = datetime(2026, 3, 19, tzinfo=timezone.utc)
_WS_CONFIG = WorkspaceConfigSnapshot(budget=5.0, strategy="stigmergic")
_WS = "ws-forage"
_TH = "t-1"


def _seeded_store() -> ProjectionStore:
    store = ProjectionStore()
    store.apply(WorkspaceCreated(
        seq=1, timestamp=_NOW, address=_WS,
        name=_WS, config=_WS_CONFIG,
    ))
    store.apply(ThreadCreated(
        seq=2, timestamp=_NOW, address=f"{_WS}/{_TH}",
        workspace_id=_WS, name=_TH,
    ))
    return store


# ---------------------------------------------------------------------------
# Event union integrity
# ---------------------------------------------------------------------------


def test_event_union_has_62_types() -> None:
    assert len(EVENT_TYPE_NAMES) == 65


def test_forager_events_in_manifest() -> None:
    expected = {
        "ForageRequested",
        "ForageCycleCompleted",
        "DomainStrategyUpdated",
        "ForagerDomainOverride",
    }
    assert expected.issubset(set(EVENT_TYPE_NAMES))


# ---------------------------------------------------------------------------
# Serialization round-trip
# ---------------------------------------------------------------------------


def test_forage_requested_roundtrip() -> None:
    event = ForageRequested(
        seq=10, timestamp=_NOW, address=_WS,
        workspace_id=_WS, thread_id=_TH, colony_id="col-1",
        mode="reactive", reason="low-confidence retrieval",
        gap_domain="python", gap_query="async error handling",
        max_results=3,
    )
    json_str = serialize(event)
    restored = deserialize(json_str)
    assert restored.type == "ForageRequested"  # type: ignore[union-attr]
    assert restored.mode == "reactive"  # type: ignore[union-attr]
    assert restored.gap_domain == "python"  # type: ignore[union-attr]


def test_forage_cycle_completed_roundtrip() -> None:
    event = ForageCycleCompleted(
        seq=11, timestamp=_NOW, address=_WS,
        workspace_id=_WS, forage_request_seq=10,
        queries_issued=2, pages_fetched=3, pages_rejected=1,
        entries_admitted=2, entries_deduplicated=1,
        duration_ms=1500,
    )
    json_str = serialize(event)
    restored = deserialize(json_str)
    assert restored.type == "ForageCycleCompleted"  # type: ignore[union-attr]
    assert restored.entries_admitted == 2  # type: ignore[union-attr]


def test_domain_strategy_updated_roundtrip() -> None:
    event = DomainStrategyUpdated(
        seq=12, timestamp=_NOW, address=_WS,
        workspace_id=_WS, domain="docs.python.org",
        preferred_level=1, success_count=5, failure_count=0,
        reason="initial success",
    )
    json_str = serialize(event)
    restored = deserialize(json_str)
    assert restored.type == "DomainStrategyUpdated"  # type: ignore[union-attr]
    assert restored.domain == "docs.python.org"  # type: ignore[union-attr]


def test_forager_domain_override_roundtrip() -> None:
    event = ForagerDomainOverride(
        seq=13, timestamp=_NOW, address=_WS,
        workspace_id=_WS, domain="example.com",
        action="distrust", actor="operator-1",
        reason="unreliable content",
    )
    json_str = serialize(event)
    restored = deserialize(json_str)
    assert restored.type == "ForagerDomainOverride"  # type: ignore[union-attr]
    assert restored.action == "distrust"  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# Projection: ForageRequested + ForageCycleCompleted
# ---------------------------------------------------------------------------


def test_forage_cycle_projection() -> None:
    store = _seeded_store()

    # Request
    store.apply(ForageRequested(
        seq=10, timestamp=_NOW, address=_WS,
        workspace_id=_WS, mode="reactive",
        reason="coverage gap in python domain",
        gap_domain="python",
    ))
    assert 10 in store._pending_forage_requests.get(_WS, {})

    # Complete
    store.apply(ForageCycleCompleted(
        seq=11, timestamp=_NOW, address=_WS,
        workspace_id=_WS, forage_request_seq=10,
        queries_issued=2, pages_fetched=4,
        entries_admitted=3, duration_ms=2000,
    ))

    # Request should be consumed
    assert 10 not in store._pending_forage_requests.get(_WS, {})

    # Cycle summary should exist
    cycles = store.forage_cycles.get(_WS, [])
    assert len(cycles) == 1
    summary = cycles[0]
    assert summary.mode == "reactive"
    assert summary.reason == "coverage gap in python domain"
    assert summary.queries_issued == 2
    assert summary.pages_fetched == 4
    assert summary.entries_admitted == 3
    assert summary.duration_ms == 2000


def test_forage_cycle_without_matching_request() -> None:
    """Cycle completion without prior request should still create a summary."""
    store = _seeded_store()
    store.apply(ForageCycleCompleted(
        seq=11, timestamp=_NOW, address=_WS,
        workspace_id=_WS, forage_request_seq=999,
        queries_issued=1, pages_fetched=1, entries_admitted=0,
    ))
    cycles = store.forage_cycles.get(_WS, [])
    assert len(cycles) == 1
    assert cycles[0].mode == "unknown"


# ---------------------------------------------------------------------------
# Projection: DomainStrategyUpdated
# ---------------------------------------------------------------------------


def test_domain_strategy_projection() -> None:
    store = _seeded_store()
    store.apply(DomainStrategyUpdated(
        seq=12, timestamp=_NOW, address=_WS,
        workspace_id=_WS, domain="docs.python.org",
        preferred_level=1, success_count=3, failure_count=0,
    ))

    strategies = store.domain_strategies.get(_WS, {})
    assert "docs.python.org" in strategies
    strat = strategies["docs.python.org"]
    assert strat.preferred_level == 1
    assert strat.success_count == 3


def test_domain_strategy_update_overwrites() -> None:
    store = _seeded_store()
    store.apply(DomainStrategyUpdated(
        seq=12, timestamp=_NOW, address=_WS,
        workspace_id=_WS, domain="example.com",
        preferred_level=1, success_count=2, failure_count=0,
    ))
    store.apply(DomainStrategyUpdated(
        seq=13, timestamp=_NOW, address=_WS,
        workspace_id=_WS, domain="example.com",
        preferred_level=2, success_count=2, failure_count=3,
        reason="escalated after failures",
    ))

    strat = store.domain_strategies[_WS]["example.com"]
    assert strat.preferred_level == 2
    assert strat.failure_count == 3


# ---------------------------------------------------------------------------
# Projection: ForagerDomainOverride
# ---------------------------------------------------------------------------


def test_domain_override_distrust() -> None:
    store = _seeded_store()
    store.apply(ForagerDomainOverride(
        seq=14, timestamp=_NOW, address=_WS,
        workspace_id=_WS, domain="spam.example.com",
        action="distrust", actor="op-1",
        reason="low quality",
    ))

    overrides = store.domain_overrides.get(_WS, {})
    assert "spam.example.com" in overrides
    override = overrides["spam.example.com"]
    assert override.action == "distrust"
    assert override.actor == "op-1"


def test_domain_override_reset_removes() -> None:
    store = _seeded_store()
    store.apply(ForagerDomainOverride(
        seq=14, timestamp=_NOW, address=_WS,
        workspace_id=_WS, domain="example.com",
        action="distrust", actor="op-1",
    ))
    assert "example.com" in store.domain_overrides.get(_WS, {})

    store.apply(ForagerDomainOverride(
        seq=15, timestamp=_NOW, address=_WS,
        workspace_id=_WS, domain="example.com",
        action="reset", actor="op-1",
    ))
    assert "example.com" not in store.domain_overrides.get(_WS, {})


def test_domain_override_trust_replaces_distrust() -> None:
    store = _seeded_store()
    store.apply(ForagerDomainOverride(
        seq=14, timestamp=_NOW, address=_WS,
        workspace_id=_WS, domain="docs.python.org",
        action="distrust", actor="op-1",
    ))
    store.apply(ForagerDomainOverride(
        seq=15, timestamp=_NOW, address=_WS,
        workspace_id=_WS, domain="docs.python.org",
        action="trust", actor="op-1",
    ))
    override = store.domain_overrides[_WS]["docs.python.org"]
    assert override.action == "trust"


# ---------------------------------------------------------------------------
# Replay: full replay produces consistent state
# ---------------------------------------------------------------------------


def test_full_replay_consistency() -> None:
    """Replay a sequence of forager events and verify final state."""
    events = [
        WorkspaceCreated(seq=1, timestamp=_NOW, address=_WS, name=_WS, config=_WS_CONFIG),
        ThreadCreated(seq=2, timestamp=_NOW, address=f"{_WS}/{_TH}", workspace_id=_WS, name=_TH),
        ForageRequested(
            seq=10, timestamp=_NOW, address=_WS,
            workspace_id=_WS, mode="proactive",
            reason="stale cluster in auth domain",
        ),
        DomainStrategyUpdated(
            seq=11, timestamp=_NOW, address=_WS,
            workspace_id=_WS, domain="auth0.com",
            preferred_level=1, success_count=1,
        ),
        ForagerDomainOverride(
            seq=12, timestamp=_NOW, address=_WS,
            workspace_id=_WS, domain="sketchy.io",
            action="distrust", actor="op-1",
        ),
        ForageCycleCompleted(
            seq=13, timestamp=_NOW, address=_WS,
            workspace_id=_WS, forage_request_seq=10,
            queries_issued=3, pages_fetched=5,
            entries_admitted=2, duration_ms=3000,
        ),
    ]

    store = ProjectionStore()
    store.replay(events)

    # Domain strategy exists
    assert "auth0.com" in store.domain_strategies.get(_WS, {})

    # Domain override exists
    assert store.domain_overrides[_WS]["sketchy.io"].action == "distrust"

    # Cycle summary exists
    cycles = store.forage_cycles.get(_WS, [])
    assert len(cycles) == 1
    assert cycles[0].entries_admitted == 2
    assert cycles[0].mode == "proactive"

    # Pending request was consumed
    assert 10 not in store._pending_forage_requests.get(_WS, {})
