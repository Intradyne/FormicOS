"""
FormicOS v0.7.6 -- Worker Manager (Auto-Scaling Worker Pool)

Background poller that dequeues colonies from the compute queue when
sufficient resources (VRAM + concurrency slots) are available.

Integration:
  - Created in server.py lifespan, stored on app.state.worker_manager
  - v1_create_colony enqueues via enqueue()
  - poll_queue() runs as a background asyncio.Task
  - ColonyManager.start() is called when a colony is promoted

Timing constants:
  - POLL_INTERVAL_SECONDS (5.0) — check queue every 5 seconds
  - VRAM_STABILIZATION_SECONDS (2.0) — yield after colony launch for
    nvidia-smi to register the VRAM spike
"""

from __future__ import annotations

import asyncio
import logging
import subprocess
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from src.models import ColonyStatus

logger = logging.getLogger("formicos.worker")

# ── Constants ─────────────────────────────────────────────────────────────

DEFAULT_MAX_CONCURRENT = 5
DEFAULT_VRAM_THRESHOLD_MB = 8000
POLL_INTERVAL_SECONDS = 5.0
VRAM_STABILIZATION_SECONDS = 2.0


# ── Queue Entry ───────────────────────────────────────────────────────────


@dataclass
class QueueEntry:
    """A colony waiting for compute resources."""

    colony_id: str
    client_id: str | None
    priority: int = 10
    enqueued_at: float = field(default_factory=time.time)
    callbacks_factory: Callable[..., dict] | None = None


# ── Worker Manager ────────────────────────────────────────────────────────


class WorkerManager:
    """
    Auto-scaling worker pool that gates colony execution on VRAM and
    concurrency limits.

    The poll loop checks every POLL_INTERVAL_SECONDS whether to promote
    the next queued colony. Promotion requires:
      1. active_count < max_concurrent
      2. free_vram > vram_threshold_mb

    On promotion failure (Orchestrator instantiation crash), the
    dead-letter protocol fires a FAILED_INITIALIZATION webhook.

    Parameters
    ----------
    colony_manager : ColonyManager
        Used to call start() and query active colony counts.
    max_concurrent : int
        Maximum number of concurrently running colonies.
    vram_threshold_mb : int
        Minimum free VRAM (in MB) required to launch a new colony.
    webhook_dispatcher : WebhookDispatcher | None
        For dead-letter webhook dispatch on initialization failure.
    """

    def __init__(
        self,
        colony_manager: Any,
        max_concurrent: int = DEFAULT_MAX_CONCURRENT,
        vram_threshold_mb: int = DEFAULT_VRAM_THRESHOLD_MB,
        webhook_dispatcher: Any | None = None,
    ) -> None:
        self._colony_manager = colony_manager
        self._max_concurrent = max_concurrent
        self._vram_threshold_mb = vram_threshold_mb
        self._webhook_dispatcher = webhook_dispatcher
        self._queue: list[QueueEntry] = []
        self._compute_lock = asyncio.Lock()
        self._poll_task: asyncio.Task | None = None

    # ── Queue API ─────────────────────────────────────────────────────

    def enqueue(
        self,
        colony_id: str,
        client_id: str | None = None,
        priority: int = 10,
        callbacks_factory: Callable[..., dict] | None = None,
    ) -> None:
        """Add a colony to the compute queue."""
        entry = QueueEntry(
            colony_id=colony_id,
            client_id=client_id,
            priority=priority,
            callbacks_factory=callbacks_factory,
        )
        self._queue.append(entry)
        self._queue.sort(key=lambda e: (e.priority, e.enqueued_at))
        logger.info(
            "Colony '%s' enqueued (priority=%d, queue_depth=%d)",
            colony_id, priority, len(self._queue),
        )

    def dequeue(self, colony_id: str) -> QueueEntry | None:
        """Remove a colony from the queue. Returns the entry or None."""
        for i, entry in enumerate(self._queue):
            if entry.colony_id == colony_id:
                return self._queue.pop(i)
        return None

    def get_queue_snapshot(self) -> list[dict[str, Any]]:
        """Return a serializable snapshot of the current queue."""
        return [
            {
                "colony_id": e.colony_id,
                "client_id": e.client_id,
                "priority": e.priority,
                "enqueued_at": e.enqueued_at,
            }
            for e in self._queue
        ]

    def get_active_colonies(self) -> list[dict[str, Any]]:
        """Return a list of currently RUNNING colonies with metadata."""
        active = []
        for info in self._colony_manager.get_all():
            if info.status == ColonyStatus.RUNNING:
                active.append({
                    "colony_id": info.colony_id,
                    "client_id": info.client_id,
                    "vram_est_gb": 12.0,  # TODO: per-model estimate
                })
        return active

    @property
    def queue_depth(self) -> int:
        return len(self._queue)

    # ── VRAM Query ────────────────────────────────────────────────────

    @staticmethod
    def get_free_vram_mb() -> int:
        """
        Query nvidia-smi for total free VRAM across all GPUs.

        Returns 0 on any error (no GPU, driver failure, etc.) which
        effectively blocks queue promotion until the next successful poll.
        """
        try:
            result = subprocess.run(
                [
                    "nvidia-smi",
                    "--query-gpu=memory.free",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0 and result.stdout.strip():
                lines = result.stdout.strip().split("\n")
                return sum(
                    int(float(line.strip()))
                    for line in lines
                    if line.strip()
                )
        except Exception:
            pass
        return 0

    # ── Dead-Letter Webhook ───────────────────────────────────────────

    async def _fire_dead_letter(
        self,
        colony_id: str,
        client_id: str | None,
        error: str,
        webhook_url: str | None,
    ) -> None:
        """Fire FAILED_INITIALIZATION webhook (dead-letter protocol)."""
        if not self._webhook_dispatcher or not webhook_url:
            return
        payload = {
            "type": "colony.initialization_failure",
            "event": "INITIALIZATION_FAILURE",
            "colony_id": colony_id,
            "client_id": client_id,
            "status": "FAILED_INITIALIZATION",
            "error_code": "SYS_WORKER_FAULT",
            "detail": error,
            "timestamp": time.strftime(
                "%Y-%m-%dT%H:%M:%SZ", time.gmtime(),
            ),
        }
        try:
            await self._webhook_dispatcher.dispatch(
                url=webhook_url,
                payload=payload,
                colony_id=colony_id,
            )
        except Exception as exc:
            logger.error(
                "Dead-letter webhook dispatch failed for '%s': %s",
                colony_id, exc,
            )

    # ── Poll Loop ─────────────────────────────────────────────────────

    async def poll_queue(self) -> None:
        """
        Background loop: check queue every POLL_INTERVAL_SECONDS.
        Promote the oldest queued colony if compute resources allow.
        """
        while True:
            try:
                async with self._compute_lock:
                    active_count = len(self.get_active_colonies())
                    free_vram = await asyncio.to_thread(
                        self.get_free_vram_mb,
                    )

                    if (
                        self._queue
                        and active_count < self._max_concurrent
                        and free_vram > self._vram_threshold_mb
                    ):
                        entry = self._queue.pop(0)
                        logger.info(
                            "Promoting colony '%s' from queue "
                            "(active=%d/%d, free_vram=%dMB)",
                            entry.colony_id,
                            active_count,
                            self._max_concurrent,
                            free_vram,
                        )
                        await self._start_colony(entry)
                        # VRAM stabilization pause
                        await asyncio.sleep(VRAM_STABILIZATION_SECONDS)
            except asyncio.CancelledError:
                logger.info("WorkerManager poll loop cancelled")
                return
            except Exception as exc:
                logger.error(
                    "WorkerManager poll error: %s", exc, exc_info=True,
                )

            await asyncio.sleep(POLL_INTERVAL_SECONDS)

    async def _start_colony(self, entry: QueueEntry) -> None:
        """Attempt to start a colony. On failure, fire dead-letter."""
        try:
            callbacks = None
            if entry.callbacks_factory:
                callbacks = entry.callbacks_factory(entry.colony_id)

            await self._colony_manager.start(
                entry.colony_id, callbacks=callbacks,
            )
            logger.info("Colony '%s' started from queue", entry.colony_id)

        except Exception as exc:
            logger.error(
                "Failed to start colony '%s' from queue: %s",
                entry.colony_id, exc, exc_info=True,
            )
            # Mark colony as FAILED
            try:
                cm = self._colony_manager
                async with cm._lock:
                    state = cm._colonies.get(entry.colony_id)
                    if state:
                        cm._set_status(state, ColonyStatus.FAILED)
                        cm._persist_registry_sync()
            except Exception:
                pass

            # Fire dead-letter webhook
            webhook_url = None
            try:
                info = self._colony_manager.get_info(entry.colony_id)
                webhook_url = info.webhook_url
            except Exception:
                pass

            await self._fire_dead_letter(
                entry.colony_id, entry.client_id, str(exc), webhook_url,
            )

    # ── Lifecycle ─────────────────────────────────────────────────────

    def start(self) -> asyncio.Task:
        """Start the background poll loop. Call from lifespan startup."""
        self._poll_task = asyncio.create_task(
            self.poll_queue(), name="worker-manager-poll",
        )
        logger.info(
            "WorkerManager started (max_concurrent=%d, "
            "vram_threshold=%dMB)",
            self._max_concurrent, self._vram_threshold_mb,
        )
        return self._poll_task

    async def stop(self) -> None:
        """Stop the background poll loop. Call from lifespan shutdown."""
        if self._poll_task:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
            self._poll_task = None
        logger.info("WorkerManager stopped")
