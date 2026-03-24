"""Unit tests for formicos.surface.ws_handler."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from formicos.core.events import (
    WorkspaceConfigSnapshot,
    WorkspaceCreated,
)
from formicos.surface.projections import ProjectionStore
from formicos.surface.ws_handler import WebSocketManager, ws_endpoint

NOW = datetime.now(UTC)


def _make_settings() -> Any:
    """Build a minimal SystemSettings-like mock for WebSocketManager."""
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


def _make_ws_mock() -> MagicMock:
    """Create a mock WebSocket with async send_text."""
    ws = MagicMock()
    ws.send_text = AsyncMock()
    return ws


def _make_runtime_mock() -> MagicMock:
    """Create a mock Runtime for dispatch tests."""
    runtime = MagicMock()
    runtime.emit_and_broadcast = AsyncMock(return_value=1)
    return runtime


class _FakeWebSocket:
    """Minimal async WebSocket stub for endpoint tests."""

    def __init__(self, messages: list[str]) -> None:
        self._messages = messages
        self.sent: list[dict[str, Any]] = []
        self.accept = AsyncMock()

    async def send_text(self, text: str) -> None:
        self.sent.append(json.loads(text))

    async def iter_text(self):
        for message in self._messages:
            yield message


class TestWebSocketManager:
    """Tests for subscription management and event fan-out."""

    def test_subscribe_adds_client(self) -> None:
        store = ProjectionStore()
        manager = WebSocketManager(store, _make_settings())
        ws = _make_ws_mock()
        manager.subscribe(ws, "ws1")
        assert ws in manager._subscribers["ws1"]

    def test_unsubscribe_removes_client(self) -> None:
        store = ProjectionStore()
        manager = WebSocketManager(store, _make_settings())
        ws = _make_ws_mock()
        manager.subscribe(ws, "ws1")
        manager.unsubscribe(ws, "ws1")
        assert "ws1" not in manager._subscribers

    def test_unsubscribe_all_removes_from_all(self) -> None:
        store = ProjectionStore()
        manager = WebSocketManager(store, _make_settings())
        ws = _make_ws_mock()
        manager.subscribe(ws, "ws1")
        manager.subscribe(ws, "ws2")
        manager.unsubscribe_all(ws)
        assert not manager._subscribers

    @pytest.mark.anyio()
    async def test_fan_out_event_sends_to_subscribers(self) -> None:
        store = ProjectionStore()
        manager = WebSocketManager(store, _make_settings())
        ws = _make_ws_mock()
        manager.subscribe(ws, "ws1")

        event = WorkspaceCreated(
            seq=1, timestamp=NOW, address="ws1",
            name="ws1",
            config=WorkspaceConfigSnapshot(budget=10.0, strategy="stigmergic"),
        )
        await manager.fan_out_event(event)
        ws.send_text.assert_called_once()
        payload = json.loads(ws.send_text.call_args[0][0])
        assert payload["type"] == "event"
        assert payload["event"]["type"] == "WorkspaceCreated"

    @pytest.mark.anyio()
    async def test_fan_out_skips_unrelated_workspace(self) -> None:
        store = ProjectionStore()
        manager = WebSocketManager(store, _make_settings())
        ws = _make_ws_mock()
        manager.subscribe(ws, "ws2")

        event = WorkspaceCreated(
            seq=1, timestamp=NOW, address="ws1",
            name="ws1",
            config=WorkspaceConfigSnapshot(budget=10.0, strategy="stigmergic"),
        )
        await manager.fan_out_event(event)
        ws.send_text.assert_not_called()

    @pytest.mark.anyio()
    async def test_send_state_sends_snapshot(self) -> None:
        store = ProjectionStore()
        manager = WebSocketManager(store, _make_settings())
        ws = _make_ws_mock()

        await manager.send_state(ws)
        ws.send_text.assert_called_once()
        payload = json.loads(ws.send_text.call_args[0][0])
        assert payload["type"] == "state"
        assert "tree" in payload["state"]
        assert "runtimeConfig" in payload["state"]

    @pytest.mark.anyio()
    async def test_send_state_to_workspace_broadcasts_to_all_subscribers(self) -> None:
        store = ProjectionStore()
        manager = WebSocketManager(store, _make_settings())
        ws1 = _make_ws_mock()
        ws2 = _make_ws_mock()

        manager.subscribe(ws1, "ws1")
        manager.subscribe(ws2, "ws1")

        await manager.send_state_to_workspace("ws1")

        ws1.send_text.assert_called_once()
        ws2.send_text.assert_called_once()

    @pytest.mark.anyio()
    async def test_dispatch_command_with_runtime(self, monkeypatch: pytest.MonkeyPatch) -> None:
        store = ProjectionStore()
        runtime = _make_runtime_mock()
        manager = WebSocketManager(store, _make_settings(), runtime=runtime)
        ws = _make_ws_mock()
        manager.subscribe(ws, "ws1")

        async def _fake_handle_command(**_: Any) -> dict[str, Any]:
            return {"status": "ok"}

        monkeypatch.setattr("formicos.surface.ws_handler.handle_command", _fake_handle_command)

        await manager.dispatch_command(
            ws,
            action="spawn_colony",
            workspace_id="ws1",
            payload={
                "threadId": "th1",
                "task": "build",
                "castes": [{"caste": "coder", "tier": "standard", "count": 1}],
            },
        )

        # Should have sent state snapshot
        sent = [json.loads(call.args[0]) for call in ws.send_text.await_args_list]
        assert any(frame["type"] == "state" for frame in sent)

    @pytest.mark.anyio()
    async def test_dispatch_command_without_runtime_sends_state(self) -> None:
        store = ProjectionStore()
        manager = WebSocketManager(store, _make_settings())
        ws = _make_ws_mock()

        await manager.dispatch_command(ws, "spawn_colony", "ws1", {})

        ws.send_text.assert_called_once()
        payload = json.loads(ws.send_text.call_args[0][0])
        assert payload["type"] == "state"


class TestWebSocketEndpoint:
    """Endpoint-level tests for command routing."""

    @pytest.mark.anyio()
    async def test_ws_endpoint_subscribe_sends_state(self) -> None:
        store = ProjectionStore()
        manager = WebSocketManager(store, _make_settings())

        ws = _FakeWebSocket([
            json.dumps({"action": "subscribe", "workspaceId": "ws1", "payload": {}}),
        ])

        await ws_endpoint(ws, manager)

        assert ws.accept.await_count == 1
        # Initial state + subscribe state = 2 state frames
        state_frames = [f for f in ws.sent if f.get("type") == "state"]
        assert len(state_frames) == 2

    @pytest.mark.anyio()
    async def test_ws_endpoint_dispatches_commands(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        store = ProjectionStore()
        runtime = _make_runtime_mock()
        manager = WebSocketManager(store, _make_settings(), runtime=runtime)

        async def _fake_handle_command(**_: Any) -> dict[str, Any]:
            return {"status": "ok"}

        monkeypatch.setattr("formicos.surface.ws_handler.handle_command", _fake_handle_command)

        ws = _FakeWebSocket([
            json.dumps({"action": "subscribe", "workspaceId": "ws1", "payload": {}}),
            json.dumps({
                "action": "send_queen_message",
                "workspaceId": "ws1",
                "payload": {"threadId": "th1", "content": "hi"},
            }),
        ])

        await ws_endpoint(ws, manager)

        assert ws.accept.await_count == 1
        assert all(frame.get("type") != "ack" for frame in ws.sent)
