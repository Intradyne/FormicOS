"""Unit tests for colony-scoped subscription in WebSocketManager."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock

import pytest

from formicos.core.events import RoundStarted, WorkspaceCreated
from formicos.surface.projections import ProjectionStore
from formicos.surface.ws_handler import WebSocketManager

NOW = datetime.now(UTC)


def _make_settings() -> Any:
    from formicos.core.settings import (
        EmbeddingConfig,
        GovernanceConfig,
        ModelDefaults,
        ModelsConfig,
        RoutingConfig,
        SystemConfig,
        SystemSettings,
    )

    return SystemSettings(
        system=SystemConfig(host="0.0.0.0", port=8080, data_dir="./data"),
        models=ModelsConfig(
            defaults=ModelDefaults(
                queen="ollama/llama3.2:3b",
                coder="ollama/llama3.2:3b",
                reviewer="ollama/llama3.2:3b",
                researcher="ollama/llama3.2:3b",
                archivist="ollama/llama3.2:3b",
            ),
            registry=[],
        ),
        embedding=EmbeddingConfig(model="test-model", dimensions=384),
        governance=GovernanceConfig(
            max_rounds_per_colony=25,
            stall_detection_window=3,
            convergence_threshold=0.95,
            default_budget_per_colony=1.0,
        ),
        routing=RoutingConfig(
            default_strategy="stigmergic",
            tau_threshold=0.35,
            k_in_cap=5,
            pheromone_decay_rate=0.1,
            pheromone_reinforce_rate=0.3,
        ),
    )


class TestColonySubscription:
    @pytest.mark.asyncio
    async def test_subscribe_returns_queue(self) -> None:
        store = ProjectionStore()
        mgr = WebSocketManager(store, _make_settings())
        queue = await mgr.subscribe_colony("c1")
        assert isinstance(queue, asyncio.Queue)

    @pytest.mark.asyncio
    async def test_unsubscribe_removes_queue(self) -> None:
        store = ProjectionStore()
        mgr = WebSocketManager(store, _make_settings())
        await mgr.subscribe_colony("c1")
        mgr.unsubscribe_colony("c1")
        assert "c1" not in mgr._colony_subscribers  # noqa: SLF001

    @pytest.mark.asyncio
    async def test_fan_out_delivers_to_colony_queue(self) -> None:
        store = ProjectionStore()
        mgr = WebSocketManager(store, _make_settings())
        queue = await mgr.subscribe_colony("c1")

        event = RoundStarted(
            seq=1, timestamp=NOW,
            address="default/main/c1",
            colony_id="c1", round_number=1,
        )
        await mgr.fan_out_event(event)

        assert not queue.empty()
        received = queue.get_nowait()
        assert received is event

    @pytest.mark.asyncio
    async def test_fan_out_ignores_unrelated_colony(self) -> None:
        store = ProjectionStore()
        mgr = WebSocketManager(store, _make_settings())
        queue = await mgr.subscribe_colony("c1")

        event = RoundStarted(
            seq=1, timestamp=NOW,
            address="default/main/c2",
            colony_id="c2", round_number=1,
        )
        await mgr.fan_out_event(event)

        assert queue.empty()

    def test_unsubscribe_nonexistent_is_safe(self) -> None:
        store = ProjectionStore()
        mgr = WebSocketManager(store, _make_settings())
        mgr.unsubscribe_colony("nonexistent")  # should not raise


class TestProtocolStatus:
    def test_protocol_status_shape(self) -> None:
        from formicos.surface.mcp_server import MCP_TOOL_NAMES
        from formicos.surface.view_state import _build_protocol_status

        status = _build_protocol_status()
        # MCP
        assert status["mcp"]["status"] == "active"
        assert status["mcp"]["transport"] == "streamable_http"
        assert status["mcp"]["endpoint"] == "/mcp"
        assert status["mcp"]["tools"] == len(MCP_TOOL_NAMES)
        # AG-UI
        assert status["agui"]["status"] == "active"
        assert status["agui"]["events"] == 9
        assert status["agui"]["endpoint"] == "/ag-ui/runs"
        assert status["agui"]["semantics"] == "summary-at-turn-end"
        # A2A
        assert status["a2a"]["status"] == "active"
        assert status["a2a"]["endpoint"] == "/a2a/tasks"
        assert status["a2a"]["semantics"] == "submit/poll/attach/result"

    @pytest.mark.asyncio
    async def test_send_state_uses_registry_when_present(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from formicos.surface.registry import CapabilityRegistry, ProtocolEntry

        store = ProjectionStore()
        mgr = WebSocketManager(store, _make_settings())
        registry = CapabilityRegistry(
            event_names=("WorkspaceCreated",),
            mcp_tools=(),
            queen_tools=(),
            agui_events=(),
            protocols=(
                ProtocolEntry(
                    name="A2A",
                    status="active",
                    endpoint="/a2a/tasks",
                    semantics="submit/poll/attach/result",
                ),
            ),
            castes=(),
            version="test",
        )
        mgr._registry = registry  # noqa: SLF001

        monkeypatch.setattr(mgr, "_fetch_skill_stats", AsyncMock(return_value=None))
        monkeypatch.setattr(mgr, "_probe_local_endpoints", AsyncMock(return_value={}))

        captured: dict[str, object] = {}

        def _fake_build_snapshot(*args: object, **kwargs: object) -> dict[str, object]:
            captured["registry"] = kwargs.get("registry")
            return {"ok": True}

        monkeypatch.setattr("formicos.surface.view_state.build_snapshot", _fake_build_snapshot)

        class _FakeWS:
            async def send_text(self, text: str) -> None:
                captured["payload"] = text

        await mgr.send_state(_FakeWS())

        assert captured["registry"] is registry
