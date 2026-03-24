"""Federation protocol: CouchDB-style push/pull replication (Wave 33 C8).

Implements CouchDB-style push/pull replication between FormicOS instances.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import structlog

from formicos.core.types import ReplicationFilter
from formicos.core.vector_clock import VectorClock
from formicos.surface.trust import PeerTrust

if TYPE_CHECKING:
    from formicos.adapters.federation_transport import FederationTransport
    from formicos.surface.projections import ProjectionStore

log = structlog.get_logger()


@dataclass
class PeerConnection:
    instance_id: str
    endpoint: str
    trust: PeerTrust = field(default_factory=PeerTrust)
    replication_filter: ReplicationFilter = field(
        default_factory=ReplicationFilter,
    )
    last_sync_clock: VectorClock = field(default_factory=VectorClock)


class FederationManager:
    """Manages federation peers and CouchDB-style push/pull replication."""

    def __init__(
        self,
        instance_id: str,
        projections: ProjectionStore,
        transport: FederationTransport,
    ) -> None:
        self._instance_id = instance_id
        self._projections = projections
        self._transport = transport
        self._peers: dict[str, PeerConnection] = {}
        self._clock = VectorClock()

    def add_peer(
        self,
        peer_id: str,
        endpoint: str,
        replication_filter: ReplicationFilter | None = None,
    ) -> None:
        """Register a federation peer."""
        self._peers[peer_id] = PeerConnection(
            instance_id=peer_id,
            endpoint=endpoint,
            replication_filter=replication_filter or ReplicationFilter(),
        )

    def remove_peer(self, peer_id: str) -> None:
        self._peers.pop(peer_id, None)

    @property
    def peers(self) -> dict[str, PeerConnection]:
        return dict(self._peers)

    @property
    def clock(self) -> VectorClock:
        return self._clock

    def increment_clock(self) -> None:
        self._clock = self._clock.increment(self._instance_id)

    async def push_to_peer(self, peer_id: str) -> int:
        """Push local CRDT events since peer's last_sync_clock."""
        peer = self._peers.get(peer_id)
        if peer is None:
            return 0
        events = self._get_events_since(peer.last_sync_clock)
        filtered = self._apply_replication_filter(events, peer.replication_filter)
        if not filtered:
            return 0
        await self._transport.send_events(peer.endpoint, filtered)
        peer.last_sync_clock = VectorClock(clock=dict(self._clock.clock))
        return len(filtered)

    async def pull_from_peer(self, peer_id: str) -> int:
        """Pull foreign CRDT events from peer."""
        peer = self._peers.get(peer_id)
        if peer is None:
            return 0
        events = await self._transport.receive_events(
            peer.endpoint, since=peer.last_sync_clock,
        )
        applied = 0
        for event in events:
            if event.get("instance_id") == self._instance_id:
                continue  # Cycle prevention
            self._apply_foreign_event(event)
            applied += 1
        return applied

    async def send_validation_feedback(
        self, peer_id: str, entry_id: str, success: bool,
    ) -> None:
        """Report outcome of using foreign knowledge to the originating peer."""
        peer = self._peers.get(peer_id)
        if peer is None:
            return
        if success:
            peer.trust.record_success()
        else:
            peer.trust.record_failure()
        await self._transport.send_feedback(peer.endpoint, entry_id, success)

    def _get_events_since(self, since: VectorClock) -> list[dict[str, Any]]:
        """Get CRDT events that happened after the given clock.

        In the current implementation, we scan memory_entries for CRDT state
        and produce synthetic event dicts. A full implementation would use
        the event store directly.
        """
        events: list[dict[str, Any]] = []
        for entry_id, entry in self._projections.memory_entries.items():
            crdt_state = entry.get("crdt_state")
            if crdt_state is not None:
                events.append({
                    "entry_id": entry_id,
                    "instance_id": self._instance_id,
                    "crdt_state": crdt_state,
                    "workspace_id": entry.get("workspace_id", ""),
                })
        return events

    def _apply_replication_filter(
        self,
        events: list[dict[str, Any]],
        filt: ReplicationFilter,
    ) -> list[dict[str, Any]]:
        """Filter events according to replication rules."""
        result: list[dict[str, Any]] = []
        for evt in events:
            entry_id = evt.get("entry_id", "")
            entry = self._projections.memory_entries.get(entry_id)
            if entry is None:
                continue
            # Domain allowlist check
            if filt.domain_allowlist:
                entry_domains = set(entry.get("domains", []))
                if not entry_domains & set(filt.domain_allowlist):
                    continue
            # Entry type check
            if filt.entry_types and entry.get("entry_type", "") not in filt.entry_types:
                continue
            # Privacy boundary — exclude thread IDs
            if filt.exclude_thread_ids and entry.get("thread_id", "") in filt.exclude_thread_ids:
                continue
            # Min confidence check
            conf = entry.get("confidence", 0.0)
            if conf < filt.min_confidence:
                continue
            result.append(evt)
        return result

    def _apply_foreign_event(self, event: dict[str, Any]) -> None:
        """Apply a foreign CRDT event to local projection state.

        Wave 38: stamps foreign entries with source_peer and federation_hop
        so trust discounting and admission policy can see the origin.
        """
        entry_id = event.get("entry_id", "")
        if not entry_id:
            return
        entry = self._projections.memory_entries.get(entry_id)
        if entry is None:
            log.debug(
                "federation.foreign_event_no_entry",
                entry_id=entry_id,
            )
            return

        # Wave 38: stamp peer origin for trust/admission visibility
        source_instance = event.get("instance_id", "")
        if source_instance and source_instance != self._instance_id:
            entry.setdefault("source_peer", source_instance)
            entry["federation_hop"] = entry.get("federation_hop", 0) + 1

        foreign_crdt = event.get("crdt_state", {})
        local_crdt = entry.setdefault("crdt_state", {})
        # Merge counters (pairwise max)
        for field_name in ("successes", "failures"):
            foreign_counts = foreign_crdt.get(field_name, {})
            local_counts = local_crdt.setdefault(field_name, {})
            for node, count in foreign_counts.items():
                local_counts[node] = max(local_counts.get(node, 0), count)
        # Merge timestamps (LWW per instance)
        foreign_ts = foreign_crdt.get("last_obs_ts", {})
        local_ts = local_crdt.setdefault("last_obs_ts", {})
        for inst, ts_data in foreign_ts.items():
            if inst not in local_ts or ts_data.get(
                "timestamp", 0,
            ) > local_ts[inst].get("timestamp", 0):
                local_ts[inst] = ts_data


__all__ = ["FederationManager", "PeerConnection"]
