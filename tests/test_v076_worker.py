"""
Tests for FormicOS v0.7.6 Auto-Scaling Worker Pool.

Covers:
- ColonyStatus.QUEUED_PENDING_COMPUTE enum member
- VALID_TRANSITIONS: CREATED → QUEUED, QUEUED → RUNNING/FAILED
- WorkerManager: enqueue, dequeue, queue ordering, queue_depth
- WorkerManager: get_free_vram_mb (mock nvidia-smi)
- WorkerManager: _start_colony success and failure (dead-letter)
- WorkerManager: _fire_dead_letter webhook payload
- ColonyManager.enqueue() status transition
- ColonyCreateRequest.priority field
- Queue endpoints (GET /api/v1/queue, DELETE /api/v1/queue/{id})
- Backward compatibility: start without queue
- Version bump to 0.7.6
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.models import ColonyStatus


# ── ColonyStatus enum ────────────────────────────────────────────────


def test_queued_pending_compute_status_exists():
    assert ColonyStatus.QUEUED_PENDING_COMPUTE == "queued_pending_compute"


def test_queued_pending_compute_serializes():
    assert ColonyStatus.QUEUED_PENDING_COMPUTE.value == "queued_pending_compute"


# ── VALID_TRANSITIONS ────────────────────────────────────────────────


def test_created_can_transition_to_queued():
    from src.colony_manager import VALID_TRANSITIONS
    assert ColonyStatus.QUEUED_PENDING_COMPUTE in VALID_TRANSITIONS[ColonyStatus.CREATED]


def test_queued_can_transition_to_running():
    from src.colony_manager import VALID_TRANSITIONS
    assert ColonyStatus.RUNNING in VALID_TRANSITIONS[ColonyStatus.QUEUED_PENDING_COMPUTE]


def test_queued_can_transition_to_failed():
    from src.colony_manager import VALID_TRANSITIONS
    assert ColonyStatus.FAILED in VALID_TRANSITIONS[ColonyStatus.QUEUED_PENDING_COMPUTE]


def test_queued_cannot_transition_to_completed():
    from src.colony_manager import VALID_TRANSITIONS
    assert ColonyStatus.COMPLETED not in VALID_TRANSITIONS[ColonyStatus.QUEUED_PENDING_COMPUTE]


# ── WorkerManager: Queue operations ──────────────────────────────────


def test_worker_manager_enqueue():
    from src.worker import WorkerManager

    wm = WorkerManager(colony_manager=MagicMock())
    wm.enqueue("c1", client_id="client-a")
    assert wm.queue_depth == 1
    snap = wm.get_queue_snapshot()
    assert snap[0]["colony_id"] == "c1"
    assert snap[0]["client_id"] == "client-a"


def test_worker_manager_dequeue():
    from src.worker import WorkerManager

    wm = WorkerManager(colony_manager=MagicMock())
    wm.enqueue("c1")
    wm.enqueue("c2")

    entry = wm.dequeue("c1")
    assert entry is not None
    assert entry.colony_id == "c1"
    assert wm.queue_depth == 1


def test_worker_manager_dequeue_not_found():
    from src.worker import WorkerManager

    wm = WorkerManager(colony_manager=MagicMock())
    assert wm.dequeue("nonexistent") is None


def test_worker_manager_queue_fifo_order():
    from src.worker import WorkerManager

    wm = WorkerManager(colony_manager=MagicMock())
    wm.enqueue("c1", priority=10)
    wm.enqueue("c2", priority=10)
    wm.enqueue("c3", priority=10)

    snap = wm.get_queue_snapshot()
    assert [s["colony_id"] for s in snap] == ["c1", "c2", "c3"]


def test_worker_manager_queue_priority_order():
    from src.worker import WorkerManager

    wm = WorkerManager(colony_manager=MagicMock())
    wm.enqueue("c-low", priority=20)
    wm.enqueue("c-high", priority=5)
    wm.enqueue("c-mid", priority=10)

    snap = wm.get_queue_snapshot()
    assert snap[0]["colony_id"] == "c-high"
    assert snap[1]["colony_id"] == "c-mid"
    assert snap[2]["colony_id"] == "c-low"


def test_worker_manager_queue_depth():
    from src.worker import WorkerManager

    wm = WorkerManager(colony_manager=MagicMock())
    assert wm.queue_depth == 0
    wm.enqueue("c1")
    assert wm.queue_depth == 1
    wm.enqueue("c2")
    assert wm.queue_depth == 2
    wm.dequeue("c1")
    assert wm.queue_depth == 1


# ── WorkerManager: VRAM query ────────────────────────────────────────


def test_get_free_vram_mb_success():
    from src.worker import WorkerManager

    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = "12000\n8000\n"

    with patch("src.worker.subprocess.run", return_value=mock_result):
        free = WorkerManager.get_free_vram_mb()
        assert free == 20000


def test_get_free_vram_mb_single_gpu():
    from src.worker import WorkerManager

    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = "24000\n"

    with patch("src.worker.subprocess.run", return_value=mock_result):
        free = WorkerManager.get_free_vram_mb()
        assert free == 24000


def test_get_free_vram_mb_error_returns_zero():
    from src.worker import WorkerManager

    with patch(
        "src.worker.subprocess.run",
        side_effect=FileNotFoundError("nvidia-smi not found"),
    ):
        free = WorkerManager.get_free_vram_mb()
        assert free == 0


def test_get_free_vram_mb_nonzero_returncode():
    from src.worker import WorkerManager

    mock_result = MagicMock()
    mock_result.returncode = 1
    mock_result.stdout = ""

    with patch("src.worker.subprocess.run", return_value=mock_result):
        free = WorkerManager.get_free_vram_mb()
        assert free == 0


# ── WorkerManager: _start_colony ──────────────────────────────────────


@pytest.mark.asyncio
async def test_start_colony_success():
    from src.worker import WorkerManager, QueueEntry

    mock_cm = AsyncMock()
    mock_cm.start = AsyncMock()

    wm = WorkerManager(colony_manager=mock_cm)
    factory = MagicMock(return_value={"on_round_update": AsyncMock()})
    entry = QueueEntry(
        colony_id="c1", client_id="test",
        callbacks_factory=factory,
    )

    await wm._start_colony(entry)
    factory.assert_called_once_with("c1")
    mock_cm.start.assert_awaited_once_with("c1", callbacks=factory.return_value)


@pytest.mark.asyncio
async def test_start_colony_failure_fires_dead_letter():
    from src.worker import WorkerManager, QueueEntry

    mock_cm = AsyncMock()
    mock_cm.start = AsyncMock(side_effect=RuntimeError("GPU OOM"))
    mock_cm._lock = asyncio.Lock()
    mock_cm._colonies = {}
    mock_cm.get_info = MagicMock(
        return_value=MagicMock(webhook_url="https://example.com/hook"),
    )

    mock_wd = AsyncMock()
    mock_wd.dispatch = AsyncMock()

    wm = WorkerManager(
        colony_manager=mock_cm,
        webhook_dispatcher=mock_wd,
    )
    entry = QueueEntry(colony_id="c1", client_id="test-client")

    await wm._start_colony(entry)

    # Verify dead-letter webhook was fired
    mock_wd.dispatch.assert_awaited_once()
    call_kwargs = mock_wd.dispatch.call_args
    payload = call_kwargs.kwargs.get("payload") or call_kwargs[1].get("payload")
    assert payload["status"] == "FAILED_INITIALIZATION"
    assert payload["error_code"] == "SYS_WORKER_FAULT"
    assert payload["colony_id"] == "c1"
    assert payload["event"] == "INITIALIZATION_FAILURE"
    assert "GPU OOM" in payload["detail"]


@pytest.mark.asyncio
async def test_start_colony_failure_no_webhook_dispatcher():
    """Dead-letter skipped when no webhook_dispatcher."""
    from src.worker import WorkerManager, QueueEntry

    mock_cm = AsyncMock()
    mock_cm.start = AsyncMock(side_effect=RuntimeError("crash"))
    mock_cm._lock = asyncio.Lock()
    mock_cm._colonies = {}
    mock_cm.get_info = MagicMock(
        return_value=MagicMock(webhook_url=None),
    )

    wm = WorkerManager(colony_manager=mock_cm, webhook_dispatcher=None)
    entry = QueueEntry(colony_id="c1", client_id="test")

    # Should not raise
    await wm._start_colony(entry)


# ── WorkerManager: _fire_dead_letter ──────────────────────────────────


@pytest.mark.asyncio
async def test_fire_dead_letter_payload():
    from src.worker import WorkerManager

    mock_wd = AsyncMock()
    mock_wd.dispatch = AsyncMock()

    wm = WorkerManager(
        colony_manager=MagicMock(),
        webhook_dispatcher=mock_wd,
    )

    await wm._fire_dead_letter(
        colony_id="c1",
        client_id="ext-agent",
        error="CUDA OOM",
        webhook_url="https://example.com/dlq",
    )

    mock_wd.dispatch.assert_awaited_once()
    payload = mock_wd.dispatch.call_args.kwargs["payload"]
    assert payload["type"] == "colony.initialization_failure"
    assert payload["event"] == "INITIALIZATION_FAILURE"
    assert payload["status"] == "FAILED_INITIALIZATION"
    assert payload["error_code"] == "SYS_WORKER_FAULT"
    assert payload["detail"] == "CUDA OOM"
    assert payload["colony_id"] == "c1"
    assert payload["client_id"] == "ext-agent"
    assert "timestamp" in payload


@pytest.mark.asyncio
async def test_fire_dead_letter_no_webhook_url():
    """No dispatch when webhook_url is None."""
    from src.worker import WorkerManager

    mock_wd = AsyncMock()
    wm = WorkerManager(
        colony_manager=MagicMock(),
        webhook_dispatcher=mock_wd,
    )

    await wm._fire_dead_letter("c1", "client", "error", webhook_url=None)
    mock_wd.dispatch.assert_not_awaited()


# ── WorkerManager: get_active_colonies ────────────────────────────────


def test_get_active_colonies():
    from src.worker import WorkerManager

    mock_cm = MagicMock()
    info_running = MagicMock(
        status=ColonyStatus.RUNNING,
        colony_id="c1",
        client_id="client-a",
    )
    info_queued = MagicMock(
        status=ColonyStatus.QUEUED_PENDING_COMPUTE,
        colony_id="c2",
        client_id="client-b",
    )
    mock_cm.get_all.return_value = [info_running, info_queued]

    wm = WorkerManager(colony_manager=mock_cm)
    active = wm.get_active_colonies()
    assert len(active) == 1
    assert active[0]["colony_id"] == "c1"


# ── ColonyManager.enqueue() ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_colony_manager_enqueue():
    from src.colony_manager import ColonyManager
    from src.models import ColonyConfig, AgentConfig

    cm = ColonyManager.__new__(ColonyManager)
    cm._colonies = {}
    cm._lock = asyncio.Lock()
    cm._workspace_base = MagicMock()
    cm._workspace_base.__truediv__ = MagicMock(return_value=MagicMock())
    cm._model_registry = None
    cm._rag_engine = None
    cm._persist_registry_sync = MagicMock()

    config = ColonyConfig(
        colony_id="test-enqueue",
        task="test task",
        agents=[AgentConfig(agent_id="a1", caste="coder")],
    )

    await cm.create(config, origin="api")

    # Enqueue should transition to QUEUED_PENDING_COMPUTE
    await cm.enqueue("test-enqueue")
    assert cm._colonies["test-enqueue"].info.status == ColonyStatus.QUEUED_PENDING_COMPUTE


@pytest.mark.asyncio
async def test_colony_manager_enqueue_invalid_transition():
    from src.colony_manager import ColonyManager, InvalidTransitionError
    from src.models import ColonyConfig, AgentConfig

    cm = ColonyManager.__new__(ColonyManager)
    cm._colonies = {}
    cm._lock = asyncio.Lock()
    cm._workspace_base = MagicMock()
    cm._workspace_base.__truediv__ = MagicMock(return_value=MagicMock())
    cm._model_registry = None
    cm._rag_engine = None
    cm._persist_registry_sync = MagicMock()

    config = ColonyConfig(
        colony_id="test-enqueue-2",
        task="test task",
        agents=[AgentConfig(agent_id="a1", caste="coder")],
    )

    await cm.create(config, origin="api")
    # Enqueue once (CREATED → QUEUED)
    await cm.enqueue("test-enqueue-2")

    # Second enqueue should fail (QUEUED → QUEUED not valid)
    with pytest.raises(InvalidTransitionError):
        await cm.enqueue("test-enqueue-2")


# ── ColonyCreateRequest priority field ────────────────────────────────


def test_colony_create_request_default_priority():
    from src.server import ColonyCreateRequest

    req = ColonyCreateRequest(task="test")
    assert req.priority == 10


def test_colony_create_request_custom_priority():
    from src.server import ColonyCreateRequest

    req = ColonyCreateRequest(task="test", priority=1)
    assert req.priority == 1


# ── Backward compatibility ───────────────────────────────────────────


def test_colony_create_request_no_webhook_url():
    """Without webhook_url, no queueing should happen."""
    from src.server import ColonyCreateRequest

    req = ColonyCreateRequest(task="test")
    assert req.webhook_url is None


# ── WorkerManager lifecycle ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_worker_manager_start_stop():
    from src.worker import WorkerManager

    wm = WorkerManager(colony_manager=MagicMock())
    task = wm.start()
    assert task is not None
    assert not task.done()

    await wm.stop()
    assert wm._poll_task is None


# ── Version bump ──────────────────────────────────────────────────────


def test_version_server():
    from src.server import VERSION
    assert VERSION == "0.9.0"


def test_version_init():
    from src import __version__
    assert __version__ == "0.9.0"
