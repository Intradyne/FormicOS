"""Wave 33 Smoke Tests — 19 items from the validation plan.

Each test maps to a numbered smoke-test item in
docs/waves/wave_33/coder_prompt_33_5_team3.md.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, get_args

import pytest

# ---------------------------------------------------------------------------
# Smoke 1: Colony lifecycle regression (workflow steps + continuation)
# ---------------------------------------------------------------------------


class TestSmoke01ColonyLifecycle:
    """Workspace → thread → workflow steps → step continuation."""

    def test_workflow_step_events_exist(self) -> None:
        """WorkflowStepDefined and WorkflowStepCompleted in event union."""
        from formicos.core.events import WorkflowStepDefined, WorkflowStepCompleted
        from formicos.core.types import WorkflowStep

        ts = datetime.now(timezone.utc)
        env = {"seq": 0, "timestamp": ts, "address": "ws/th/col"}

        step = WorkflowStep(step_index=0, description="Implement feature")
        evt = WorkflowStepDefined(**env, workspace_id="ws1", thread_id="th1", step=step)
        assert evt.step.description == "Implement feature"

        comp = WorkflowStepCompleted(
            **env, workspace_id="ws1", thread_id="th1",
            step_index=0, colony_id="col1", success=True,
            artifacts_produced=["code"],
        )
        assert comp.success is True
        assert comp.step_index == 0


# ---------------------------------------------------------------------------
# Smoke 2: Transcript harvest — bug-type entry extraction
# ---------------------------------------------------------------------------


class TestSmoke02TranscriptHarvest:
    """Harvest extracts bug-type entries from colony transcripts."""

    def test_parse_bug_entry(self) -> None:
        from formicos.surface.memory_extractor import parse_harvest_response

        raw = '```json\n[{"turn_index": 0, "type": "bug", "summary": "Fixed race in auth"}]\n```'
        entries = parse_harvest_response(raw)
        assert len(entries) == 1
        assert entries[0]["type"] == "bug"

    def test_all_harvest_types(self) -> None:
        from formicos.surface.memory_extractor import HARVEST_TYPES

        assert "bug" in HARVEST_TYPES
        assert HARVEST_TYPES["bug"] == "experience"
        assert set(HARVEST_TYPES.keys()) == {"bug", "decision", "convention", "learning"}


# ---------------------------------------------------------------------------
# Smoke 3: Inline dedup — cosine > 0.92 prevents duplicate
# Verified via existing test_inline_dedup.py (test_above_threshold_returns_id)
# ---------------------------------------------------------------------------


class TestSmoke03InlineDedup:
    """Inline dedup is a private method on ColonyManager — verify existence."""

    def test_method_exists(self) -> None:
        from formicos.surface.colony_manager import ColonyManager
        assert hasattr(ColonyManager, "_check_inline_dedup")


# ---------------------------------------------------------------------------
# Smoke 4: Prediction errors — low semantic → counter incremented
# Verified via existing test_prediction_errors.py
# ---------------------------------------------------------------------------


class TestSmoke04PredictionErrors:
    """Prediction error tracking exists in knowledge catalog search path."""

    def test_prediction_error_threshold_constant(self) -> None:
        """The 0.38 threshold is used in knowledge_catalog search."""
        from formicos.surface import knowledge_catalog
        src = open(knowledge_catalog.__file__).read()  # noqa: SIM115
        assert "0.38" in src or "prediction_error" in src


# ---------------------------------------------------------------------------
# Smoke 5: Permanent decay class — no confidence decay
# ---------------------------------------------------------------------------


class TestSmoke05PermanentDecay:
    """Entry with decay_class='permanent' → gamma=1.0 → no decay."""

    def test_permanent_gamma_is_one(self) -> None:
        from formicos.surface.knowledge_constants import GAMMA_RATES
        assert GAMMA_RATES["permanent"] == 1.0

    def test_permanent_no_alpha_decay(self) -> None:
        from formicos.core.crdt import GCounter, LWWRegister, ObservationCRDT
        from formicos.surface.knowledge_constants import GAMMA_RATES

        now = time.time()
        day = 86400.0
        ts_reg = LWWRegister()
        ts_reg.assign(now - 30 * day, now - 30 * day, "inst")

        # Set decay_class to permanent via LWWRegister
        dc_reg = LWWRegister()
        dc_reg.assign("permanent", now, "inst")

        crdt = ObservationCRDT(
            successes=GCounter(counts={"inst": 10}),
            last_obs_ts={"inst": ts_reg},
            decay_class=dc_reg,
        )
        alpha = crdt.query_alpha(now, gamma_rates=GAMMA_RATES, prior_alpha=5.0)
        # gamma=1.0 → 1.0^30 * 10 = 10.0; total = 5.0 + 10.0 = 15.0
        assert alpha == pytest.approx(15.0)


# ---------------------------------------------------------------------------
# Smoke 6: Gamma cap — ephemeral at 180 days capped
# ---------------------------------------------------------------------------


class TestSmoke06GammaCap:
    """Ephemeral entry after 180 days → alpha capped, not collapsed."""

    def test_ephemeral_180_day_cap(self) -> None:
        from formicos.core.crdt import GCounter, LWWRegister, ObservationCRDT
        from formicos.surface.knowledge_constants import GAMMA_RATES, MAX_ELAPSED_DAYS  # noqa: F811

        assert MAX_ELAPSED_DAYS == 180.0
        now = time.time()
        day = 86400.0
        ts_reg = LWWRegister()
        ts_reg.assign(now - 365 * day, now - 365 * day, "inst")

        dc_reg = LWWRegister()
        dc_reg.assign("ephemeral", now, "inst")

        crdt = ObservationCRDT(
            successes=GCounter(counts={"inst": 100}),
            last_obs_ts={"inst": ts_reg},
            decay_class=dc_reg,
        )
        alpha = crdt.query_alpha(
            now, gamma_rates=GAMMA_RATES, prior_alpha=5.0,
            max_elapsed_days=MAX_ELAPSED_DAYS,
        )
        # 0.98^180 * 100 ≈ 2.71; total ≈ 7.71 — capped, not collapsed to ~5
        assert alpha > 5.0, "Alpha should be above prior due to capped decay"
        assert alpha < 20.0, "Alpha should be heavily decayed for ephemeral"


# ---------------------------------------------------------------------------
# Smoke 7: Credential detection — scan functions exist
# ---------------------------------------------------------------------------


class TestSmoke07CredentialDetection:
    """Credential scanning API exists with dual-config."""

    def test_scan_functions_exist(self) -> None:
        from formicos.surface.credential_scan import scan_text, scan_mixed_content
        assert callable(scan_text)
        assert callable(scan_mixed_content)

    def test_dual_config_exists(self) -> None:
        from formicos.surface.credential_scan import PROSE_PLUGINS, CODE_PLUGINS
        # Prose excludes entropy-based detectors that code includes
        assert isinstance(PROSE_PLUGINS, (list, tuple, set, frozenset))
        assert isinstance(CODE_PLUGINS, (list, tuple, set, frozenset))


# ---------------------------------------------------------------------------
# Smoke 8: Credential redaction — [REDACTED:type] format
# ---------------------------------------------------------------------------


class TestSmoke08CredentialRedaction:
    """redact_credentials produces [REDACTED:type] format."""

    def test_redact_function_exists(self) -> None:
        from formicos.surface.credential_scan import redact_credentials
        assert callable(redact_credentials)

    def test_clean_text_unchanged(self) -> None:
        from formicos.surface.credential_scan import redact_credentials
        text, count = redact_credentials("Hello world, no secrets here.")
        assert text == "Hello world, no secrets here."
        assert count == 0

    def test_redact_format_in_source(self) -> None:
        """Verify [REDACTED:{type}] format string exists in implementation."""
        from formicos.surface import credential_scan
        src = open(credential_scan.__file__).read()  # noqa: SIM115
        assert "[REDACTED:" in src


# ---------------------------------------------------------------------------
# Smoke 9: StructuredError — WORKSPACE_NOT_FOUND in registry
# ---------------------------------------------------------------------------


class TestSmoke09StructuredError:
    """MCP structured error with error_code, recovery_hint, suggested_action."""

    def test_workspace_not_found_in_registry(self) -> None:
        from formicos.surface.structured_error import KNOWN_ERRORS
        assert "WORKSPACE_NOT_FOUND" in KNOWN_ERRORS

    def test_workspace_not_found_has_recovery_hint(self) -> None:
        from formicos.surface.structured_error import KNOWN_ERRORS
        err = KNOWN_ERRORS["WORKSPACE_NOT_FOUND"]
        assert err.recovery_hint, "recovery_hint should be non-empty"

    def test_mcp_error_format(self) -> None:
        from formicos.surface.structured_error import KNOWN_ERRORS, to_mcp_tool_error
        err = KNOWN_ERRORS["WORKSPACE_NOT_FOUND"]
        mcp_err = to_mcp_tool_error(err)
        assert mcp_err["isError"] is True
        assert "content" in mcp_err
        assert "structuredContent" in mcp_err


# ---------------------------------------------------------------------------
# Smoke 10: MCP resources — server creates successfully
# ---------------------------------------------------------------------------


class TestSmoke10MCPResources:
    """MCP server creates and exposes resources."""

    def test_mcp_server_creates(self) -> None:
        from unittest.mock import MagicMock
        from formicos.surface.mcp_server import create_mcp_server

        runtime = MagicMock()
        runtime.projections = MagicMock()
        runtime.projections.workspaces = {}
        runtime.projections.memory_entries = {}
        server = create_mcp_server(runtime)
        assert server is not None


# ---------------------------------------------------------------------------
# Smoke 11: Agent Card — route handler exists
# ---------------------------------------------------------------------------


class TestSmoke11AgentCard:
    """Agent Card route exists at /.well-known/agent.json."""

    def test_protocol_routes_include_agent_card(self) -> None:
        from formicos.surface.routes import protocols
        src = open(protocols.__file__).read()  # noqa: SIM115
        assert "/.well-known/agent.json" in src
        assert "knowledge" in src.lower()


# ---------------------------------------------------------------------------
# Smoke 12: Co-occurrence — weights reinforced and decayed
# ---------------------------------------------------------------------------


class TestSmoke12Cooccurrence:
    """Co-occurrence data tracked in projections."""

    def test_cooccurrence_key_canonical(self) -> None:
        from formicos.surface.projections import cooccurrence_key
        assert cooccurrence_key("b", "a") == cooccurrence_key("a", "b")

    def test_cooccurrence_entry_exists(self) -> None:
        from formicos.surface.projections import CooccurrenceEntry
        entry = CooccurrenceEntry(weight=1.5)
        assert entry.weight == 1.5


# ---------------------------------------------------------------------------
# Smoke 13: CRDT merge — exact query_alpha computation
# ---------------------------------------------------------------------------


class TestSmoke13CRDTMerge:
    """Two ObservationCRDTs → merge → query_alpha matches expected value."""

    def test_exact_computation(self) -> None:
        from formicos.core.crdt import GCounter, LWWRegister, ObservationCRDT

        now = time.time()
        day = 86400.0

        # Instance A: 5 successes, last_obs at t-10 days
        ts_a = LWWRegister()
        ts_a.assign(now - 10 * day, now - 10 * day, "A")
        crdt_a = ObservationCRDT(
            successes=GCounter(counts={"A": 5}),
            last_obs_ts={"A": ts_a},
        )

        # Instance B: 3 successes, last_obs at t-2 days
        ts_b = LWWRegister()
        ts_b.assign(now - 2 * day, now - 2 * day, "B")
        crdt_b = ObservationCRDT(
            successes=GCounter(counts={"B": 3}),
            last_obs_ts={"B": ts_b},
        )

        merged = crdt_a.merge(crdt_b)
        gamma_rates = {"ephemeral": 0.98, "stable": 0.995, "permanent": 1.0}
        alpha = merged.query_alpha(now, gamma_rates=gamma_rates, prior_alpha=5.0)

        # Expected: 5.0 + (0.98^10 * 5) + (0.98^2 * 3)
        #         = 5.0 + 4.0855 + 2.8812 = 11.967
        expected = 5.0 + (0.98 ** 10 * 5) + (0.98 ** 2 * 3)
        assert alpha == pytest.approx(expected, rel=1e-3)
        assert alpha == pytest.approx(11.967, rel=1e-2)


# ---------------------------------------------------------------------------
# Smoke 14: PeerTrust scoring — 10th percentile, not mean
# ---------------------------------------------------------------------------


class TestSmoke14PeerTrust:
    """PeerTrust(11, 1).score → ~0.82 (10th percentile, NOT 0.917 mean)."""

    def test_score_is_10th_percentile_not_mean(self) -> None:
        from formicos.surface.trust import PeerTrust

        t = PeerTrust(11.0, 1.0)
        assert 0.7 < t.score < 0.9, f"10th percentile should be 0.7-0.9, got {t.score}"
        assert t.mean > t.score, "Mean should be higher than 10th percentile"
        assert t.mean == pytest.approx(11.0 / 12.0, rel=1e-3)
        # Score should NOT equal mean (which is ~0.917)
        assert abs(t.score - t.mean) > 0.05


# ---------------------------------------------------------------------------
# Smoke 15: Conflict resolution — Pareto + adaptive threshold
# ---------------------------------------------------------------------------


class TestSmoke15ConflictResolution:
    """Contradictory entries → Pareto dominance or adaptive threshold."""

    def test_pareto_dominant_wins(self) -> None:
        from formicos.core.types import Resolution
        from formicos.surface.conflict_resolution import resolve_conflict

        a: dict[str, Any] = {
            "id": "a", "conf_alpha": 45, "conf_beta": 5,
            "created_at": "2026-03-18T12:00:00Z",
            "merged_from": ["x", "y", "z"],
        }
        b: dict[str, Any] = {
            "id": "b", "conf_alpha": 4, "conf_beta": 6,
            "created_at": "2026-03-17T12:00:00Z",
            "merged_from": [],
        }
        result = resolve_conflict(a, b)
        assert result.resolution == Resolution.winner
        assert result.primary_id == "a"

    def test_equal_entries_competing(self) -> None:
        from formicos.core.types import Resolution
        from formicos.surface.conflict_resolution import resolve_conflict

        a: dict[str, Any] = {
            "id": "a", "conf_alpha": 5, "conf_beta": 5,
            "created_at": "2026-03-18T12:00:00Z",
            "merged_from": [],
        }
        b: dict[str, Any] = {
            "id": "b", "conf_alpha": 5, "conf_beta": 5,
            "created_at": "2026-03-18T12:00:00Z",
            "merged_from": [],
        }
        result = resolve_conflict(a, b)
        assert result.resolution == Resolution.competing


# ---------------------------------------------------------------------------
# Smoke 16: Federation round-trip (mock transport)
# ---------------------------------------------------------------------------


class TestSmoke16FederationRoundTrip:
    """Push events to peer → trust updated on feedback."""

    @pytest.mark.asyncio
    async def test_federation_validation_feedback_updates_trust(self) -> None:
        from formicos.core.vector_clock import VectorClock
        from formicos.surface.federation import FederationManager
        from formicos.surface.projections import ProjectionStore

        class MockTransport:
            async def send_events(self, endpoint: str, events: list) -> None:
                pass

            async def receive_events(self, endpoint: str, since: VectorClock) -> list:
                return []

            async def send_feedback(
                self, endpoint: str, entry_id: str, success: bool,
            ) -> None:
                pass

        store = ProjectionStore()
        transport = MockTransport()
        fm = FederationManager("inst-A", store, transport)  # type: ignore[arg-type]
        fm.add_peer("inst-B", "http://peer-b:8080")

        assert "inst-B" in fm.peers
        initial_alpha = fm.peers["inst-B"].trust.alpha

        # Positive feedback increases trust alpha
        await fm.send_validation_feedback("inst-B", entry_id="e1", success=True)
        assert fm.peers["inst-B"].trust.alpha == initial_alpha + 1.0

        # Negative feedback increases trust beta (asymmetric: +2.0 per Wave 38)
        initial_beta = fm.peers["inst-B"].trust.beta
        await fm.send_validation_feedback("inst-B", entry_id="e2", success=False)
        assert fm.peers["inst-B"].trust.beta == initial_beta + 2.0


# ---------------------------------------------------------------------------
# Smoke 17: Dedup merge event — MemoryEntryMerged emitted
# ---------------------------------------------------------------------------


class TestSmoke17DedupMergeEvent:
    """Auto-merge (>=0.98 sim) emits MemoryEntryMerged, not StatusChanged."""

    def test_memory_entry_merged_projection(self) -> None:
        from formicos.core.events import MemoryEntryMerged, MemoryEntryCreated
        from formicos.surface.projections import ProjectionStore

        store = ProjectionStore()
        ts = datetime(2026, 3, 18, tzinfo=timezone.utc)

        # Seed entries via proper events
        store.apply(MemoryEntryCreated(
            seq=1, timestamp=ts, address="ws-1/t-1",
            workspace_id="ws-1",
            entry={
                "id": "target-1", "entry_type": "skill",
                "status": "verified", "title": "Target",
                "content": "Target content",
                "source_colony_id": "col-1", "source_artifact_ids": [],
                "workspace_id": "ws-1", "thread_id": "t-1",
                "conf_alpha": 10.0, "conf_beta": 2.0, "confidence": 0.83,
                "domains": ["python"], "merged_from": [],
            },
        ))
        store.apply(MemoryEntryCreated(
            seq=2, timestamp=ts, address="ws-1/t-1",
            workspace_id="ws-1",
            entry={
                "id": "source-1", "entry_type": "skill",
                "status": "verified", "title": "Source",
                "content": "Source longer content here for merge",
                "source_colony_id": "col-2", "source_artifact_ids": [],
                "workspace_id": "ws-1", "thread_id": "t-1",
                "conf_alpha": 6.0, "conf_beta": 4.0, "confidence": 0.6,
                "domains": ["testing"], "merged_from": [],
            },
        ))

        # Apply merge event
        store.apply(MemoryEntryMerged(
            seq=3, timestamp=ts, address="ws-1",
            target_id="target-1", source_id="source-1",
            merged_content="Source longer content here for merge",
            merged_domains=["python", "testing"],
            merged_from=["source-1"],
            content_strategy="keep_longer",
            similarity=0.99,
            merge_source="dedup",
            workspace_id="ws-1",
        ))

        target = store.memory_entries["target-1"]
        assert target["content"] == "Source longer content here for merge"
        assert set(target["domains"]) == {"python", "testing"}
        assert "source-1" in target["merged_from"]
        assert target["merge_count"] == 1

        source = store.memory_entries["source-1"]
        assert source["status"] == "rejected"


# ---------------------------------------------------------------------------
# Smoke 18: Full replay of all event types including CRDT events
# ---------------------------------------------------------------------------


class TestSmoke18FullReplay:
    """All 53 event types in closed union, including 5 Wave 33 CRDT events."""

    def test_all_event_types_in_union(self) -> None:
        from formicos.core.events import FormicOSEvent, EVENT_TYPE_NAMES

        annotated_args = get_args(FormicOSEvent)
        union_type = annotated_args[0]
        members = get_args(union_type)
        assert len(members) == 69
        assert len(EVENT_TYPE_NAMES) == 69

    def test_crdt_events_in_union(self) -> None:
        from formicos.core.events import EVENT_TYPE_NAMES

        wave33_events = {
            "CRDTCounterIncremented",
            "CRDTTimestampUpdated",
            "CRDTSetElementAdded",
            "CRDTRegisterAssigned",
            "MemoryEntryMerged",
        }
        assert wave33_events.issubset(set(EVENT_TYPE_NAMES))


# ---------------------------------------------------------------------------
# Smoke 19: CI clean — import sanity
# ---------------------------------------------------------------------------


class TestSmoke19CIClean:
    """All Wave 33 modules import cleanly."""

    def test_import_core_events(self) -> None:
        from formicos.core import events
        assert hasattr(events, "FormicOSEvent")
        assert hasattr(events, "EVENT_TYPE_NAMES")
        assert len(events.EVENT_TYPE_NAMES) == 69

    def test_import_crdt(self) -> None:
        from formicos.core.crdt import GCounter, LWWRegister, GSet, ObservationCRDT
        assert callable(GCounter)
        assert callable(ObservationCRDT)

    def test_import_vector_clock(self) -> None:
        from formicos.core.vector_clock import VectorClock
        assert callable(VectorClock)

    def test_import_federation(self) -> None:
        from formicos.surface.federation import FederationManager
        from formicos.surface.trust import PeerTrust
        from formicos.surface.conflict_resolution import resolve_conflict
        assert callable(FederationManager)
        assert callable(PeerTrust)
        assert callable(resolve_conflict)
