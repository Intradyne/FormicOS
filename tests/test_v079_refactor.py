"""
FormicOS v0.7.9 — Pydantic Hardening & Scaffolding Tests

Tests:
1. DiagnosticsPayload model creation and serialization
2. HardwareState model creation
3. ColonyFleetItem model creation
4. colony_manager.get_diagnostics() returns DiagnosticsPayload (not raw dict)
5. src.core imports work (Orchestrator, AsyncContextTree)
6. src.services imports work (WebhookDispatcher, WorkerManager)
7. Version assertions (VERSION == "0.9.0", __version__ == "0.9.0")
8. Backward-compat: from src.server import ColonyCreateRequest still works
9. Backward-compat: from src.server import create_app still works
"""

import asyncio
from unittest.mock import MagicMock, patch

import pytest


# ── 1. DiagnosticsPayload model creation and serialization ───────────


def test_diagnostics_payload_defaults():
    """DiagnosticsPayload can be created with just colony_id and status."""
    from src.models import DiagnosticsPayload

    payload = DiagnosticsPayload(colony_id="test-1", status="running")
    assert payload.colony_id == "test-1"
    assert payload.status == "running"
    assert payload.round == 0
    assert payload.max_rounds == 0
    assert payload.origin == "ui"
    assert payload.client_id is None
    assert payload.error_traceback is None
    assert payload.last_decisions == []
    assert payload.last_episodes == []
    assert payload.epoch_summaries == []
    assert payload.timeline_spans == []
    assert payload.ws_connections == 0


def test_diagnostics_payload_full():
    """DiagnosticsPayload with all fields populated."""
    from src.models import DiagnosticsPayload, HardwareState

    payload = DiagnosticsPayload(
        colony_id="colony-full",
        status="completed",
        round=5,
        max_rounds=10,
        created_at=1000.0,
        origin="api",
        client_id="client-abc",
        hardware_state=HardwareState(free_vram_mb=4096),
        error_traceback=None,
        last_decisions=[{"round_num": 1, "detail": "test"}],
        last_episodes=[{"round_num": 1, "summary": "did stuff"}],
        epoch_summaries=[{"epoch_id": 0, "summary": "epoch 0"}],
        timeline_spans=[{"span_id": "s1", "duration_ms": 100}],
        ws_connections=3,
    )
    assert payload.round == 5
    assert payload.hardware_state.free_vram_mb == 4096
    assert len(payload.last_decisions) == 1
    assert payload.ws_connections == 3


def test_diagnostics_payload_serialization():
    """DiagnosticsPayload serializes to dict via model_dump()."""
    from src.models import DiagnosticsPayload

    payload = DiagnosticsPayload(colony_id="ser-test", status="running")
    dumped = payload.model_dump()
    assert isinstance(dumped, dict)
    assert dumped["colony_id"] == "ser-test"
    assert dumped["status"] == "running"
    assert "hardware_state" in dumped
    assert dumped["hardware_state"]["free_vram_mb"] == 0


def test_diagnostics_payload_json_round_trip():
    """DiagnosticsPayload survives JSON serialization round-trip."""
    from src.models import DiagnosticsPayload

    original = DiagnosticsPayload(colony_id="json-rt", status="failed", round=3)
    json_str = original.model_dump_json()
    restored = DiagnosticsPayload.model_validate_json(json_str)
    assert restored.colony_id == original.colony_id
    assert restored.round == 3


# ── 2. HardwareState model creation ─────────────────────────────────


def test_hardware_state_defaults():
    """HardwareState defaults free_vram_mb to 0."""
    from src.models import HardwareState

    hw = HardwareState()
    assert hw.free_vram_mb == 0


def test_hardware_state_custom():
    """HardwareState accepts custom free_vram_mb."""
    from src.models import HardwareState

    hw = HardwareState(free_vram_mb=16384)
    assert hw.free_vram_mb == 16384


# ── 3. ColonyFleetItem model creation ───────────────────────────────


def test_colony_fleet_item_defaults():
    """ColonyFleetItem with minimal required fields."""
    from src.models import ColonyFleetItem

    item = ColonyFleetItem(colony_id="fleet-1", task="do stuff", status="running")
    assert item.colony_id == "fleet-1"
    assert item.task == "do stuff"
    assert item.status == "running"
    assert item.round == 0
    assert item.max_rounds == 10
    assert item.origin == "ui"
    assert item.client_id is None
    assert item.created_at == 0.0
    assert item.updated_at == 0.0


def test_colony_fleet_item_full():
    """ColonyFleetItem with all fields populated."""
    from src.models import ColonyFleetItem

    item = ColonyFleetItem(
        colony_id="fleet-full",
        task="big task",
        status="completed",
        round=10,
        max_rounds=10,
        origin="api",
        client_id="client-xyz",
        created_at=1000.0,
        updated_at=2000.0,
    )
    assert item.round == 10
    assert item.client_id == "client-xyz"
    assert item.updated_at == 2000.0


def test_colony_fleet_item_serialization():
    """ColonyFleetItem serializes cleanly."""
    from src.models import ColonyFleetItem

    item = ColonyFleetItem(colony_id="ser-fleet", task="test", status="created")
    dumped = item.model_dump()
    assert isinstance(dumped, dict)
    assert dumped["colony_id"] == "ser-fleet"


# ── 4. colony_manager.get_diagnostics() returns DiagnosticsPayload ───


@pytest.mark.asyncio
async def test_get_diagnostics_returns_pydantic_model():
    """get_diagnostics() returns DiagnosticsPayload, not raw dict."""
    from src.colony_manager import ColonyManager, ColonyInfo
    from src.models import DiagnosticsPayload, ColonyStatus

    # Build a minimal ColonyManager without full init
    cm = ColonyManager.__new__(ColonyManager)
    cm._colonies = {}
    cm._lock = asyncio.Lock()

    # Create a mock colony state
    mock_ctx = MagicMock()
    mock_ctx.get = MagicMock(return_value=None)
    mock_ctx._decisions = []
    mock_ctx._episodes = []
    mock_ctx.get_epoch_summaries = MagicMock(return_value=[])

    info = ColonyInfo(colony_id="diag-test", task="diagnostics test")
    info.status = ColonyStatus.RUNNING
    info.round = 2
    info.max_rounds = 10

    state = MagicMock()
    state.info = info
    state.context_tree = mock_ctx
    cm._colonies["diag-test"] = state

    # The method does `from src.worker import WorkerManager` locally,
    # so we patch at the source module where the class is defined.
    with patch("src.worker.WorkerManager") as MockWM:
        MockWM.get_free_vram_mb = MagicMock(return_value=8192)
        result = await cm.get_diagnostics("diag-test")

    assert isinstance(result, DiagnosticsPayload)
    assert result.colony_id == "diag-test"
    assert result.status == "running"
    assert result.round == 2
    assert result.max_rounds == 10


# ── 5. src.core imports work ────────────────────────────────────────


def test_core_imports_orchestrator():
    """src.core re-exports Orchestrator."""
    from src.core import Orchestrator
    assert Orchestrator is not None


def test_core_imports_context_tree():
    """src.core re-exports AsyncContextTree."""
    from src.core import AsyncContextTree
    assert AsyncContextTree is not None


def test_core_imports_workspace_manager():
    """src.core re-exports SharedWorkspaceManager."""
    from src.core import SharedWorkspaceManager
    assert SharedWorkspaceManager is not None


def test_core_imports_rag():
    """src.core re-exports RAGEngine."""
    from src.core import RAGEngine
    assert RAGEngine is not None


def test_core_all_attribute():
    """src.core.__all__ lists expected exports."""
    import src.core
    expected = {
        "Orchestrator", "AsyncContextTree", "SharedWorkspaceManager", "RAGEngine",
        "EgressProxyError", "ProxyRouter", "KeyVault",
        "REPLHarness", "REPLHarnessError", "SubcallRouter",
        "CFOToolkit",
    }
    assert set(src.core.__all__) == expected


# ── 6. src.services imports work ────────────────────────────────────


def test_services_imports_webhook():
    """src.services re-exports WebhookDispatcher."""
    from src.services import WebhookDispatcher
    assert WebhookDispatcher is not None


def test_services_imports_worker():
    """src.services re-exports WorkerManager."""
    from src.services import WorkerManager
    assert WorkerManager is not None


def test_services_all_attribute():
    """src.services.__all__ lists expected exports."""
    import src.services
    expected = {"WebhookDispatcher", "WorkerManager", "AsyncDocumentIngestor"}
    assert set(src.services.__all__) == expected


# ── 7. Version assertions ──────────────────────────────────────────


def test_version_server():
    """server.py VERSION is 0.7.9."""
    from src.server import VERSION
    assert VERSION == "0.9.0"


def test_version_init():
    """src.__version__ is 0.7.9."""
    from src import __version__
    assert __version__ == "0.9.0"


def test_version_consistency():
    """server.py VERSION and src.__version__ match."""
    from src.server import VERSION
    from src import __version__
    assert VERSION == __version__


# ── 8. Backward-compat: ColonyCreateRequest importable from server ──


def test_colony_create_request_from_server():
    """ColonyCreateRequest is importable from src.server."""
    from src.server import ColonyCreateRequest
    assert ColonyCreateRequest is not None
    # Verify it's a Pydantic model
    assert hasattr(ColonyCreateRequest, "model_fields")


def test_colony_create_request_from_models():
    """ColonyCreateRequest is importable from src.models (canonical location)."""
    from src.models import ColonyCreateRequest
    assert ColonyCreateRequest is not None


def test_colony_create_request_same_class():
    """Both import paths resolve to the same class."""
    from src.server import ColonyCreateRequest as FromServer
    from src.models import ColonyCreateRequest as FromModels
    assert FromServer is FromModels


# ── 9. Backward-compat: create_app importable from server ──────────


def test_create_app_importable():
    """create_app is importable from src.server."""
    from src.server import create_app
    assert callable(create_app)


def test_create_app_returns_fastapi(sample_config_path):
    """create_app() returns a FastAPI instance."""
    from src.models import load_config
    from src.server import create_app
    import os

    os.environ["FORMICOS_CONFIG"] = str(sample_config_path)
    try:
        config = load_config(str(sample_config_path))
        app = create_app(config)
        # FastAPI is a Starlette subclass
        assert hasattr(app, "routes")
        assert hasattr(app, "openapi")
    finally:
        os.environ.pop("FORMICOS_CONFIG", None)
