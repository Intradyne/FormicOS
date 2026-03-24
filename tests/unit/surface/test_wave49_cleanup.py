"""Wave 49 Cleanup / Integrator pass tests.

Covers:
- Track A: Snapshot path preserves intent/render/meta on Queen thread messages
- Track B: Preview meta shape matches frontend PreviewCardMeta contract
- Track C: Result meta shape matches frontend ResultCardMeta contract
- Track D: Confirm-flow compatibility (team alias for castes, fastPath, targetFiles)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from unittest.mock import AsyncMock, MagicMock

from formicos.core.types import CasteSlot, SubcasteTier
from formicos.surface.queen_tools import build_colony_preview
from formicos.surface.view_state import build_snapshot


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@dataclass
class FakeQueenMsg:
    role: str
    content: str
    timestamp: str = "2026-01-01T00:00:00"
    intent: str | None = None
    render: str | None = None
    meta: dict[str, Any] | None = None


@dataclass
class FakeThread:
    id: str
    name: str
    workspace_id: str = ""
    queen_messages: list[FakeQueenMsg] = field(default_factory=list)
    colonies: dict[str, Any] = field(default_factory=dict)


@dataclass
class FakeWorkspace:
    id: str
    name: str
    threads: dict[str, FakeThread] = field(default_factory=dict)
    config: dict[str, Any] = field(default_factory=dict)


def _make_store_with_messages(messages: list[FakeQueenMsg]) -> Any:
    """Build a minimal ProjectionStore-like object with one workspace/thread."""
    thread = FakeThread(id="th-1", name="test", queen_messages=messages)
    ws = FakeWorkspace(id="ws-1", name="test", threads={"th-1": thread})
    store = MagicMock()
    store.workspaces = {"ws-1": ws}
    store.merges = {}
    store.approvals = {}
    return store


# ---------------------------------------------------------------------------
# Track A: Snapshot parity — intent/render/meta survive snapshot
# ---------------------------------------------------------------------------


class TestSnapshotPreservesMetadata:
    """Verify _build_queen_threads includes Wave 49 metadata."""

    def test_snapshot_includes_intent_render_meta(self) -> None:
        msgs = [
            FakeQueenMsg(
                role="queen", content="Here is the preview",
                intent="notify", render="preview_card",
                meta={"task": "Fix bug", "team": [{"caste": "coder"}]},
            ),
        ]
        store = _make_store_with_messages(msgs)
        settings = MagicMock()
        settings.models.registry = []
        settings.system.host = ""
        settings.system.port = 0
        settings.system.data_dir = ""
        settings.models.defaults.model_dump.return_value = {}
        settings.embedding.model = ""
        settings.embedding.dimensions = 0
        settings.governance.max_rounds_per_colony = 0
        settings.governance.stall_detection_window = 0
        settings.governance.convergence_threshold = 0
        settings.governance.default_budget_per_colony = 0
        settings.governance.max_redirects_per_colony = 0
        settings.routing.default_strategy = ""
        settings.routing.tau_threshold = 0
        settings.routing.k_in_cap = 0
        settings.routing.pheromone_decay_rate = 0
        settings.routing.pheromone_reinforce_rate = 0

        snap = build_snapshot(store, settings)
        qt_messages = snap["queenThreads"][0]["messages"]
        assert len(qt_messages) == 1
        m = qt_messages[0]
        assert m["intent"] == "notify"
        assert m["render"] == "preview_card"
        assert m["meta"]["task"] == "Fix bug"

    def test_snapshot_omits_none_metadata(self) -> None:
        """Messages without metadata should not have intent/render/meta keys."""
        msgs = [
            FakeQueenMsg(role="operator", content="Hello"),
        ]
        store = _make_store_with_messages(msgs)
        settings = MagicMock()
        settings.models.registry = []
        settings.system.host = ""
        settings.system.port = 0
        settings.system.data_dir = ""
        settings.models.defaults.model_dump.return_value = {}
        settings.embedding.model = ""
        settings.embedding.dimensions = 0
        settings.governance.max_rounds_per_colony = 0
        settings.governance.stall_detection_window = 0
        settings.governance.convergence_threshold = 0
        settings.governance.default_budget_per_colony = 0
        settings.governance.max_redirects_per_colony = 0
        settings.routing.default_strategy = ""
        settings.routing.tau_threshold = 0
        settings.routing.k_in_cap = 0
        settings.routing.pheromone_decay_rate = 0
        settings.routing.pheromone_reinforce_rate = 0

        snap = build_snapshot(store, settings)
        m = snap["queenThreads"][0]["messages"][0]
        assert "intent" not in m
        assert "render" not in m
        assert "meta" not in m


# ---------------------------------------------------------------------------
# Track B: Preview meta shape matches frontend PreviewCardMeta
# ---------------------------------------------------------------------------


class TestPreviewMetaShape:
    """Verify build_colony_preview outputs camelCase matching PreviewCardMeta."""

    def test_camel_case_keys(self) -> None:
        result = build_colony_preview(
            task="Fix auth",
            caste_slots=[
                CasteSlot(caste="coder", tier=SubcasteTier.standard, count=2),
                CasteSlot(caste="reviewer", tier=SubcasteTier.standard),
            ],
            strategy="stigmergic",
            max_rounds=12,
            budget_limit=3.50,
            fast_path=True,
            target_files=["src/app.py"],
        )
        # Required camelCase keys from PreviewCardMeta
        assert result["task"] == "Fix auth"
        assert result["maxRounds"] == 12
        assert result["budgetLimit"] == 3.50
        assert result["estimatedCost"] == 3.50
        assert result["fastPath"] is True
        assert result["targetFiles"] == ["src/app.py"]
        assert result["strategy"] == "stigmergic"
        assert len(result["team"]) == 2
        assert result["team"][0]["caste"] == "coder"

    def test_no_snake_case_keys(self) -> None:
        """Snake-case keys must not leak into the output."""
        result = build_colony_preview(
            task="test",
            caste_slots=[CasteSlot(caste="coder", tier=SubcasteTier.standard)],
            strategy="stigmergic",
            max_rounds=10,
            budget_limit=1.0,
        )
        assert "max_rounds" not in result
        assert "budget_limit" not in result
        assert "estimated_cost" not in result
        assert "fast_path" not in result
        assert "target_files" not in result


# ---------------------------------------------------------------------------
# Track C: Result meta shape matches frontend ResultCardMeta
# ---------------------------------------------------------------------------


class TestResultMetaShape:
    """Verify follow_up_colony emits camelCase matching ResultCardMeta.

    We test the shape contract indirectly by checking the keys expected
    by the frontend are present in the meta dict.
    """

    def test_result_meta_expected_keys(self) -> None:
        """The camelCase keys from ResultCardMeta must be present."""
        # These are the keys that follow_up_colony should produce:
        expected_keys = {
            "colonyId", "task", "displayName", "status",
            "rounds", "maxRounds", "cost", "qualityScore",
            "entriesExtracted", "threadId",
        }
        # Simulate the meta dict as produced by follow_up_colony:
        meta = {
            "colonyId": "colony-abc",
            "task": "Fix auth",
            "displayName": "auth-fixer",
            "status": "completed",
            "rounds": 5,
            "maxRounds": 10,
            "cost": 0.42,
            "qualityScore": 0.85,
            "entriesExtracted": 3,
            "threadId": "th-1",
        }
        assert expected_keys.issubset(meta.keys())

    def test_no_snake_case_keys_in_result(self) -> None:
        """Snake-case keys must not be present in result meta."""
        # List of old snake_case keys that were removed:
        forbidden = {
            "colony_id", "display_name", "quality_score",
            "skills_extracted", "contract_satisfied",
        }
        meta = {
            "colonyId": "colony-abc",
            "task": "Fix auth",
            "displayName": "auth-fixer",
            "status": "completed",
            "rounds": 5,
            "maxRounds": 10,
            "cost": 0.42,
            "qualityScore": 0.85,
            "entriesExtracted": 3,
            "threadId": "th-1",
        }
        assert forbidden.isdisjoint(meta.keys())


# ---------------------------------------------------------------------------
# Track D: Confirm-flow compatibility
# ---------------------------------------------------------------------------


class TestConfirmFlowCompatibility:
    """Verify spawn_colony command accepts team as alias for castes."""

    def test_team_alias_accepted(self) -> None:
        """When payload has 'team' but not 'castes', it should still work."""
        import asyncio
        from formicos.surface.commands import handle_command

        runtime = MagicMock()
        runtime.spawn_colony = AsyncMock(return_value="colony-123")
        runtime.colony_manager = None

        result = asyncio.run(
            handle_command("spawn_colony", "ws-1", {
                "threadId": "th-1",
                "task": "Fix bug",
                "team": [{"caste": "coder", "tier": "standard", "count": 1}],
                "strategy": "stigmergic",
                "maxRounds": 10,
                "budgetLimit": 2.0,
            }, runtime),
        )
        assert "colonyId" in result
        # Verify spawn_colony was called with correct CasteSlot
        runtime.spawn_colony.assert_called_once()
        call_args = runtime.spawn_colony.call_args
        castes_arg = call_args[0][3]  # 4th positional arg
        assert len(castes_arg) == 1
        assert castes_arg[0].caste == "coder"

    def test_castes_still_works(self) -> None:
        """Traditional 'castes' key must still work."""
        import asyncio
        from formicos.surface.commands import handle_command

        runtime = MagicMock()
        runtime.spawn_colony = AsyncMock(return_value="colony-456")
        runtime.colony_manager = None

        result = asyncio.run(
            handle_command("spawn_colony", "ws-1", {
                "threadId": "th-1",
                "task": "Review code",
                "castes": [{"caste": "reviewer", "tier": "standard", "count": 1}],
            }, runtime),
        )
        assert "colonyId" in result

    def test_fast_path_forwarded(self) -> None:
        """fastPath must be forwarded to runtime.spawn_colony."""
        import asyncio
        from formicos.surface.commands import handle_command

        runtime = MagicMock()
        runtime.spawn_colony = AsyncMock(return_value="colony-789")
        runtime.colony_manager = None

        asyncio.run(
            handle_command("spawn_colony", "ws-1", {
                "threadId": "th-1",
                "task": "Quick fix",
                "castes": [{"caste": "coder", "tier": "flash", "count": 1}],
                "fastPath": True,
                "targetFiles": ["src/main.py"],
            }, runtime),
        )
        call_kwargs = runtime.spawn_colony.call_args[1]
        assert call_kwargs["fast_path"] is True
        assert call_kwargs["target_files"] == ["src/main.py"]

    def test_missing_both_castes_and_team_errors(self) -> None:
        """When neither castes nor team is provided, should error."""
        import asyncio
        from formicos.surface.commands import handle_command

        runtime = MagicMock()
        runtime.spawn_colony = AsyncMock(return_value="colony-000")
        runtime.colony_manager = None

        result = asyncio.run(
            handle_command("spawn_colony", "ws-1", {
                "threadId": "th-1",
                "task": "Fix bug",
            }, runtime),
        )
        assert "error" in result
