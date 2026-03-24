"""Tests for federation protocol (Wave 33 C8)."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from formicos.core.types import ReplicationFilter
from formicos.core.vector_clock import VectorClock
from formicos.surface.federation import FederationManager, PeerConnection
from formicos.surface.projections import ProjectionStore


class MockTransport:
    """In-memory federation transport for tests."""

    def __init__(self) -> None:
        self.sent_events: list[list[dict[str, Any]]] = []
        self.sent_feedback: list[dict[str, Any]] = []
        self._receive_events: list[dict[str, Any]] = []

    async def send_events(
        self, endpoint: str, events: list[dict[str, Any]],
    ) -> None:
        self.sent_events.append(events)

    async def receive_events(
        self, endpoint: str, since: VectorClock,
    ) -> list[dict[str, Any]]:
        return self._receive_events

    async def send_feedback(
        self, endpoint: str, entry_id: str, success: bool,
    ) -> None:
        self.sent_feedback.append({
            "entry_id": entry_id, "success": success,
        })


def _make_federation(
    transport: MockTransport | None = None,
) -> tuple[FederationManager, MockTransport, ProjectionStore]:
    store = ProjectionStore()
    t = transport or MockTransport()
    fm = FederationManager("local-1", store, t)  # type: ignore[arg-type]
    return fm, t, store


class TestPeerManagement:
    def test_add_and_remove_peer(self) -> None:
        fm, _, _ = _make_federation()
        fm.add_peer("peer-1", "http://peer-1:8000")
        assert "peer-1" in fm.peers
        fm.remove_peer("peer-1")
        assert "peer-1" not in fm.peers

    def test_increment_clock(self) -> None:
        fm, _, _ = _make_federation()
        fm.increment_clock()
        assert fm.clock.clock == {"local-1": 1}


class TestPush:
    @pytest.mark.asyncio
    async def test_push_sends_events(self) -> None:
        fm, transport, store = _make_federation()
        fm.add_peer("peer-1", "http://peer-1:8000")
        store.memory_entries["mem-1"] = {
            "id": "mem-1",
            "crdt_state": {"successes": {"local-1": 5}},
            "workspace_id": "ws-1",
            "entry_type": "skill",
            "confidence": 0.8,
            "domains": [],
            "thread_id": "",
        }
        count = await fm.push_to_peer("peer-1")
        assert count == 1
        assert len(transport.sent_events) == 1

    @pytest.mark.asyncio
    async def test_push_updates_sync_clock(self) -> None:
        fm, _, store = _make_federation()
        fm.add_peer("peer-1", "http://peer-1:8000")
        fm.increment_clock()
        store.memory_entries["mem-1"] = {
            "id": "mem-1",
            "crdt_state": {"successes": {}},
            "workspace_id": "ws-1",
            "entry_type": "skill",
            "confidence": 0.8,
            "domains": [],
            "thread_id": "",
        }
        await fm.push_to_peer("peer-1")
        peer = fm.peers["peer-1"]
        assert peer.last_sync_clock.clock == {"local-1": 1}


class TestPull:
    @pytest.mark.asyncio
    async def test_pull_applies_foreign_events(self) -> None:
        transport = MockTransport()
        transport._receive_events = [
            {
                "entry_id": "mem-1",
                "instance_id": "remote-1",
                "crdt_state": {"successes": {"remote-1": 3}},
            },
        ]
        fm, _, store = _make_federation(transport)
        fm.add_peer("remote-1", "http://remote-1:8000")
        store.memory_entries["mem-1"] = {
            "id": "mem-1",
            "crdt_state": {"successes": {"local-1": 5}},
            "workspace_id": "ws-1",
        }
        count = await fm.pull_from_peer("remote-1")
        assert count == 1
        crdt = store.memory_entries["mem-1"]["crdt_state"]
        assert crdt["successes"]["remote-1"] == 3
        assert crdt["successes"]["local-1"] == 5

    @pytest.mark.asyncio
    async def test_pull_skips_own_events(self) -> None:
        """Cycle prevention: skip events from own instance."""
        transport = MockTransport()
        transport._receive_events = [
            {
                "entry_id": "mem-1",
                "instance_id": "local-1",  # own instance
                "crdt_state": {"successes": {"local-1": 99}},
            },
        ]
        fm, _, store = _make_federation(transport)
        fm.add_peer("remote-1", "http://remote-1:8000")
        store.memory_entries["mem-1"] = {
            "id": "mem-1",
            "crdt_state": {"successes": {"local-1": 5}},
            "workspace_id": "ws-1",
        }
        count = await fm.pull_from_peer("remote-1")
        assert count == 0


class TestValidationFeedback:
    @pytest.mark.asyncio
    async def test_success_increases_trust(self) -> None:
        fm, transport, _ = _make_federation()
        fm.add_peer("peer-1", "http://peer-1:8000")
        initial_alpha = fm.peers["peer-1"].trust.alpha
        await fm.send_validation_feedback("peer-1", "mem-1", success=True)
        assert fm.peers["peer-1"].trust.alpha == initial_alpha + 1
        assert len(transport.sent_feedback) == 1

    @pytest.mark.asyncio
    async def test_failure_increases_beta(self) -> None:
        fm, _, _ = _make_federation()
        fm.add_peer("peer-1", "http://peer-1:8000")
        initial_beta = fm.peers["peer-1"].trust.beta
        await fm.send_validation_feedback("peer-1", "mem-1", success=False)
        # Wave 38: asymmetric penalty — failures add 2.0 to beta
        assert fm.peers["peer-1"].trust.beta == initial_beta + 2


class TestReplicationFilter:
    @pytest.mark.asyncio
    async def test_domain_filter(self) -> None:
        fm, transport, store = _make_federation()
        fm.add_peer(
            "peer-1", "http://peer-1:8000",
            replication_filter=ReplicationFilter(domain_allowlist=["python"]),
        )
        store.memory_entries["mem-1"] = {
            "id": "mem-1",
            "crdt_state": {"successes": {}},
            "workspace_id": "ws-1",
            "entry_type": "skill",
            "confidence": 0.8,
            "domains": ["rust"],
            "thread_id": "",
        }
        count = await fm.push_to_peer("peer-1")
        assert count == 0  # filtered out by domain

    @pytest.mark.asyncio
    async def test_exclude_thread_ids(self) -> None:
        fm, _, store = _make_federation()
        fm.add_peer(
            "peer-1", "http://peer-1:8000",
            replication_filter=ReplicationFilter(
                exclude_thread_ids=["secret-thread"],
            ),
        )
        store.memory_entries["mem-1"] = {
            "id": "mem-1",
            "crdt_state": {"successes": {}},
            "workspace_id": "ws-1",
            "entry_type": "skill",
            "confidence": 0.8,
            "domains": [],
            "thread_id": "secret-thread",
        }
        count = await fm.push_to_peer("peer-1")
        assert count == 0  # privacy boundary
