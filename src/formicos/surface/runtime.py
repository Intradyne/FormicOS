"""Shared application service layer — the ONE mutation path (ADR-001, ADR-005).

All state mutations flow through ``emit_and_broadcast``. Both MCP tools and
WS command handlers delegate here instead of duplicating event emission logic.
Also provides LLM routing, model cascade resolution, and agent building.
"""

from __future__ import annotations

import json
import re
import time as _time_mod
from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import structlog

from formicos.core.events import (
    ApprovalDenied,
    ApprovalGranted,
    ColonyKilled,
    ColonySpawned,
    FormicOSEvent,
    KnowledgeEdgeCreated,
    KnowledgeEntityCreated,
    KnowledgeEntityMerged,
    MergeCreated,
    MergePruned,
    ModelAssignmentChanged,
    QueenMessage,
    ThreadCreated,
    ThreadRenamed,
    WorkspaceConfigChanged,
    WorkspaceConfigSnapshot,
    WorkspaceCreated,
)
from formicos.core.types import (
    AgentConfig,
    CasteSlot,
    InputSource,
    LLMChunk,
    LLMMessage,
    LLMResponse,
    LLMToolSpec,
    ModelRecord,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from formicos.core.ports import EventStorePort, LLMPort, VectorPort
    from formicos.core.settings import CasteRecipeSet, SystemSettings
    from formicos.surface.projections import ProjectionStore
    from formicos.surface.ws_handler import WebSocketManager

log = structlog.get_logger()


def _log_forage_task(task: Any) -> None:
    """Error callback for background forage tasks."""
    if not task.cancelled() and task.exception() is not None:
        log.error(
            "forager.background_task_failed",
            error=str(task.exception()),
        )


_THREAD_STOP_WORDS = {
    "a", "an", "and", "are", "build", "can", "create", "for", "from", "help", "i",
    "in", "make", "me", "of", "please", "the", "to", "with", "write", "you",
}


def _now() -> datetime:
    return datetime.now(UTC)


def _derive_thread_display_name(content: str) -> str | None:
    """Derive a concise display name from an operator's first message."""
    words = re.findall(r"[A-Za-z0-9]+", content.lower())
    filtered = [w for w in words if w not in _THREAD_STOP_WORDS]
    chosen = filtered[:4] or words[:4]
    if not chosen:
        return None
    return " ".join(word.capitalize() for word in chosen)


# ---------------------------------------------------------------------------
# Provider cooldown cache (ADR-024)
# ---------------------------------------------------------------------------


class _ProviderCooldown:
    """Sliding-window failure tracker for LLM providers.

    Tracks recent failures per provider. After ``threshold`` failures within
    ``window_s`` seconds, the provider is cooled down for ``cooldown_s`` seconds.
    In-memory only — not persisted.

    Wave 50: ``max_retries_per_request`` caps total retries across all
    providers for a single LLM call. ``notify_callback`` is called when a
    provider enters cooldown (fire-and-forget).
    """

    def __init__(
        self,
        threshold: int = 3,
        window_s: float = 60.0,
        cooldown_s: float = 120.0,
        max_retries_per_request: int = 3,
        notify_callback: Callable[[str], Any] | None = None,
    ) -> None:
        self._threshold = threshold
        self._window_s = window_s
        self._cooldown_s = cooldown_s
        self._max_retries_per_request = max_retries_per_request
        self._notify_callback = notify_callback
        # provider → list of failure timestamps
        self._failures: dict[str, list[float]] = {}
        # provider → cooldown-until timestamp
        self._cooled_until: dict[str, float] = {}

    @property
    def max_retries_per_request(self) -> int:
        return self._max_retries_per_request

    def record_failure(self, provider: str) -> None:
        """Record a provider failure. Starts cooldown if threshold is reached."""
        now = _time_mod.monotonic()
        failures = self._failures.setdefault(provider, [])
        failures.append(now)
        # Prune old failures outside the window
        cutoff = now - self._window_s
        self._failures[provider] = [t for t in failures if t > cutoff]
        if len(self._failures[provider]) >= self._threshold:
            self._cooled_until[provider] = now + self._cooldown_s
            log.warning(
                "provider_cooldown.activated",
                provider=provider,
                cooldown_s=self._cooldown_s,
            )
            # Wave 50: notify on cooldown activation
            if self._notify_callback is not None:
                import contextlib  # noqa: PLC0415

                with contextlib.suppress(Exception):
                    self._notify_callback(provider)

    def is_cooled_down(self, provider: str) -> bool:
        """Check if a provider is currently in cooldown."""
        until = self._cooled_until.get(provider)
        if until is None:
            return False
        if _time_mod.monotonic() >= until:
            # Cooldown expired
            del self._cooled_until[provider]
            self._failures.pop(provider, None)
            return False
        return True


# ---------------------------------------------------------------------------
# LLM Router
# ---------------------------------------------------------------------------


class LLMRouter:
    """Routes model addresses to provider-specific adapters."""

    # Default fallback chain (ADR-014): gemini → local → anthropic
    _DEFAULT_FALLBACK: list[str] = [
        "gemini/gemini-2.5-flash",
        "llama-cpp/gpt-4",
        "anthropic/claude-sonnet-4.6",
    ]

    def __init__(
        self,
        adapters: dict[str, LLMPort],
        routing_table: dict[str, Any] | None = None,
        registry: list[ModelRecord] | None = None,
        fallback_chain: list[str] | None = None,
    ) -> None:
        self._adapters = adapters
        self._routing_table = routing_table or {}
        self._fallback_chain = fallback_chain or self._DEFAULT_FALLBACK
        # Precompute cheapest model from registry (ADR-012 §1.3)
        self._cheapest: str | None = self._find_cheapest(registry or [], adapters)
        # Model policy lookup for fallback clamping
        self._registry_map: dict[str, ModelRecord] = {
            r.address: r for r in (registry or [])
        }
        # Provider cooldown cache (ADR-024)
        self._cooldown = _ProviderCooldown()

    @staticmethod
    def _find_cheapest(
        registry: list[ModelRecord],
        adapters: dict[str, LLMPort] | None = None,
    ) -> str | None:
        """Return address of the model with the lowest input cost that has an adapter."""
        best: str | None = None
        best_cost = float("inf")
        for rec in registry:
            if adapters is not None:
                # Wave 64: adapter keys are now provider:endpoint
                prefix = rec.address.split("/", 1)[0]
                adapter_key = (
                    f"{prefix}:{rec.endpoint or 'default'}"
                    if hasattr(rec, "endpoint")
                    else f"{prefix}:default"
                )
                if (
                    adapter_key not in adapters
                    and prefix not in adapters
                    and not any(
                        k.startswith(f"{prefix}:") for k in adapters
                    )
                ):
                    continue
            cost = rec.cost_per_input_token if rec.cost_per_input_token is not None else 0.0
            if cost < best_cost:
                best_cost = cost
                best = rec.address
        return best

    def route(
        self,
        caste: str,
        phase: str,
        round_num: int,
        budget_remaining: float,
        default_model: str,
    ) -> str:
        """Select model via budget gate → routing table → adapter check → cascade.

        Pure lookup, no async, no LLM calls. ADR-012 decision order.
        """
        reason = "cascade_default"
        selected = default_model

        # Step 1: Budget gate
        if budget_remaining < 0.10:
            selected = self._cheapest or default_model
            reason = "budget_gate"
        else:
            # Step 2: Routing table lookup
            phase_entry = self._routing_table.get(phase)
            if phase_entry is not None:
                caste_model = getattr(phase_entry, caste, None)
                if caste_model is not None:
                    selected = caste_model
                    reason = "routing_table"

        # Step 3: Adapter check (only if we changed from default)
        if selected != default_model:
            prefix = selected.split("/", 1)[0]
            if prefix not in self._adapters:
                log.debug(
                    "compute_router.unavailable_provider",
                    selected=selected, prefix=prefix,
                    fallback=default_model,
                )
                selected = default_model
                reason = "adapter_fallback"
            elif self._cooldown.is_cooled_down(prefix):
                log.debug(
                    "compute_router.provider_cooled",
                    selected=selected,
                    prefix=prefix,
                    fallback=default_model,
                )
                selected = default_model
                reason = "cooldown_fallback"

        log.info(
            "compute_router.route",
            caste=caste, phase=phase, round_num=round_num,
            selected=selected, reason=reason,
            budget_remaining=round(budget_remaining, 4),
        )
        return selected

    async def complete(
        self,
        model: str,
        messages: Sequence[LLMMessage],
        tools: Sequence[LLMToolSpec] | None = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
        tool_choice: object | None = None,  # Wave 54: reactive escalation
    ) -> LLMResponse:
        prefix = model.split("/", 1)[0]

        # ADR-024: Skip cooled-down providers, use fallback immediately
        if self._cooldown.is_cooled_down(prefix):
            log.info("llm_router.provider_cooled", provider=prefix, model=model)
            return await self._complete_with_fallback(
                model, messages, tools, temperature, max_tokens,
                tool_choice=tool_choice,
            )

        try:
            adapter = self._resolve(model)
            result = await adapter.complete(
                model, messages, tools=tools,
                temperature=temperature, max_tokens=max_tokens,
                tool_choice=tool_choice,
            )
        except Exception as exc:
            # Record failure for cooldown tracking (ADR-024)
            self._cooldown.record_failure(prefix)
            log.warning("llm_router.provider_error", provider=prefix, error=str(exc))
            return await self._complete_with_fallback(
                model, messages, tools, temperature, max_tokens,
                tool_choice=tool_choice,
            )

        if result.stop_reason == "blocked":
            # Gemini content blocks are per-request, not provider health (ADR-024)
            return await self._complete_with_fallback(
                model, messages, tools, temperature, max_tokens,
                original_result=result,
                tool_choice=tool_choice,
            )
        return result

    async def _complete_with_fallback(
        self,
        original_model: str,
        messages: Sequence[LLMMessage],
        tools: Sequence[LLMToolSpec] | None,
        temperature: float,
        max_tokens: int,
        original_result: LLMResponse | None = None,
        tool_choice: object | None = None,  # Wave 54
    ) -> LLMResponse:
        """Try fallback chain models (ADR-014 + ADR-024).

        Wave 50: per-request retry cap prevents infinite fallback loops.
        """
        result: LLMResponse | None = None
        retries = 0
        max_retries = self._cooldown.max_retries_per_request
        for fallback_model in self._fallback_chain:
            if retries >= max_retries:
                log.warning(
                    "llm_router.max_retries_exhausted",
                    original_model=original_model,
                    retries=retries,
                )
                break
            if fallback_model == original_model:
                continue
            fb_prefix = fallback_model.split("/", 1)[0]
            if fb_prefix not in self._adapters:
                continue
            if self._cooldown.is_cooled_down(fb_prefix):
                continue
            log.warning(
                "llm_router.fallback",
                blocked_model=original_model, fallback_model=fallback_model,
            )
            # Clamp max_tokens to fallback model's policy
            fb_record = self._registry_map.get(fallback_model)
            fb_max = fb_record.max_output_tokens if fb_record else max_tokens
            clamped = min(max_tokens, fb_max)
            retries += 1
            try:
                fb_adapter = self._adapters[fb_prefix]
                result = await fb_adapter.complete(
                    fallback_model, messages, tools=tools,
                    temperature=temperature, max_tokens=clamped,
                    tool_choice=tool_choice,
                )
                if result.stop_reason != "blocked":
                    return result
            except Exception:
                self._cooldown.record_failure(fb_prefix)
                continue

        # All fallbacks exhausted — return last result or original
        if result is not None:
            return result
        if original_result is not None:
            return original_result
        raise RuntimeError(
            f"All providers exhausted for model '{original_model}'"
        )

    async def stream(
        self,
        model: str,
        messages: Sequence[LLMMessage],
        tools: Sequence[LLMToolSpec] | None = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> AsyncIterator[LLMChunk]:
        adapter = self._resolve(model)
        async for chunk in adapter.stream(  # pyright: ignore[reportGeneralTypeIssues,reportUnknownVariableType]
            model, messages, tools=tools,
            temperature=temperature, max_tokens=max_tokens,
        ):
            yield chunk

    def provider_health(self) -> dict[str, str]:
        """Return current health status per adapter key.

        Wave 64: keys are now provider:endpoint. Cooldown still tracks
        by provider prefix (provider-level, not endpoint-level).
        """
        result: dict[str, str] = {}
        for adapter_key in self._adapters:
            provider = adapter_key.split(":")[0]
            if self._cooldown.is_cooled_down(provider):
                result[adapter_key] = "cooldown"
            else:
                result[adapter_key] = "ok"
        return result

    def _resolve(self, model: str) -> LLMPort:
        prefix = model.split("/", 1)[0]
        # Wave 64: look up by (provider:endpoint) key first, then fall
        # back to provider-only prefix for backward compatibility.
        # Check if any key starts with "prefix:" — use the endpoint from
        # the model registry to build the full key.
        rec = self._registry_map.get(model)
        if rec is not None:
            adapter_key = (
                f"{rec.provider}:{rec.endpoint or 'default'}"
            )
            adapter = self._adapters.get(adapter_key)
            if adapter is not None:
                return adapter
        # Fallback: try prefix:default, then bare prefix (backward compat),
        # then any key starting with prefix:
        adapter = self._adapters.get(f"{prefix}:default")
        if adapter is not None:
            return adapter
        adapter = self._adapters.get(prefix)
        if adapter is not None:
            return adapter
        for key, adp in self._adapters.items():
            if key.startswith(f"{prefix}:"):
                return adp
        raise ValueError(
            f"No adapter registered for provider '{prefix}'"
        )


# ---------------------------------------------------------------------------
# Runtime
# ---------------------------------------------------------------------------


class Runtime:
    """Shared application service layer. Single mutation path for all operations."""

    def __init__(
        self,
        event_store: EventStorePort,
        projections: ProjectionStore,
        ws_manager: WebSocketManager,
        settings: SystemSettings,
        castes: CasteRecipeSet | None,
        llm_router: LLMRouter,
        embed_fn: Any | None,  # noqa: ANN401
        vector_store: VectorPort | None,
        cost_fn: Callable[[str, int, int], float] | None = None,
        kg_adapter: Any = None,  # noqa: ANN401
        embed_client: Any = None,  # noqa: ANN401
    ) -> None:
        self.event_store = event_store
        self.projections = projections
        self.ws_manager = ws_manager
        self.settings = settings
        self.castes = castes
        self.llm_router = llm_router
        self.embed_fn = embed_fn
        self.embed_client = embed_client
        self.vector_store = vector_store
        self.cost_fn: Callable[[str, int, int], float] = cost_fn or (lambda m, i, o: 0.0)
        self.kg_adapter = kg_adapter
        self._wire_kg_events()
        # Set by app.py after colony_manager is created
        self.colony_manager: Any = None  # noqa: ANN401
        # Set by app.py after queen is created
        self.queen: Any = None  # noqa: ANN401
        # Set by app.py after memory store is created (Wave 26)
        self.memory_store: Any = None  # noqa: ANN401

    def _wire_kg_events(self) -> None:
        """Inject KG event callback into the adapter (Wave 14 Stream D)."""
        if self.kg_adapter is None or not hasattr(self.kg_adapter, "_event_cb"):
            return

        _EVENT_CLASSES: dict[str, type[FormicOSEvent]] = {
            "KnowledgeEntityCreated": KnowledgeEntityCreated,  # type: ignore[dict-item]
            "KnowledgeEdgeCreated": KnowledgeEdgeCreated,  # type: ignore[dict-item]
            "KnowledgeEntityMerged": KnowledgeEntityMerged,  # type: ignore[dict-item]
        }

        async def _kg_event_cb(event_type: str, **kwargs: Any) -> None:
            cls = _EVENT_CLASSES.get(event_type)
            if cls is None:
                return
            event = cls(  # type: ignore[call-arg]
                seq=0,
                timestamp=datetime.now(UTC),
                address="system",
                **kwargs,
            )
            await self.emit_and_broadcast(event)

        self.kg_adapter._event_cb = _kg_event_cb  # noqa: SLF001

    async def emit_and_broadcast(self, event: FormicOSEvent) -> int:
        """The ONE mutation path: append → project → fan out to WS."""
        seq = await self.event_store.append(event)
        event_with_seq = event.model_copy(update={"seq": seq})  # pyright: ignore[reportAttributeAccessIssue]
        self.projections.apply(event_with_seq)
        await self.ws_manager.fan_out_event(event_with_seq)

        # Live sync: push memory events into Qdrant (Wave 26.5)
        if self.memory_store is not None:
            etype = getattr(event_with_seq, "type", "")
            sync_id: str = ""
            if etype == "MemoryEntryCreated":
                sync_id = str(getattr(event_with_seq, "entry", {}).get("id", ""))
            elif etype == "MemoryEntryStatusChanged":
                sync_id = str(getattr(event_with_seq, "entry_id", ""))
            elif etype == "MemoryEntryMerged":
                sync_id = str(getattr(event_with_seq, "target_id", ""))
            elif etype in ("MemoryConfidenceUpdated", "MemoryEntryRefined"):
                sync_id = str(getattr(event_with_seq, "entry_id", ""))
            if sync_id:
                await self.memory_store.sync_entry(
                    sync_id, self.projections.memory_entries,
                )

        # Wave 59.5: bridge memory entries to knowledge graph
        if self.kg_adapter is not None:
            etype = getattr(event_with_seq, "type", "")
            if etype == "MemoryEntryCreated":
                entry = getattr(event_with_seq, "entry", {})
                entry_id = str(
                    entry.get("id", "") if isinstance(entry, dict)
                    else getattr(entry, "id", "")
                )
                title = str(
                    entry.get("title", "") if isinstance(entry, dict)
                    else getattr(entry, "title", "")
                )
                ws_id = str(
                    entry.get("workspace_id", "") if isinstance(entry, dict)
                    else getattr(entry, "workspace_id", "")
                )
                canonical_type = str(
                    entry.get("canonical_type", "skill") if isinstance(entry, dict)
                    else getattr(entry, "canonical_type", "skill")
                )
                if entry_id and title:
                    try:
                        entity_type = "SKILL" if canonical_type == "skill" else "CONCEPT"
                        node_id = await self.kg_adapter.resolve_entity(
                            name=title,
                            entity_type=entity_type,
                            workspace_id=ws_id,
                            source_colony=str(
                                entry.get("source_colony_id", "")
                                if isinstance(entry, dict)
                                else getattr(entry, "source_colony_id", "")
                            ),
                        )
                        self.projections.entry_kg_nodes[entry_id] = node_id
                    except Exception:  # noqa: BLE001
                        log.warning("kg_bridge.create_failed", entry_id=entry_id)

            elif etype == "MemoryEntryRefined":
                entry_id = str(getattr(event_with_seq, "entry_id", ""))
                source_colony = str(getattr(event_with_seq, "source_colony_id", ""))
                node_id = self.projections.entry_kg_nodes.get(entry_id, "")
                if node_id:
                    try:
                        ws_id = str(getattr(event_with_seq, "workspace_id", ""))
                        await self.kg_adapter.add_edge(
                            from_node=node_id, to_node=node_id,
                            predicate="SUPERSEDES",
                            workspace_id=ws_id,
                            source_colony=source_colony,
                            confidence=0.9,
                        )
                    except Exception:  # noqa: BLE001
                        log.warning("kg_bridge.refine_edge_failed", entry_id=entry_id)

            elif etype == "MemoryEntryMerged":
                target_id = str(getattr(event_with_seq, "target_id", ""))
                source_id = str(getattr(event_with_seq, "source_id", ""))
                t_node = self.projections.entry_kg_nodes.get(target_id, "")
                s_node = self.projections.entry_kg_nodes.get(source_id, "")
                if t_node and s_node:
                    try:
                        ws_id = str(getattr(event_with_seq, "workspace_id", ""))
                        await self.kg_adapter.add_edge(
                            from_node=t_node, to_node=s_node,
                            predicate="DERIVED_FROM",
                            workspace_id=ws_id,
                            confidence=0.9,
                        )
                    except Exception:  # noqa: BLE001
                        log.warning("kg_bridge.merge_edge_failed")

        return seq

    async def _rebuild_entry_kg_nodes(self) -> None:
        """Rebuild entry_kg_nodes mapping from KG database after replay."""
        if self.kg_adapter is None:
            return
        for entry_id, entry in self.projections.memory_entries.items():
            title = entry.get("title", "")
            ws_id = entry.get("workspace_id", "")
            if title and ws_id:
                try:
                    node_id = await self.kg_adapter.resolve_entity(
                        name=title,
                        entity_type=(
                            "SKILL" if entry.get("canonical_type") == "skill"
                            else "CONCEPT"
                        ),
                        workspace_id=ws_id,
                    )
                    self.projections.entry_kg_nodes[entry_id] = node_id
                except Exception:  # noqa: BLE001
                    pass

    # -- Operation functions (shared by MCP and WS commands) --

    async def create_workspace(self, name: str) -> str:
        """Create a new workspace. Returns workspace name/id."""
        await self.emit_and_broadcast(WorkspaceCreated(
            seq=0, timestamp=_now(), address=name,
            name=name,
            config=WorkspaceConfigSnapshot(
                budget=self.settings.governance.default_budget_per_colony,
                strategy=self.settings.routing.default_strategy,
            ),
        ))
        ws_dir = Path(self.settings.system.data_dir) / "workspaces" / name / "files"
        ws_dir.mkdir(parents=True, exist_ok=True)
        return name

    async def create_thread(
        self, workspace_id: str, name: str, *,
        goal: str = "", expected_outputs: list[str] | None = None,
    ) -> str:
        """Create a new thread in a workspace. Returns thread name/id."""
        address = f"{workspace_id}/{name}"
        await self.emit_and_broadcast(ThreadCreated(
            seq=0, timestamp=_now(), address=address,
            workspace_id=workspace_id, name=name,
            goal=goal,
            expected_outputs=expected_outputs or [],
        ))
        return name

    async def rename_thread(
        self, workspace_id: str, thread_id: str, new_name: str,
        renamed_by: str = "operator",
    ) -> None:
        """Rename a thread (display-only, does not change addresses)."""
        address = f"{workspace_id}/{thread_id}"
        await self.emit_and_broadcast(ThreadRenamed(
            seq=0, timestamp=_now(), address=address,
            workspace_id=workspace_id, thread_id=thread_id,
            new_name=new_name, renamed_by=renamed_by,
        ))

    _MAX_INPUT_SOURCE_SUMMARY_TOKENS = 2000

    async def spawn_colony(
        self,
        workspace_id: str,
        thread_id: str,
        task: str,
        castes: list[CasteSlot],
        strategy: str = "stigmergic",
        max_rounds: int = 25,
        budget_limit: float = 5.0,
        model_assignments: dict[str, str] | None = None,
        template_id: str = "",
        input_sources: list[InputSource] | None = None,
        step_index: int = -1,
        target_files: list[str] | None = None,
        fast_path: bool = False,
        spawn_source: str = "",
    ) -> str:
        """Spawn a new colony. Returns colony_id.

        If *input_sources* is provided, each source is resolved eagerly
        (ADR-033). The resolved summaries are stored on the ColonySpawned
        event so replay never depends on later lookups.

        If *target_files* is provided, the colony will focus on those
        files (Wave 41 multi-file coordination).
        """
        resolved_sources = self._resolve_input_sources(input_sources or [])
        colony_id = f"colony-{uuid4().hex[:8]}"
        address = f"{workspace_id}/{thread_id}/{colony_id}"
        await self.emit_and_broadcast(ColonySpawned(
            seq=0, timestamp=_now(), address=address,
            thread_id=thread_id, task=task, castes=castes,
            model_assignments=model_assignments or {},
            strategy=strategy,  # type: ignore[arg-type]
            max_rounds=max_rounds, budget_limit=budget_limit,
            template_id=template_id,
            input_sources=resolved_sources,
            step_index=step_index,
            target_files=target_files or [],
            fast_path=fast_path,
            spawn_source=spawn_source,
        ))
        return colony_id

    def _resolve_input_sources(
        self, sources: list[InputSource],
    ) -> list[InputSource]:
        """Resolve input sources at spawn time (ADR-033).

        For type="colony": source must exist and be completed.
        Prefers Archivist summary, falls back to truncated final round outputs.
        """
        resolved: list[InputSource] = []
        for src in sources:
            if src.type == "colony":
                colony = self.projections.get_colony(src.colony_id)
                if colony is None:
                    raise ValueError(
                        f"Source colony '{src.colony_id}' not found.",
                    )
                if colony.status != "completed":
                    raise ValueError(
                        f"Source colony '{src.colony_id}' is "
                        f"{colony.status}. Chain only from completed colonies.",
                    )
                summary = self._get_colony_compressed_output(colony)
                resolved.append(InputSource(
                    type="colony",
                    colony_id=src.colony_id,
                    summary=summary,
                    artifacts=getattr(colony, "artifacts", []),
                ))
        return resolved

    def _get_colony_compressed_output(self, colony: Any) -> str:  # noqa: ANN401
        """Extract a compressed summary from a completed colony.

        Preference: Archivist summary > truncated final round outputs.
        Capped at _MAX_INPUT_SOURCE_SUMMARY_TOKENS * 4 characters.
        """
        max_chars = self._MAX_INPUT_SOURCE_SUMMARY_TOKENS * 4

        # Try Archivist summary from the colony's round records
        if colony.round_records:
            last_round = colony.round_records[-1]
            if last_round.agent_outputs:
                # Look for archivist output first
                for aid, output in last_round.agent_outputs.items():
                    agent = colony.agents.get(aid)
                    if agent and agent.caste == "archivist" and output:
                        return output[:max_chars]

                # Fall back to all final round outputs, truncated
                parts: list[str] = []
                budget = max_chars
                for _aid, output in last_round.agent_outputs.items():
                    if not output or budget <= 0:
                        continue
                    chunk = output[:budget]
                    parts.append(chunk)
                    budget -= len(chunk)
                return "\n---\n".join(parts)

        return ""

    async def kill_colony(self, colony_id: str, killed_by: str = "operator") -> None:
        colony = self.projections.get_colony(colony_id)
        address = colony_id if colony is None else (
            f"{colony.workspace_id}/{colony.thread_id}/{colony.id}"
        )
        await self.emit_and_broadcast(ColonyKilled(
            seq=0, timestamp=_now(), address=address,
            colony_id=colony_id, killed_by=killed_by,
        ))
        if self.colony_manager is not None:
            await self.colony_manager.stop_colony(colony_id)

    async def send_queen_message(
        self, workspace_id: str, thread_id: str, content: str,
    ) -> None:
        address = f"{workspace_id}/{thread_id}"
        await self.emit_and_broadcast(QueenMessage(
            seq=0, timestamp=_now(), address=address,
            thread_id=thread_id, role="operator", content=content,
        ))
        thread = self.projections.get_thread(workspace_id, thread_id)
        if (
            thread is not None
            and thread.name == thread_id
            and thread_id.startswith("thread-")
        ):
            operator_messages = [
                m for m in thread.queen_messages if m.role == "operator"
            ]
            if len(operator_messages) <= 1:
                display_name = _derive_thread_display_name(content)
                if display_name and display_name != thread.name:
                    await self.rename_thread(
                        workspace_id,
                        thread_id,
                        display_name,
                        renamed_by="queen",
                    )

    async def create_merge(
        self, workspace_id: str, from_colony: str, to_colony: str,
        created_by: str = "operator",
    ) -> str:
        edge_id = f"merge-{uuid4().hex[:8]}"
        await self.emit_and_broadcast(MergeCreated(
            seq=0, timestamp=_now(), address=workspace_id,
            edge_id=edge_id, from_colony=from_colony,
            to_colony=to_colony, created_by=created_by,
        ))
        return edge_id

    async def prune_merge(self, workspace_id: str, edge_id: str) -> None:
        await self.emit_and_broadcast(MergePruned(
            seq=0, timestamp=_now(), address=workspace_id,
            edge_id=edge_id, pruned_by="operator",
        ))

    async def broadcast(
        self, workspace_id: str, thread_id: str, from_colony: str,
    ) -> list[str]:
        thread = self.projections.get_thread(workspace_id, thread_id)
        if thread is None:
            return []
        edges: list[str] = []
        for cid in thread.colonies:
            if cid != from_colony:
                edge_id = await self.create_merge(workspace_id, from_colony, cid)
                edges.append(edge_id)
        return edges

    async def approve(self, workspace_id: str, request_id: str) -> None:
        await self.emit_and_broadcast(ApprovalGranted(
            seq=0, timestamp=_now(), address=workspace_id,
            request_id=request_id,
        ))

    async def deny(self, workspace_id: str, request_id: str) -> None:
        await self.emit_and_broadcast(ApprovalDenied(
            seq=0, timestamp=_now(), address=workspace_id,
            request_id=request_id,
        ))

    _CASTE_MODEL_FIELDS = {"queen_model", "coder_model", "reviewer_model",
                           "researcher_model", "archivist_model"}

    async def update_config(
        self, workspace_id: str, field: str, value: str | float | None,
    ) -> None:
        new_value = str(value) if value is not None else None

        # Caste model fields emit ModelAssignmentChanged for projection parity
        if field in self._CASTE_MODEL_FIELDS:
            caste = field.removesuffix("_model")
            ws = self.projections.workspaces.get(workspace_id)
            old_value = ws.config.get(field) if ws else None
            await self.emit_and_broadcast(ModelAssignmentChanged(
                seq=0, timestamp=_now(), address=workspace_id,
                scope=workspace_id, caste=caste,
                old_model=str(old_value) if old_value else None,
                new_model=new_value,
            ))
        else:
            await self.emit_and_broadcast(WorkspaceConfigChanged(
                seq=0, timestamp=_now(), address=workspace_id,
                workspace_id=workspace_id, field=field,
                old_value=None, new_value=new_value,
            ))

    # -- Model cascade resolution (algorithms.md §10) --

    def resolve_model(self, caste: str, workspace_id: str | None = None) -> str:
        """Resolve the model address for a caste using thread→workspace→system cascade."""
        # Workspace override
        if workspace_id:
            ws = self.projections.workspaces.get(workspace_id)
            if ws and ws.config:
                ws_value = ws.config.get(f"{caste}_model")
                if ws_value is not None:
                    return str(ws_value)
        # System defaults
        defaults = self.settings.models.defaults.model_dump()
        return str(defaults.get(caste, defaults.get("coder", "")))

    def build_agents(self, colony_id: str) -> list[AgentConfig]:
        """Build AgentConfig list from colony projection + caste recipes.

        Iterates over colony.castes (list[CasteSlot]) and expands each
        slot's ``count`` into individual AgentConfig instances.

        Model resolution order (per slot):
        1. colony.model_assignments[caste]  (explicit spawn-time override)
        2. recipe.tier_models[slot.tier]    (tier-specific recipe model)
        3. resolve_model(caste, workspace)  (workspace → system cascade)

        Effective policy is computed from ModelRecord x caste base values:
        - effective_output_tokens = model.max_output_tokens
        - effective_time_limit_s  = base_time x model.time_multiplier
        - effective_tool_calls    = base_tools x model.tool_call_multiplier
        """
        colony = self.projections.get_colony(colony_id)
        if colony is None or self.castes is None:
            return []

        # Build registry map for model policy lookup
        registry_map: dict[str, ModelRecord] = {
            m.address: m for m in self.settings.models.registry
        }

        agents: list[AgentConfig] = []
        idx = 0
        for slot in colony.castes:
            caste_name = slot.caste.lower()
            recipe = self.castes.castes.get(caste_name)
            if recipe is None:
                continue
            # Tier-aware model resolution
            explicit = colony.model_assignments.get(slot.caste)
            tier_model = recipe.tier_models.get(slot.tier.value)
            cascade = self.resolve_model(caste_name, colony.workspace_id)
            model = explicit or tier_model or cascade

            # Compute effective policy from model record
            model_rec = registry_map.get(model)
            eff_output = (
                model_rec.max_output_tokens if model_rec else recipe.max_tokens
            )
            eff_time = int(
                recipe.max_execution_time_s
                * (model_rec.time_multiplier if model_rec else 1.0)
            )
            eff_tools = int(
                recipe.base_tool_calls_per_iteration
                * (model_rec.tool_call_multiplier if model_rec else 1.0)
            )

            for _ in range(slot.count):
                agent_id = (
                    f"{caste_name}-{idx}-{colony_id.split('-')[-1][:8]}"
                )
                agents.append(AgentConfig(
                    id=agent_id, name=recipe.name, caste=caste_name,
                    model=model, recipe=recipe,
                    effective_output_tokens=eff_output,
                    effective_time_limit_s=eff_time,
                    effective_tool_calls=eff_tools,
                ))
                idx += 1
        return agents

    # -- Suggest-team (ADR-016, algorithms.md §A6) --

    async def suggest_team(self, objective: str) -> list[dict[str, Any]]:
        """LLM recommends castes for a given objective.

        Routes to Gemini Flash if available, falls back to default model.
        Returns list of {caste, count, reasoning} dicts.
        """
        if not self.castes:
            return self._default_suggestion()

        caste_desc = "\n".join(
            f"- {name}: {c.description}"
            for name, c in self.castes.castes.items()
            if name != "queen"
        )
        prompt = (
            "Given this objective, recommend which castes to include in a colony.\n\n"
            f"Available castes:\n{caste_desc}\n\n"
            f"Objective: {objective}\n\n"
            'Respond as a JSON array. Each entry: '
            '{"caste": "name", "tier": "standard", "count": 1, "reasoning": "brief why"}\n'
            "Valid tiers: light, standard, heavy, flash.\n"
            "Include only castes that are genuinely needed. "
            "Typical colony size is 2-4 agents."
        )
        try:
            # Prefer Gemini Flash (cheap); LLMRouter fallback chain
            # handles unavailable providers automatically
            model = self.resolve_model("queen")
            response = await self.llm_router.complete(
                model=model,
                messages=[{"role": "user", "content": prompt}],  # type: ignore[list-item]
                temperature=0.0,
                max_tokens=500,
            )
            import json_repair
            result = json_repair.loads(response.content)
            if isinstance(result, list):
                return result  # pyright: ignore[reportReturnType]
        except Exception:
            log.debug("suggest_team.llm_failed", objective=objective[:100])

        return self._default_suggestion()

    @staticmethod
    def _default_suggestion() -> list[dict[str, Any]]:
        return [
            {
                "caste": "coder", "tier": "standard",
                "count": 1, "reasoning": "Default implementation agent",
            },
            {
                "caste": "reviewer", "tier": "light",
                "count": 1, "reasoning": "Default quality gate",
            },
        ]

    # -- Config mutation (Wave 19 — approval-driven) --

    async def apply_config_change(
        self,
        param_path: str,
        proposed_value: str,
        workspace_id: str,
    ) -> None:
        """Apply a validated config change: in-memory + persist + event.

        Parses the dot-path to determine the target (caste recipe field,
        governance, or routing) and delegates to existing persistence.
        """
        parts = param_path.split(".")

        # castes.{caste}.{field} — update caste recipe
        if len(parts) == 3 and parts[0] == "castes" and self.castes:
            caste_name, field_name = parts[1], parts[2]
            recipe = self.castes.castes.get(caste_name)
            if recipe is None:
                raise ValueError(f"Unknown caste: {caste_name}")
            old_value = str(getattr(recipe, field_name, ""))
            # Coerce value
            coerced = self._coerce_config_value(recipe, field_name, proposed_value)
            # Mutate in-memory (CasteRecipe is not frozen in the registry)
            object.__setattr__(recipe, field_name, coerced)
            # Persist via existing caste save path
            await self._persist_castes()
            # Emit event
            await self.emit_and_broadcast(WorkspaceConfigChanged(
                seq=0, timestamp=_now(), address=workspace_id,
                workspace_id=workspace_id, field=param_path,
                old_value=old_value, new_value=proposed_value,
            ))
            log.info(
                "config.applied",
                param_path=param_path, old=old_value, new=proposed_value,
            )
            return

        # governance.{field} or routing.{field}
        if len(parts) == 2 and parts[0] in ("governance", "routing"):
            section = getattr(self.settings, parts[0], None)
            if section is None:
                raise ValueError(f"Unknown config section: {parts[0]}")
            field_name = parts[1]
            old_value = str(getattr(section, field_name, ""))
            coerced = self._coerce_settings_value(section, field_name, proposed_value)
            object.__setattr__(section, field_name, coerced)
            await self.emit_and_broadcast(WorkspaceConfigChanged(
                seq=0, timestamp=_now(), address=workspace_id,
                workspace_id=workspace_id, field=param_path,
                old_value=old_value, new_value=proposed_value,
            ))
            log.info(
                "config.applied",
                param_path=param_path, old=old_value, new=proposed_value,
            )
            return

        raise ValueError(f"Cannot apply config change to path: {param_path}")

    @staticmethod
    def _coerce_config_value(recipe: Any, field_name: str, value: str) -> Any:  # noqa: ANN401
        """Coerce string value to match the type of the existing recipe field."""
        current = getattr(recipe, field_name, None)
        if isinstance(current, float):
            return float(value)
        if isinstance(current, int):
            return int(value)
        return value

    @staticmethod
    def _coerce_settings_value(section: Any, field_name: str, value: str) -> Any:  # noqa: ANN401
        """Coerce string value to match the type of an existing settings field."""
        current = getattr(section, field_name, None)
        if isinstance(current, float):
            return float(value)
        if isinstance(current, int):
            return int(value)
        return value

    async def _persist_castes(self) -> None:
        """Persist caste recipes to YAML via the existing save path."""
        if self.castes is None:
            return
        try:
            from pathlib import Path  # noqa: PLC0415

            import yaml  # noqa: PLC0415

            castes_path = (
                Path(self.settings.system.data_dir) / ".." / "config" / "caste_recipes.yaml"
            )
            # Fallback to standard location
            if not castes_path.exists():
                castes_path = Path(__file__).resolve().parents[3] / "config" / "caste_recipes.yaml"
            if castes_path.exists():
                data = {
                    name: recipe.model_dump()
                    for name, recipe in self.castes.castes.items()
                }
                with castes_path.open("w", encoding="utf-8") as f:
                    yaml.safe_dump({"castes": data}, f, default_flow_style=False)
                log.info("config.castes_persisted", path=str(castes_path))
        except Exception:
            log.exception("config.persist_failed")

    # -- Tool call parsing helper --

    @staticmethod
    def parse_tool_input(tc: dict[str, Any]) -> dict[str, Any]:
        """Normalize tool call input across Anthropic and OpenAI formats."""
        if "input" in tc:
            return tc["input"]  # pyright: ignore[reportReturnType]
        args = tc.get("arguments", "{}")
        if isinstance(args, str):
            return json.loads(args)  # pyright: ignore[reportReturnType]
        return args  # pyright: ignore[reportReturnType]

    # -- Pre-spawn memory retrieval (Wave 26 B3) --

    async def retrieve_relevant_memory(
        self,
        task: str,
        workspace_id: str,
        thread_id: str = "",
    ) -> str:
        """Deterministic pre-spawn knowledge retrieval.

        Searches the unified knowledge catalog for skills and experiences
        relevant to *task* and returns a formatted block for Queen context
        injection.

        Called by ``QueenAgent.respond()`` before the first LLM call.
        This is a deterministic runtime action, not a model-facing nudge.
        """
        catalog = getattr(self, "knowledge_catalog", None)
        if catalog is None:
            return ""

        try:
            results: list[dict[str, Any]] = await catalog.search(
                query=task,
                workspace_id=workspace_id,
                thread_id=thread_id,
                top_k=5,
            )
        except Exception:
            log.debug("runtime.memory_retrieval_failed", task=task[:80])
            return ""

        if not results:
            return ""

        lines = [f"[System Knowledge -- {len(results)} entries found]"]

        for entry in results:
            ctype = str(entry.get("canonical_type", "skill")).upper()
            source = str(entry.get("source_system", ""))
            status_tag = str(entry.get("status", "candidate")).upper()
            polarity = str(entry.get("polarity", "positive"))
            polarity_tag = f", {polarity}" if polarity != "positive" else ""
            title = entry.get("title", "")
            content = str(entry.get("content_preview", ""))[:300]
            colony = entry.get("source_colony_id", "")
            conf = entry.get("confidence", 0.5)
            lines.append(
                f'[{ctype}, {status_tag}, {source}{polarity_tag}] '
                f'"{title}": {content}',
            )
            lines.append(f"  source: colony {colony}, confidence: {conf:.1f}")

        return "\n".join(lines)


    # -- Unified knowledge fetch for agent context (Wave 28 A1) --

    async def fetch_knowledge_for_colony(
        self,
        task: str,
        workspace_id: str,
        thread_id: str = "",
        top_k: int = 8,   # Wave 58: wider net for index-only format
    ) -> list[dict[str, Any]]:
        """Fetch unified knowledge items from the catalog for agent context.

        Returns normalized KnowledgeItem dicts from the Wave 27 knowledge
        catalog.  Called by colony_manager before each round.
        """
        catalog = getattr(self, "knowledge_catalog", None)
        if catalog is None:
            return []
        try:
            return await catalog.search(
                query=task, workspace_id=workspace_id,
                thread_id=thread_id, top_k=top_k,
            )
        except Exception:
            log.debug("runtime.knowledge_fetch_failed", task=task[:80])
            return []

    # -- Callback factories for progressive-disclosure tools (Wave 28 A1) --

    def make_catalog_search_fn(
        self,
    ) -> Callable[..., Any] | None:
        """Create a callback for the repointed agent memory_search tool."""
        catalog = getattr(self, "knowledge_catalog", None)
        if catalog is None:
            return None

        runtime_ref = self

        async def _catalog_search(
            query: str,
            workspace_id: str,
            top_k: int = 5,
            tier: str = "auto",
        ) -> list[dict[str, Any]]:
            results = await catalog.search_tiered(
                query=query, workspace_id=workspace_id,
                top_k=top_k, tier=tier,
            )
            # Wave 44: dispatch reactive forage signal as background task
            if results:
                signal = results[0].get("_forage_signal")
                if signal is not None:
                    forager_svc = getattr(runtime_ref, "forager_service", None)
                    if forager_svc is not None:
                        import asyncio  # noqa: PLC0415

                        task = asyncio.create_task(
                            forager_svc.handle_forage_signal(signal),
                        )
                        task.add_done_callback(_log_forage_task)
            return results

        return _catalog_search

    def make_knowledge_detail_fn(
        self,
    ) -> Callable[..., Any] | None:
        """Create a callback for the knowledge_detail agent tool."""
        catalog = getattr(self, "knowledge_catalog", None)
        if catalog is None:
            return None

        async def _knowledge_detail(item_id: str) -> str:
            result = await catalog.get_by_id(item_id)
            if result is None:
                return f"Error: knowledge item '{item_id}' not found"

            title = result.get("title", "")
            source = result.get("source_system", "")
            ctype = result.get("canonical_type", "skill").upper()

            # Wave 58: trajectory entries get structured step display
            traj_data = result.get("trajectory_data", [])
            sub_type = result.get("sub_type", "")
            if sub_type == "trajectory" and traj_data:
                content = result.get("content_preview", "") or result.get("content", "")
                lines = [f"[TRAJECTORY, {source}] {title}", "", content, ""]

                # Group steps by round
                rounds: dict[int, list[str]] = {}
                for step in traj_data:
                    rn = step.get("round_number", 0)
                    agent_id = step.get("agent_id", "?")
                    tool = step.get("tool", "?")
                    rounds.setdefault(rn, []).append(f"{agent_id}: {tool}")

                lines.append("Tool sequence:")
                for rn in sorted(rounds):
                    tools_str = ", ".join(rounds[rn])
                    lines.append(f"  Round {rn}: {tools_str}")

                domains = result.get("domains", [])
                tool_refs = result.get("tool_refs", [])
                if domains:
                    lines.append(f"\nDomains: {', '.join(domains)}")
                if tool_refs:
                    lines.append(f"Tools referenced: {', '.join(tool_refs)}")

                return "\n".join(lines)

            # Standard (non-trajectory) format
            content = (
                result.get("content_preview", "") or result.get("summary", "")
            )
            return (
                f"[{ctype}, {source}] "
                f"{title}\n\n{content}"
            )

        return _knowledge_detail

    def make_artifact_inspect_fn(
        self,
    ) -> Callable[..., Any] | None:
        """Create a callback for the artifact_inspect agent tool."""
        projections = self.projections

        async def _artifact_inspect(
            colony_id: str, artifact_id: str,
        ) -> str:
            colony = projections.get_colony(colony_id)
            if colony is None:
                return f"Error: colony '{colony_id}' not found"
            for art in colony.artifacts:
                art_dict: dict[str, Any] = art
                if art_dict.get("id") == artifact_id:
                    name = art_dict.get("name", "unnamed")
                    atype = art_dict.get("artifact_type", "generic")
                    content = art_dict.get("content", "")
                    return (
                        f"[Artifact: {name} ({atype})]\n\n"
                        f"{content[:5000]}"
                    )
            return (
                f"Error: artifact '{artifact_id}' not found "
                f"in colony '{colony_id}'"
            )

        return _artifact_inspect

    def make_transcript_search_fn(self) -> Callable[..., Any] | None:
        """Create a callback for the transcript_search agent tool."""
        projections = self.projections

        async def _transcript_search(
            query: str, workspace_id: str, top_k: int = 3,
        ) -> str:
            # Collect completed colonies for this workspace
            colonies = [
                c for c in projections.colonies.values()
                if getattr(c, "workspace_id", "") == workspace_id
                and getattr(c, "status", "") in ("completed", "failed")
            ]
            if not colonies:
                return "No completed colonies found in this workspace."

            # Build search corpus: task + last round output
            def _last_output(colony_proj: object) -> str:
                rounds: list[object] = getattr(colony_proj, "round_records", [])  # type: ignore[assignment]
                if not rounds:
                    return ""
                last_round = rounds[-1]
                agent_outputs: dict[str, str] = getattr(last_round, "agent_outputs", {})  # type: ignore[assignment]
                if not agent_outputs:
                    return ""
                # Return last agent's output
                vals = list(agent_outputs.values())
                return str(vals[-1] if vals else "")[:500]

            corpus_texts = [
                f"{getattr(c, 'task', '')} {_last_output(c)}"
                for c in colonies
            ]

            # Try BM25 search first, fall back to word overlap
            scored: list[tuple[float, Any]] = []
            try:
                import bm25s  # type: ignore[import-not-found]  # noqa: PLC0415

                def _code_tokenizer(texts: list[str]) -> list[list[str]]:
                    import re as _re  # noqa: PLC0415
                    result: list[list[str]] = []
                    for text in texts:
                        text = _re.sub(r"([a-z])([A-Z])", r"\1 \2", text)
                        text = _re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", text)
                        tokens = _re.findall(r"\w+", text.lower())
                        result.append([t for t in tokens if len(t) > 1])
                    return result

                corpus_tokens = _code_tokenizer(corpus_texts)
                query_tokens = _code_tokenizer([query])
                retriever = bm25s.BM25()  # type: ignore[reportUnknownMemberType]
                retriever.index(corpus_tokens)  # type: ignore[reportUnknownMemberType]
                bm25_results, bm25_scores = retriever.retrieve(  # type: ignore[reportUnknownMemberType]
                    query_tokens, k=min(top_k, len(colonies)),
                )
                for i in range(len(bm25_results[0])):  # type: ignore[reportUnknownArgumentType]
                    idx = int(bm25_results[0][i])  # type: ignore[reportUnknownArgumentType]
                    scored.append((float(bm25_scores[0][i]), colonies[idx]))  # type: ignore[reportUnknownArgumentType]
            except ImportError:
                # Fallback: word-overlap scoring (no dependency)
                query_words = set(query.lower().split())
                for i, text in enumerate(corpus_texts):
                    entry_words = set(text.lower().split())
                    overlap = len(query_words & entry_words)
                    if overlap > 0:
                        scored.append((float(overlap), colonies[i]))
                scored.sort(key=lambda x: -x[0])
                scored = scored[:top_k]

            if not scored:
                return f"No matching colonies found for query: {query}"

            # Format results as pointers (not full transcripts)
            lines: list[str] = []
            for _score, colony in scored:
                cid = getattr(colony, "id", "?")
                status = getattr(colony, "status", "?")
                task = str(getattr(colony, "task", ""))[:100]
                output_snippet = _last_output(colony)[:200]
                artifacts: list[object] = getattr(colony, "artifacts", [])  # type: ignore[assignment]
                art_count = len(artifacts) if artifacts else 0
                art_types: set[str] = set()
                for art in artifacts or []:
                    if isinstance(art, dict):
                        art_dict: dict[str, Any] = art  # type: ignore[assignment]
                        art_types.add(str(art_dict.get("artifact_type", "generic")))
                    else:
                        art_types.add("generic")

                # Quality score and knowledge extraction count
                quality = getattr(colony, "quality_score", None)
                quality_str = f", quality: {quality:.2f}" if quality is not None else ""
                skills_count = len(getattr(colony, "skills_extracted", []) or [])
                knowledge_line = (
                    f"\n  Knowledge extracted: {skills_count} entries"
                    if skills_count > 0
                    else ""
                )

                lines.append(
                    f"[Colony {cid[:8]} ({status}{quality_str})] Task: {task}\n"
                    f"  Output snippet: {output_snippet}\n"
                    f"  Artifacts: {art_count}"
                    f" ({', '.join(sorted(art_types)) if art_types else 'none'})"
                    f"{knowledge_line}"
                )
            return "\n\n".join(lines)

        return _transcript_search

    def make_knowledge_feedback_fn(
        self,
        colony_id: str,
        workspace_id: str,
        thread_id: str = "",
    ) -> Callable[..., Any] | None:
        """Create a callback for the knowledge_feedback agent tool (B7)."""
        runtime = self

        async def _knowledge_feedback(
            entry_id: str, helpful: bool, reason: str = "",
        ) -> str:
            entry = runtime.projections.memory_entries.get(entry_id)
            if not entry:
                return f"Entry {entry_id} not found"

            from formicos.core.events import MemoryConfidenceUpdated  # noqa: PLC0415
            from formicos.surface.knowledge_constants import (  # noqa: PLC0415
                GAMMA_PER_DAY,
                GAMMA_RATES,
                MAX_ELAPSED_DAYS,
                PRIOR_ALPHA,
                PRIOR_BETA,
            )

            event_ts = datetime.now(UTC)
            old_alpha = float(entry.get("conf_alpha", PRIOR_ALPHA))
            old_beta = float(entry.get("conf_beta", PRIOR_BETA))

            # Gamma-decay before update
            last_updated = entry.get(
                "last_confidence_update", entry.get("created_at", ""),
            )
            elapsed_days = 0.0
            if last_updated:
                try:
                    elapsed_days = (
                        event_ts - datetime.fromisoformat(last_updated)
                    ).total_seconds() / 86400.0
                    elapsed_days = max(elapsed_days, 0.0)
                except (ValueError, TypeError):
                    elapsed_days = 0.0
            elapsed_days = min(elapsed_days, MAX_ELAPSED_DAYS)
            decay_class = entry.get("decay_class", "ephemeral")
            gamma = GAMMA_RATES.get(decay_class, GAMMA_PER_DAY)
            gamma_eff = gamma ** elapsed_days
            decayed_alpha = gamma_eff * old_alpha + (1 - gamma_eff) * PRIOR_ALPHA
            decayed_beta = gamma_eff * old_beta + (1 - gamma_eff) * PRIOR_BETA

            if helpful:
                new_alpha = max(decayed_alpha + 1.0, 1.0)
                new_beta = max(decayed_beta, 1.0)
                feedback_reason = "agent_feedback_positive"
            else:
                new_alpha = max(decayed_alpha, 1.0)
                new_beta = max(decayed_beta + 1.0, 1.0)
                entry["prediction_error_count"] = (
                    entry.get("prediction_error_count", 0) + 1
                )
                feedback_reason = "agent_feedback_negative"

            new_confidence = new_alpha / (new_alpha + new_beta)
            address = (
                f"{workspace_id}/{thread_id}/{colony_id}"
                if workspace_id
                else colony_id
            )
            await runtime.emit_and_broadcast(
                MemoryConfidenceUpdated(
                    seq=0,
                    timestamp=event_ts,
                    address=address,
                    entry_id=entry_id,
                    colony_id=colony_id,
                    colony_succeeded=helpful,
                    old_alpha=old_alpha,
                    old_beta=old_beta,
                    new_alpha=new_alpha,
                    new_beta=new_beta,
                    new_confidence=new_confidence,
                    workspace_id=workspace_id,
                    thread_id=thread_id,
                    reason=feedback_reason,
                ),
            )

            if helpful:
                return f"Positive feedback recorded for {entry_id}"
            return f"Negative feedback recorded for {entry_id}: {reason}"

        return _knowledge_feedback

    def make_forage_fn(self) -> Callable[..., Any] | None:
        """Create a callback for the request_forage agent tool (Wave 48).

        Returns None if the Forager service is not configured.
        The callback sends a forage request through the existing ForagerService,
        waits for the cycle to complete, and returns compressed findings with
        provenance.
        """
        forager_svc = getattr(self, "forager_service", None)
        if forager_svc is None:
            return None

        runtime_ref = self

        async def _request_forage(
            *,
            topic: str,
            context: str = "",
            domains: list[str] | None = None,
            max_results: int = 5,
            workspace_id: str = "",
            colony_id: str = "",
        ) -> str:
            signal = {
                "workspace_id": workspace_id,
                "trigger": "reactive",
                "gap_description": topic,
                "topic": topic,
                "context": context,
                "domains": domains or [],
                "max_results": min(max_results, 10),
                "colony_id": colony_id,
            }
            # Run the forage cycle synchronously (awaited, not fire-and-forget)
            try:
                await forager_svc.handle_forage_signal(signal)
            except Exception as exc:  # noqa: BLE001
                return f"Forage request failed: {exc}"

            # Collect recently admitted entries from projections
            entries = runtime_ref.projections.memory_entries
            admitted: list[dict[str, Any]] = []
            for entry_dict in entries.values():
                if (
                    entry_dict.get("source_colony_id") == "forager"
                    or entry_dict.get("source_system") == "forager"
                ):
                    # Check if this entry is recent and relevant
                    title = entry_dict.get("title", "")
                    content = entry_dict.get("content", "")
                    if topic.lower() in (title + content).lower():
                        admitted.append({
                            "id": entry_dict.get("id", ""),
                            "title": title,
                            "content": content[:300],
                            "source_url": entry_dict.get("web_source_url", ""),
                            "source_domain": entry_dict.get(
                                "web_source_domain", "",
                            ),
                        })
                if len(admitted) >= max_results:
                    break

            if not admitted:
                return (
                    f"Forage cycle completed for '{topic}' but no entries "
                    "were admitted (content may have been filtered or "
                    "deduplicated). Try refining the topic."
                )

            lines = [
                f"Forage completed: {len(admitted)} entries admitted "
                f"for '{topic}'.",
                "",
            ]
            for i, entry in enumerate(admitted, 1):
                lines.append(f"[{i}] {entry['title']}")
                if entry["source_url"]:
                    lines.append(f"    Source: {entry['source_url']}")
                lines.append(f"    {entry['content']}")
                lines.append("")
            return "\n".join(lines)

        return _request_forage


# ---------------------------------------------------------------------------
# Wave 43 Pillar 3: Budget enforcement
# ---------------------------------------------------------------------------


class BudgetEnforcer:
    """Hierarchical budget enforcement with operator-legible decisions.

    Layered checks:
    1. Workspace soft warning at 80% utilization
    2. Model downgrade at 90% utilization
    3. Workspace hard stop at 100%
    4. Spawn throttle when approaching limit

    All decisions are logged via structlog for operator inspection.
    Colony-level hard stops remain in colony_manager.py (ADR-009).
    """

    # Thresholds as fractions of budget_limit
    WARN_THRESHOLD: float = 0.80
    DOWNGRADE_THRESHOLD: float = 0.90
    HARD_STOP_THRESHOLD: float = 1.0

    def __init__(self, projections: ProjectionStore) -> None:
        self._projections = projections

    def check_spawn_allowed(self, workspace_id: str) -> tuple[bool, str]:
        """Check whether a new colony spawn is allowed under budget.

        Returns (allowed, reason). Blocks spawns when workspace budget
        is at or above hard stop threshold.
        """
        ws = self._projections.workspaces.get(workspace_id)
        if ws is None:
            return True, "workspace_unknown"
        if not isinstance(ws.budget_limit, (int, float)) or ws.budget_limit <= 0:
            return True, "no_budget_limit"
        # Wave 60: gate on api_cost (real money), not total_cost
        utilization = ws.budget.api_cost / ws.budget_limit if ws.budget_limit > 0 else 0.0
        if utilization >= self.HARD_STOP_THRESHOLD:
            log.warning(
                "budget_enforcer.spawn_blocked",
                workspace_id=workspace_id,
                api_cost=round(ws.budget.api_cost, 4),
                budget_limit=ws.budget_limit,
                utilization=round(utilization, 4),
            )
            return False, (
                f"Workspace budget exhausted "
                f"(${ws.budget.api_cost:.2f} of ${ws.budget_limit:.2f})"
            )
        if utilization >= self.WARN_THRESHOLD:
            log.info(
                "budget_enforcer.spawn_warning",
                workspace_id=workspace_id,
                utilization=round(utilization, 4),
            )
        return True, "ok"

    def check_model_downgrade(
        self, workspace_id: str, budget_remaining_colony: float,
    ) -> bool:
        """Return True if model should be downgraded to cheapest available.

        Triggers when workspace utilization exceeds DOWNGRADE_THRESHOLD
        OR colony-level budget_remaining is below $0.50.
        """
        ws = self._projections.workspaces.get(workspace_id)
        if (ws is not None
                and isinstance(ws.budget_limit, (int, float))
                and ws.budget_limit > 0):
            # Wave 60: gate on api_cost (real money), not total_cost
            utilization = ws.budget.api_cost / ws.budget_limit
            if utilization >= self.DOWNGRADE_THRESHOLD:
                if not ws.budget.downgrade_active:
                    ws.budget.downgrade_active = True
                    log.info(
                        "budget_enforcer.model_downgrade_activated",
                        workspace_id=workspace_id,
                        utilization=round(utilization, 4),
                    )
                return True
        return budget_remaining_colony < 0.50

    def check_workspace_hard_stop(self, workspace_id: str) -> tuple[bool, str]:
        """Check if workspace has hit hard budget stop.

        Returns (should_stop, reason).
        """
        ws = self._projections.workspaces.get(workspace_id)
        if (ws is None
                or not isinstance(ws.budget_limit, (int, float))
                or ws.budget_limit <= 0):
            return False, ""
        # Wave 60: gate on api_cost (real money), not total_cost
        utilization = ws.budget.api_cost / ws.budget_limit
        if utilization >= self.HARD_STOP_THRESHOLD:
            reason = (
                f"Workspace API budget exhausted "
                f"(${ws.budget.api_cost:.2f} of ${ws.budget_limit:.2f})"
            )
            log.warning(
                "budget_enforcer.workspace_hard_stop",
                workspace_id=workspace_id,
                api_cost=round(ws.budget.api_cost, 4),
                budget_limit=ws.budget_limit,
            )
            return True, reason
        # Soft warning (logged once)
        if utilization >= self.WARN_THRESHOLD and not ws.budget.warning_issued:
            ws.budget.warning_issued = True
            log.info(
                "budget_enforcer.workspace_warning",
                workspace_id=workspace_id,
                utilization=round(utilization, 4),
                api_cost=round(ws.budget.api_cost, 4),
            )
        return False, ""

    def budget_summary(self, workspace_id: str) -> dict[str, Any]:
        """Return operator-legible budget summary for a workspace."""
        ws = self._projections.workspaces.get(workspace_id)
        if ws is None:
            return {"error": "workspace_not_found"}
        utilization = (
            ws.budget.total_cost / ws.budget_limit
            if ws.budget_limit > 0 else 0.0
        )
        colony_budgets: list[dict[str, Any]] = []
        for colony in self._projections.workspace_colonies(workspace_id):
            colony_budgets.append({
                "colony_id": colony.id,
                "status": colony.status,
                "cost": round(colony.budget_truth.total_cost, 4),
                "budget_limit": colony.budget_limit,
                "tokens": colony.budget_truth.total_tokens,
                "model_usage": dict(colony.budget_truth.model_usage),
            })
        return {
            "workspace_id": workspace_id,
            "total_cost": round(ws.budget.total_cost, 4),
            "budget_limit": ws.budget_limit,
            "utilization": round(utilization, 4),
            "warning_issued": ws.budget.warning_issued,
            "downgrade_active": ws.budget.downgrade_active,
            "total_input_tokens": ws.budget.total_input_tokens,
            "total_output_tokens": ws.budget.total_output_tokens,
            "total_reasoning_tokens": ws.budget.total_reasoning_tokens,
            "total_cache_read_tokens": ws.budget.total_cache_read_tokens,
            "model_usage": dict(ws.budget.model_usage),
            "colonies": colony_budgets,
        }


__all__ = ["BudgetEnforcer", "LLMRouter", "Runtime"]
