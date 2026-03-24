"""Tests for VRAM probe functions and slot probe consolidation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from formicos.core.settings import load_config
from formicos.surface.projections import (
    ColonyProjection,
    ProjectionStore,
    ThreadProjection,
    WorkspaceProjection,
)
from formicos.surface.view_state import build_snapshot
from formicos.surface.ws_handler import (
    _parse_prometheus_gauge,
    _probe_vram_health,
)

_CONFIG_PATH = Path(__file__).resolve().parents[3] / "config" / "formicos.yaml"
_SETTINGS = load_config(_CONFIG_PATH)


class TestParsePrometheusGauge:
    """Test Prometheus metric text parsing."""

    def test_parses_integer_gauge(self) -> None:
        text = "llama_gpu_memory_used_bytes 12345678\n"
        assert _parse_prometheus_gauge(text, "llama_gpu_memory_used_bytes") == 12345678.0

    def test_parses_float_gauge(self) -> None:
        text = "llama_gpu_memory_total_bytes 48318382080.0\n"
        assert _parse_prometheus_gauge(text, "llama_gpu_memory_total_bytes") == 48318382080.0

    def test_returns_none_for_missing_metric(self) -> None:
        text = "llama_kv_cache_usage_bytes 100\n"
        assert _parse_prometheus_gauge(text, "llama_gpu_memory_used_bytes") is None

    def test_handles_multiple_metrics(self) -> None:
        text = (
            "# HELP llama_gpu info\n"
            "llama_gpu_memory_used_bytes 20000000000\n"
            "llama_gpu_memory_total_bytes 48000000000\n"
        )
        assert _parse_prometheus_gauge(text, "llama_gpu_memory_used_bytes") == 20000000000.0
        assert _parse_prometheus_gauge(text, "llama_gpu_memory_total_bytes") == 48000000000.0

    def test_handles_empty_text(self) -> None:
        assert _parse_prometheus_gauge("", "llama_gpu_memory_used_bytes") is None


class TestProbeVramHealth:
    """Test VRAM extraction from /health response data."""

    def test_extracts_vram_top_level(self) -> None:
        data: dict[str, Any] = {"vram_used": 20000, "vram_total": 48000, "status": "ok"}
        result = _probe_vram_health(data)
        assert result == {"usedMb": 20000, "totalMb": 48000}

    def test_extracts_vram_nested_gpu_memory(self) -> None:
        data: dict[str, Any] = {
            "status": "ok",
            "gpu_memory": {"used": 15000, "total": 32000},
        }
        result = _probe_vram_health(data)
        assert result == {"usedMb": 15000, "totalMb": 32000}

    def test_returns_none_when_absent(self) -> None:
        data: dict[str, Any] = {"status": "ok", "slots_idle": 2}
        assert _probe_vram_health(data) is None

    def test_returns_none_for_non_numeric(self) -> None:
        data: dict[str, Any] = {"vram_used": "unknown", "vram_total": "unknown"}
        assert _probe_vram_health(data) is None


class TestVramInSnapshot:
    """Verify VRAM flows from probe data into the operator snapshot."""

    def _store_with_colony(self) -> ProjectionStore:
        store = ProjectionStore()
        colony = ColonyProjection(
            id="col-1",
            thread_id="th-1",
            workspace_id="ws-1",
            task="test",
            status="running",
        )
        thread = ThreadProjection(id="th-1", workspace_id="ws-1", name="main")
        thread.colonies["col-1"] = colony
        ws = WorkspaceProjection(id="ws-1", name="default")
        ws.threads["th-1"] = thread
        store.workspaces["ws-1"] = ws
        store.colonies["col-1"] = colony
        return store

    def test_vram_null_when_no_probe(self) -> None:
        store = self._store_with_colony()
        snapshot = build_snapshot(store, _SETTINGS)
        for model in snapshot["localModels"]:
            assert model["vram"] is None

    def test_vram_populated_from_probe(self) -> None:
        store = self._store_with_colony()
        snapshot = build_snapshot(
            store,
            _SETTINGS,
            probed_local={
                "http://localhost:8008": {
                    "status": "ok",
                    "vram": {"usedMb": 18500, "totalMb": 48000},
                },
            },
        )
        local_models = snapshot["localModels"]
        assert len(local_models) >= 1
        assert local_models[0]["vram"] == {"usedMb": 18500, "totalMb": 48000}

    def test_vram_none_when_probe_has_no_vram(self) -> None:
        store = self._store_with_colony()
        snapshot = build_snapshot(
            store,
            _SETTINGS,
            probed_local={
                "http://localhost:8008": {
                    "status": "ok",
                },
            },
        )
        local_models = snapshot["localModels"]
        assert len(local_models) >= 1
        assert local_models[0]["vram"] is None
