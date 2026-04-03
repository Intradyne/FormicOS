"""WebSocket command bridge (ADR-005).

Thin bridge (~50 LOC of core logic) between browser WebSocket commands and
the same MCP operations. Manages subscriptions and event fan-out.
"""

from __future__ import annotations

import asyncio
import json
import re
from typing import TYPE_CHECKING, Any

import httpx
import structlog
from starlette.websockets import WebSocket, WebSocketDisconnect

from formicos.surface.commands import handle_command

if TYPE_CHECKING:
    from formicos.core.events import FormicOSEvent
    from formicos.core.settings import CasteRecipeSet, SystemSettings
    from formicos.surface.projections import ProjectionStore
    from formicos.surface.registry import CapabilityRegistry
    from formicos.surface.runtime import Runtime

log = structlog.get_logger()


def _extract_context_window(props: dict[str, Any]) -> int | None:
    """Best-effort context window extraction from llama.cpp /props output."""
    for key in (
        "context_window",
        "contextWindow",
        "ctx_size",
        "ctxSize",
        "n_ctx",
        "nCtx",
        "max_context_length",
        "maxContextLength",
        "context_length",
        "contextLength",
    ):
        value = props.get(key)
        if isinstance(value, int) and value > 0:
            return value
    nested = props.get("default_generation_settings")
    if isinstance(nested, dict):
        nested_dict: dict[str, Any] = nested  # pyright: ignore[reportUnknownVariableType]
        for key in ("n_ctx", "ctx_size", "context_window"):
            value = nested_dict.get(key)
            if isinstance(value, int) and value > 0:
                return value
    return None


def _parse_prometheus_gauge(text: str, metric_name: str) -> float | None:
    """Extract a Prometheus gauge value by metric name from /metrics text."""
    pattern = rf"^{re.escape(metric_name)}\s+([\d.eE+\-]+)"
    match = re.search(pattern, text, re.MULTILINE)
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            pass
    return None


async def _probe_vram_metrics(
    client: httpx.AsyncClient, endpoint: str,
) -> dict[str, int] | None:
    """Option A: llama.cpp /metrics Prometheus endpoint (cleanest, no Docker needed)."""
    try:
        resp = await client.get(f"{endpoint}/metrics")
        if resp.status_code != 200:
            return None
        text = resp.text
        used = _parse_prometheus_gauge(text, "llama_gpu_memory_used_bytes")
        total = _parse_prometheus_gauge(text, "llama_gpu_memory_total_bytes")
        if used is not None and total is not None:
            return {"usedMb": round(used / 1_048_576), "totalMb": round(total / 1_048_576)}
    except Exception:  # noqa: BLE001
        pass
    return None


def _normalize_vram_value_to_mib(value: float) -> int:
    """Normalize a single VRAM value to MiB.

    Sources are inconsistent: some report bytes, some MiB. Normalize each
    field independently so mixed-unit responses do not produce absurd output.
    """
    if value > 100_000:
        return round(value / 1_048_576)
    return round(value)


def _normalize_vram_to_mib(used: float, total: float) -> dict[str, int]:
    """Normalize VRAM values to MiB."""
    return {
        "usedMb": _normalize_vram_value_to_mib(used),
        "totalMb": _normalize_vram_value_to_mib(total),
    }


def _probe_vram_health(health_data: dict[str, Any]) -> dict[str, int] | None:
    """Option B: check if VRAM is included in the /health response."""
    vram_used = health_data.get("vram_used")
    vram_total = health_data.get("vram_total")
    if isinstance(vram_used, (int, float)) and isinstance(vram_total, (int, float)):
        return _normalize_vram_to_mib(vram_used, vram_total)
    # Also check nested gpu_memory fields (some builds)
    gpu = health_data.get("gpu_memory")
    if isinstance(gpu, dict):
        gpu_dict: dict[str, Any] = gpu  # pyright: ignore[reportUnknownVariableType]
        used = gpu_dict.get("used")
        total = gpu_dict.get("total")
        if isinstance(used, (int, float)) and isinstance(total, (int, float)):
            return _normalize_vram_to_mib(used, total)
    return None


async def _probe_vram_nvidia_smi() -> dict[str, int] | None:
    """Option C: docker exec nvidia-smi (last resort, requires Docker socket)."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "docker", "exec", "formicos-llm",
            "nvidia-smi", "--query-gpu=memory.used,memory.total",
            "--format=csv,noheader,nounits",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5)
        parts = stdout.decode().strip().split(",")
        if len(parts) == 2:
            used = int(parts[0].strip())
            total = int(parts[1].strip())
            if used > 0 and total > 0:
                return {"usedMb": used, "totalMb": total}
    except Exception:  # noqa: BLE001
        pass
    return None


class WebSocketManager:
    """Manages WebSocket client connections, subscriptions, and event fan-out."""

    def __init__(
        self,
        projections: ProjectionStore,
        settings: SystemSettings,
        castes: CasteRecipeSet | None = None,
        runtime: Runtime | None = None,
    ) -> None:
        self._projections = projections
        self._settings = settings
        self._castes = castes
        self._runtime = runtime
        self._registry: CapabilityRegistry | None = None
        self._addon_registrations: list[Any] | None = None
        # workspace_id -> set of connected websockets
        self._subscribers: dict[str, set[WebSocket]] = {}
        # colony_id -> set of queues for colony-scoped subscriptions (AG-UI, A2A attach)
        self._colony_subscribers: dict[str, set[asyncio.Queue[FormicOSEvent]]] = {}

    def subscribe(self, ws: WebSocket, workspace_id: str) -> None:
        """Subscribe a client to events for a workspace."""
        if workspace_id not in self._subscribers:
            self._subscribers[workspace_id] = set()
        self._subscribers[workspace_id].add(ws)
        log.info("ws.subscribed", workspace_id=workspace_id)

    def unsubscribe(self, ws: WebSocket, workspace_id: str) -> None:
        """Unsubscribe a client from a workspace."""
        subs = self._subscribers.get(workspace_id)
        if subs is not None:
            subs.discard(ws)
            if not subs:
                del self._subscribers[workspace_id]
        log.info("ws.unsubscribed", workspace_id=workspace_id)

    def unsubscribe_all(self, ws: WebSocket) -> None:
        """Remove a client from all subscriptions."""
        for workspace_id in list(self._subscribers):
            self.unsubscribe(ws, workspace_id)

    async def subscribe_colony(
        self, colony_id: str,
    ) -> asyncio.Queue[FormicOSEvent]:
        """Subscribe to events for a single colony (AG-UI / A2A attach).

        Returns a dedicated queue for this subscriber. Multiple consumers
        can subscribe to the same colony simultaneously. Caller must call
        ``unsubscribe_colony(colony_id, queue)`` when done.
        """
        queue: asyncio.Queue[FormicOSEvent] = asyncio.Queue(maxsize=1000)
        if colony_id not in self._colony_subscribers:
            self._colony_subscribers[colony_id] = set()
        self._colony_subscribers[colony_id].add(queue)
        return queue

    def unsubscribe_colony(
        self, colony_id: str, queue: asyncio.Queue[FormicOSEvent] | None = None,
    ) -> None:
        """Remove a specific colony-scoped subscription.

        If *queue* is given, only that subscriber is removed. If *queue*
        is ``None``, all subscribers for the colony are removed (legacy compat).
        """
        subs = self._colony_subscribers.get(colony_id)
        if subs is None:
            return
        if queue is not None:
            subs.discard(queue)
            if not subs:
                del self._colony_subscribers[colony_id]
        else:
            del self._colony_subscribers[colony_id]

    async def fan_out_event(self, event: FormicOSEvent) -> None:
        """Send an event to all subscribers whose workspace matches the event address."""
        address: str = event.address  # pyright: ignore[reportAttributeAccessIssue]
        workspace_id = address.split("/")[0] if "/" in address else address
        payload = json.dumps({
            "type": "event",
            "event": json.loads(event.model_dump_json()),  # pyright: ignore[reportAttributeAccessIssue]
        })
        subs = self._subscribers.get(workspace_id, set())
        closed: list[WebSocket] = []
        for ws in subs:
            try:
                await ws.send_text(payload)
            except Exception:  # noqa: BLE001
                closed.append(ws)
        for ws in closed:
            subs.discard(ws)

        # Fan out to colony-scoped subscribers (AG-UI / A2A attach)
        if self._colony_subscribers:
            colony_id = address.rsplit("/", 1)[-1] if "/" in address else address
            # Also check colony_id attribute for terminal events
            evt_colony = getattr(event, "colony_id", None)
            for cid, queues in list(self._colony_subscribers.items()):
                if cid in (colony_id, evt_colony):
                    for queue in list(queues):
                        try:
                            queue.put_nowait(event)
                        except asyncio.QueueFull:
                            log.warning("colony.queue_full", colony_id=cid)

    async def _fetch_skill_stats(self) -> dict[str, object] | None:
        """Skill bank stats — legacy skill bank is read-only (Wave 30)."""
        return {"total": 0, "avgConfidence": 0.0}

    async def _probe_local_endpoints(self) -> dict[str, dict[str, Any]]:
        """Best-effort probe of local LLM server health endpoints.

        Queries each unique local-provider endpoint's ``/health`` and
        ``/props`` paths (llama.cpp convention).  Returns a dict keyed
        by endpoint URL with probe results.  On any failure the endpoint
        is omitted — callers fall back to ``-1`` / unknown sentinel values.
        """
        local_providers = {"llama-cpp", "llama-cpp-swarm", "ollama", "local"}

        seen: dict[str, str] = {}  # endpoint -> first address
        for m in self._settings.models.registry:
            if m.provider not in local_providers:
                continue
            ep = m.endpoint or ""
            if ep and ep not in seen:
                seen[ep] = m.address

        if not seen:
            return {}

        probed: dict[str, dict[str, Any]] = {}
        async with httpx.AsyncClient(timeout=httpx.Timeout(3.0)) as client:
            for ep in seen:
                try:
                    # Single consolidated health+slots call (replaces previous two-call pattern)
                    health = await client.get(
                        f"{ep}/health", params={"include_slots": ""},
                    )
                    data: dict[str, Any] = health.json() if health.status_code == 200 else {}
                    status: str = (
                        data.get("status", "error") if health.status_code == 200 else "error"
                    )
                    result: dict[str, Any] = {
                        "status": status if status == "ok" else "error",
                        "slots_idle": data.get("slots_idle", 0),
                        "slots_processing": data.get("slots_processing", 0),
                    }
                    # Slot details from the same response
                    raw_slots: list[Any] = data.get("slots", [])
                    if raw_slots:
                        result["slot_details"] = [
                            {
                                "id": s.get("id"),  # pyright: ignore[reportUnknownMemberType]
                                "state": s.get("state", 0),  # pyright: ignore[reportUnknownMemberType]
                                "n_ctx": s.get("n_ctx", 0),  # pyright: ignore[reportUnknownMemberType]
                                "prompt_tokens": s.get("prompt_tokens", 0),  # pyright: ignore[reportUnknownMemberType]
                            }
                            for s in raw_slots
                            if isinstance(s, dict)
                        ]
                    # /props for total_slots and context window
                    try:
                        props = await client.get(f"{ep}/props")
                        if props.status_code == 200:
                            pdata: dict[str, Any] = props.json()
                            total_slots = pdata.get("total_slots")
                            if isinstance(total_slots, int) and total_slots > 0:
                                result["total_slots"] = total_slots
                            context_window = _extract_context_window(pdata)
                            if context_window is not None:
                                result["context_window"] = context_window
                    except Exception:  # noqa: BLE001
                        pass  # /props is optional — degrade gracefully

                    # VRAM probe (try methods in order of preference)
                    vram = await _probe_vram_metrics(client, ep)
                    if vram is None:
                        vram = _probe_vram_health(data)
                    if vram is None:
                        vram = await _probe_vram_nvidia_smi()
                    result["vram"] = vram  # None if all methods fail

                    probed[ep] = result
                except Exception:  # noqa: BLE001
                    log.debug("ws.probe_failed", endpoint=ep)
        return probed

    async def send_state(self, ws: WebSocket) -> None:
        """Send the current operator state snapshot to a single client."""
        from formicos.surface.view_state import build_snapshot

        skill_stats = await self._fetch_skill_stats()
        probed = await self._probe_local_endpoints()
        # Provider cooldown health from LLMRouter (ADR-024)
        p_health: dict[str, str] | None = None
        if self._runtime is not None:
            p_health = self._runtime.llm_router.provider_health()
        snapshot = build_snapshot(
            self._projections, self._settings, self._castes,
            skill_bank_stats=skill_stats,  # pyright: ignore[reportArgumentType]
            probed_local=probed,
            provider_health=p_health,
            registry=self._registry,
            addon_registrations=self._addon_registrations,
        )
        await ws.send_text(json.dumps({"type": "state", "state": snapshot}))

    async def send_state_to_workspace(self, workspace_id: str) -> None:
        """Broadcast the current state snapshot to all subscribers of a workspace."""
        subs = list(self._subscribers.get(workspace_id, set()))
        closed: list[WebSocket] = []
        for ws in subs:
            try:
                await self.send_state(ws)
            except Exception:  # noqa: BLE001
                closed.append(ws)
        for ws in closed:
            self.unsubscribe(ws, workspace_id)

    async def dispatch_command(
        self,
        ws: WebSocket,
        action: str,
        workspace_id: str,
        payload: dict[str, Any],
    ) -> None:
        """Execute a WS command through the shared command handlers."""
        if self._runtime is None:
            log.warning("ws.command_missing_runtime", action=action, workspace_id=workspace_id)
            await self.send_state(ws)
            return

        result = await handle_command(
            action=action,
            workspace_id=workspace_id,
            payload=payload,
            runtime=self._runtime,
        )
        if "error" in result:
            log.warning(
                "ws.command_error",
                action=action,
                workspace_id=workspace_id,
                error=result["error"],
            )

        # Runtime.emit_and_broadcast already appended, projected, and fanned out events.
        # Just send the updated state snapshot to this workspace's subscribers.
        subs = self._subscribers.get(workspace_id, set())
        if ws in subs:
            await self.send_state_to_workspace(workspace_id)
        else:
            await self.send_state(ws)


async def ws_endpoint(ws: WebSocket, manager: WebSocketManager) -> None:
    """Starlette WebSocket endpoint handler."""
    await ws.accept()
    # Send initial state snapshot immediately on connect
    await manager.send_state(ws)
    try:
        async for raw in ws.iter_text():
            try:
                msg: dict[str, Any] = json.loads(raw)
            except json.JSONDecodeError:
                from formicos.surface.structured_error import (  # noqa: PLC0415
                    KNOWN_ERRORS,
                    to_ws_error,
                )
                await ws.send_text(json.dumps(to_ws_error(KNOWN_ERRORS["INVALID_JSON"])))
                continue

            action = msg.get("action", "")
            workspace_id = msg.get("workspaceId", "")
            payload: dict[str, Any] = msg.get("payload", {})
            if not isinstance(payload, dict):  # pyright: ignore[reportUnnecessaryIsInstance]
                payload = {}

            if action == "subscribe":
                manager.subscribe(ws, workspace_id)
                await manager.send_state(ws)
            elif action == "unsubscribe":
                manager.unsubscribe(ws, workspace_id)
            else:
                await manager.dispatch_command(ws, action, workspace_id, payload)
    except WebSocketDisconnect:
        pass
    finally:
        manager.unsubscribe_all(ws)


__all__ = ["WebSocketManager", "ws_endpoint"]
