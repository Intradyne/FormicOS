"""
FormicOS v0.6.0 -- Model Registry

Maps model IDs to AsyncOpenAI client instances.  Resolves subcaste tiers
to concrete model assignments.  Tracks VRAM budgets and model health.

Each agent references a model_id (e.g. 'local/qwen3-30b') which the
registry maps to a concrete backend endpoint and protocol.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from typing import Any

import aiohttp
import httpx
from openai import AsyncOpenAI

from .llm_client import AioLLMClient, LLMClient
from .models import (
    FormicOSConfig,
    ModelBackendType,
    ModelRegistryEntry,
    SubcasteMapEntry,
    SubcasteTier,
)

logger = logging.getLogger(__name__)

# ── Result dataclasses ──────────────────────────────────────────────────


@dataclass(frozen=True)
class SubcasteResolution:
    """Resolved subcaste tier → concrete clients and model strings."""

    primary_client: LLMClient
    primary_model: str
    refine_client: LLMClient | None = None
    refine_model: str | None = None


# ── Circuit Breaker (v0.7.3) ──────────────────────────────────────────


class CircuitState:
    """Circuit breaker states."""
    CLOSED = "closed"        # normal: probes pass through
    OPEN = "open"            # fail-fast: no probes
    HALF_OPEN = "half_open"  # single probe attempt


@dataclass
class CircuitBreaker:
    """Three-state circuit breaker for model health checks.

    CLOSED → OPEN after ``failure_threshold`` consecutive failures.
    OPEN → HALF_OPEN after ``cooldown_seconds`` elapse.
    HALF_OPEN → CLOSED on success, or back to OPEN on failure.
    """

    failure_threshold: int = 3
    cooldown_seconds: float = 60.0
    probe_timeout: float = 5.0

    state: str = CircuitState.CLOSED
    failure_count: int = 0
    last_failure_at: float = 0.0
    last_success_at: float = 0.0
    last_latency_ms: float = 0.0
    last_healthy: bool | None = None
    _time_func: Any = None  # injectable for tests

    def _now(self) -> float:
        return (self._time_func or time.monotonic)()

    def record_success(self, latency_ms: float) -> None:
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_success_at = self._now()
        self.last_latency_ms = latency_ms
        self.last_healthy = True

    def record_failure(self) -> None:
        self.failure_count += 1
        self.last_failure_at = self._now()
        self.last_healthy = False
        if self.failure_count >= self.failure_threshold:
            self.state = CircuitState.OPEN

    def should_probe(self) -> bool:
        """Return True if a health probe should be attempted."""
        if self.state == CircuitState.CLOSED:
            return True
        if self.state == CircuitState.OPEN:
            if self._now() - self.last_failure_at >= self.cooldown_seconds:
                self.state = CircuitState.HALF_OPEN
                return True
            return False
        # HALF_OPEN: allow exactly one probe
        return True


# ── ModelRegistry ───────────────────────────────────────────────────────


class ModelRegistry:
    """
    Registry of available LLM backends.

    Constructed from a validated :class:`FormicOSConfig`; entries are
    immutable after init.  Clients are lazily created on first access
    and cached for the lifetime of the registry.
    """

    def __init__(
        self,
        config: FormicOSConfig,
        aio_session: aiohttp.ClientSession | None = None,
    ) -> None:
        self._config = config
        self._aio_session = aio_session
        self._entries: dict[str, ModelRegistryEntry] = {}
        self._clients: dict[str, tuple[LLMClient, str]] = {}
        self._breakers: dict[str, CircuitBreaker] = {}

        # Populate entries from the validated config
        for model_id, entry in config.model_registry.items():
            # Backfill model_id onto the entry so callers can read it
            if not entry.model_id:
                entry = entry.model_copy(update={"model_id": model_id})
            self._entries[model_id] = entry

        logger.info(
            "Model registry loaded: %d models", len(self._entries)
        )

    # ── Public API ──────────────────────────────────────────────────

    def get_entry(self, model_id: str) -> ModelRegistryEntry:
        """Look up a model entry.

        Raises:
            KeyError: If *model_id* is not registered.  The error message
                includes the list of known model IDs.
        """
        if model_id not in self._entries:
            known = ", ".join(sorted(self._entries.keys())) or "(none)"
            raise KeyError(
                f"Model not found in registry: {model_id!r}. "
                f"Registered models: {known}"
            )
        return self._entries[model_id]

    def get_client(self, model_id: str) -> tuple[LLMClient, str]:
        """Return ``(LLMClient, model_string)`` for *model_id*.

        Clients are cached -- the same *model_id* always returns the
        same client instance.  When an ``aio_session`` was provided at
        construction, returns an ``AioLLMClient``; otherwise falls back
        to ``AsyncOpenAI``.

        Raises:
            KeyError: Unknown *model_id*.
            ValueError: Backend requires an endpoint but none is configured.
            RuntimeError: Anthropic backend requested without API key.
        """
        if model_id in self._clients:
            return self._clients[model_id]

        entry = self.get_entry(model_id)
        client, model_string = self._create_client(model_id, entry)
        self._clients[model_id] = (client, model_string)
        return client, model_string

    def get_cached_clients(self) -> dict[str, LLMClient]:
        """Return a dict of model_id → client for all cached (already-created) clients."""
        return {mid: client for mid, (client, _) in self._clients.items()}

    def has_model(self, model_id: str) -> bool:
        """Check whether *model_id* exists in the registry."""
        return model_id in self._entries

    def list_models(self) -> dict[str, dict[str, Any]]:
        """Return all models with status info (suitable for ``/api/models``).

        Includes circuit breaker state when available; otherwise ``status``
        defaults to ``"unknown"``.
        """
        result: dict[str, dict[str, Any]] = {}
        for model_id, entry in self._entries.items():
            breaker = self._breakers.get(model_id)
            if breaker is not None and breaker.last_healthy is not None:
                status = "healthy" if breaker.last_healthy else "unhealthy"
            else:
                status = "unknown"

            result[model_id] = {
                "type": entry.type,
                "backend": entry.backend.value,
                "endpoint": entry.endpoint,
                "model_string": entry.model_string,
                "context_length": entry.context_length,
                "vram_gb": entry.vram_gb,
                "supports_tools": entry.supports_tools,
                "supports_streaming": entry.supports_streaming,
                "requires_approval": entry.requires_approval,
                "status": status,
                "circuit_state": breaker.state if breaker else "unknown",
            }
        return result

    def get_vram_budget(self) -> dict[str, Any]:
        """Compute advisory VRAM budget from local model entries.

        Returns a dict with ``total_vram``, ``allocated``, and
        ``available`` (based on ``hardware.vram_gb`` from config).
        """
        allocated = 0.0
        per_model: list[dict[str, Any]] = []

        for model_id, entry in self._entries.items():
            if entry.backend in (
                ModelBackendType.LLAMA_CPP,
                ModelBackendType.OLLAMA,
            ) and entry.vram_gb:
                per_model.append({
                    "model_id": model_id,
                    "vram_gb": entry.vram_gb,
                })
                allocated += entry.vram_gb

        total_vram = self._config.hardware.vram_gb
        available = max(0.0, total_vram - allocated)

        if allocated > total_vram:
            logger.warning(
                "VRAM over-committed: %.1f GB allocated across %d models, "
                "but only %.1f GB total GPU VRAM declared",
                allocated,
                len(per_model),
                total_vram,
            )

        return {
            "total_vram": round(total_vram, 2),
            "allocated": round(allocated, 2),
            "available": round(available, 2),
            "models": per_model,
        }

    async def resolve_subcaste(
        self,
        tier: SubcasteTier,
        subcaste_map: dict[str, SubcasteMapEntry],
    ) -> SubcasteResolution:
        """Resolve a subcaste *tier* to client(s) + model string(s).

        Resolution chain:
        1. Look up ``tier.value`` in *subcaste_map*.
        2. Resolve the ``primary`` model_id via :meth:`get_client`.
        3. If ``refine_with`` is set, resolve that too.

        Raises:
            KeyError: If the tier is not present in *subcaste_map*, or
                a referenced model_id is not registered.
        """
        tier_key = tier.value
        if tier_key not in subcaste_map:
            known = ", ".join(sorted(subcaste_map.keys())) or "(none)"
            raise KeyError(
                f"Subcaste tier {tier_key!r} not found in subcaste_map. "
                f"Available tiers: {known}"
            )

        entry = subcaste_map[tier_key]
        # Allow both SubcasteMapEntry and raw dict
        if isinstance(entry, dict):
            entry = SubcasteMapEntry(**entry)

        primary_client, primary_model = self.get_client(entry.primary)

        refine_client: LLMClient | None = None
        refine_model: str | None = None
        if entry.refine_with is not None:
            refine_client, refine_model = self.get_client(entry.refine_with)

        return SubcasteResolution(
            primary_client=primary_client,
            primary_model=primary_model,
            refine_client=refine_client,
            refine_model=refine_model,
        )

    async def health_check(self, model_id: str) -> dict[str, Any]:
        """Async health ping for a model endpoint.

        Uses a circuit breaker (v0.7.3) instead of fixed TTL cache:
        - CLOSED: probes pass through normally.
        - OPEN: fail-fast, no probe calls until cooldown elapses.
        - HALF_OPEN: single probe attempt; success → CLOSED, failure → OPEN.

        Returns a dict with ``healthy``, ``latency_ms``, and ``circuit_state``.

        Raises:
            KeyError: Unknown *model_id*.
        """
        entry = self.get_entry(model_id)

        # Get or create circuit breaker for this model
        breaker = self._breakers.get(model_id)
        if breaker is None:
            breaker = CircuitBreaker()
            self._breakers[model_id] = breaker

        # Circuit open → fail-fast
        if not breaker.should_probe():
            return {
                "healthy": False,
                "latency_ms": 0.0,
                "circuit_state": breaker.state,
            }

        # Actually probe the endpoint
        healthy = False
        latency_ms = 0.0

        if entry.endpoint:
            # Strip /v1 suffix for the health ping — most servers expose
            # health at the root or /health, not under /v1.
            base = entry.endpoint.rstrip("/")
            if base.endswith("/v1"):
                base = base[:-3]
            health_url = f"{base}/health"

            t0 = time.monotonic()
            try:
                async with httpx.AsyncClient(timeout=breaker.probe_timeout) as http:
                    resp = await http.get(health_url)
                    healthy = resp.status_code < 500
            except Exception:
                healthy = False
            latency_ms = round((time.monotonic() - t0) * 1000, 2)
        else:
            # No endpoint (e.g. anthropic_api uses cloud) — assume healthy
            # if we can construct the client without error.
            try:
                self.get_client(model_id)
                healthy = True
            except Exception:
                healthy = False

        if healthy:
            breaker.record_success(latency_ms)
        else:
            breaker.record_failure()

        return {
            "healthy": healthy,
            "latency_ms": latency_ms,
            "circuit_state": breaker.state,
        }

    @property
    def model_ids(self) -> list[str]:
        """All registered model IDs."""
        return list(self._entries.keys())

    # ── Internal: client factory ────────────────────────────────────

    def _create_client(
        self, model_id: str, entry: ModelRegistryEntry
    ) -> tuple[LLMClient, str]:
        """Create a fresh LLM client for the given entry.

        When ``self._aio_session`` is available, creates an
        ``AioLLMClient`` backed by the shared aiohttp connection pool.
        Otherwise falls back to ``AsyncOpenAI`` (httpx-based).
        """
        timeout = self._config.inference.timeout_seconds

        if entry.backend == ModelBackendType.LLAMA_CPP:
            if not entry.endpoint:
                raise ValueError(
                    f"llama_cpp backend {model_id!r} requires an endpoint"
                )
            client: LLMClient = self._make_client(
                entry.endpoint, "not-needed", timeout,
            )
            model_string = entry.model_string or "local-model"

        elif entry.backend == ModelBackendType.OPENAI_COMPATIBLE:
            if not entry.endpoint:
                raise ValueError(
                    f"openai_compatible backend {model_id!r} requires an endpoint"
                )
            api_key = os.environ.get("OPENAI_COMPATIBLE_API_KEY", "not-needed")
            client = self._make_client(entry.endpoint, api_key, timeout)
            model_string = entry.model_string or "default"

        elif entry.backend == ModelBackendType.OLLAMA:
            endpoint = entry.endpoint or "http://localhost:11434/v1"
            client = self._make_client(endpoint, "not-needed", timeout)
            model_string = entry.model_string or "local-model"

        elif entry.backend == ModelBackendType.ANTHROPIC_API:
            api_key = os.environ.get("ANTHROPIC_API_KEY")
            if not api_key:
                raise RuntimeError(
                    f"Anthropic backend {model_id!r} requires the "
                    "ANTHROPIC_API_KEY environment variable to be set. "
                    "Please set it and restart."
                )
            # Anthropic models can be accessed via their OpenAI-compatible
            # proxy or the native SDK.  Here we use the OpenAI-compatible
            # shim so the rest of the pipeline stays uniform.
            endpoint = entry.endpoint or "https://api.anthropic.com/v1"
            client = self._make_client(endpoint, api_key, timeout)
            model_string = entry.model_string or entry.model_id or model_id

        else:
            raise ValueError(f"Unknown backend type: {entry.backend!r}")

        return client, model_string

    def _make_client(
        self, base_url: str, api_key: str, timeout: float
    ) -> LLMClient:
        """Build either an AioLLMClient or AsyncOpenAI based on session availability."""
        if self._aio_session is not None:
            return AioLLMClient(
                session=self._aio_session,
                base_url=base_url,
                api_key=api_key,
                timeout=timeout,
            )
        return AsyncOpenAI(
            base_url=base_url,
            api_key=api_key,
            timeout=timeout,
        )
