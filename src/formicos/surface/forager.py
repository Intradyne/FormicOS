"""Forager orchestration for bounded web-knowledge acquisition (Wave 44).

Coordinates the search → filter → chunk → dedup → admit → write cycle.
Consumes Team 1's substrate (EgressGateway, fetch pipeline) and Team 3's
event definitions (ForageRequested, ForageCycleCompleted). Until those
land, the forager operates with protocol interfaces and structlog audit.

The forager does NOT perform network I/O inline in retrieval.
It receives ``ForageRequest`` signals and runs the acquisition cycle
as a bounded background workflow.

Key design rules:
  - Query formation is deterministic (no LLM rewriting).
  - Web content starts with conservative priors (ephemeral decay, candidate status).
  - Admitted entries reuse ``MemoryEntryCreated`` — no parallel lifecycle.
  - Provenance metadata (source_url, fetch_timestamp, etc.) is embedded in the entry dict.
  - Exact-hash deduplication prevents repeated content.
"""

from __future__ import annotations

import hashlib
import re
import time as _time_mod
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol, runtime_checkable

import structlog

from formicos.surface.admission import AdmissionResult, evaluate_entry

log = structlog.get_logger()


# ---------------------------------------------------------------------------
# Forage request / result types
# ---------------------------------------------------------------------------


@dataclass
class ForageRequest:
    """Signal requesting a forage cycle — the handoff contract.

    Created by retrieval (reactive trigger) or proactive intelligence.
    Consumed by the forager orchestrator. Never performs I/O itself.
    """

    workspace_id: str
    trigger: str  # "reactive", "proactive:confidence_decline", "proactive:coverage_gap", etc.
    gap_description: str  # human-readable reason
    domains: list[str] = field(default_factory=lambda: list[str]())
    topic: str = ""  # primary search topic
    context: str = ""  # additional context for query formation
    colony_id: str = ""  # source colony that triggered this
    thread_id: str = ""
    max_results: int = 5
    budget_limit: float = 0.50  # cost cap for this cycle


@dataclass
class ForageCycleResult:
    """Summary of a completed forage cycle."""

    request: ForageRequest
    queries_executed: list[str] = field(default_factory=lambda: list[str]())
    urls_fetched: int = 0
    chunks_produced: int = 0
    duplicates_skipped: int = 0
    entries_admitted: int = 0
    entries_rejected: int = 0
    admitted_entry_ids: list[str] = field(default_factory=lambda: list[str]())
    duration_ms: int = 0
    error: str = ""


# ---------------------------------------------------------------------------
# Deterministic query templates (Pillar 2B)
# ---------------------------------------------------------------------------


# Template keys match trigger types and gap signals from proactive_intelligence.
_QUERY_TEMPLATES: dict[str, str] = {
    # Reactive trigger: low-confidence retrieval
    "reactive": "{topic} {context}",
    # Proactive: stale entry needs refresh
    "proactive:confidence_decline": "{topic} latest {year}",
    # Proactive: prediction errors suggest knowledge is wrong
    "proactive:prediction_error": "{topic} {context} correct approach",
    # Proactive: cluster of stale entries
    "proactive:stale_cluster": "{topic} reference guide {year}",
    # Proactive: coverage gap in a domain
    "proactive:coverage_gap": "{topic} how to {context}",
    # Proactive: low knowledge ROI
    "proactive:knowledge_roi": "{topic} best practices tutorial",
    # Default fallback
    "default": "{topic} {context}",
}


def build_query(request: ForageRequest) -> str:
    """Build a deterministic search query from a forage request.

    No LLM rewriting — just template expansion with cleanup.
    """
    template = _QUERY_TEMPLATES.get(
        request.trigger,
        _QUERY_TEMPLATES["default"],
    )
    year = str(datetime.now(UTC).year)
    topic = request.topic or " ".join(request.domains[:3])
    context = request.context or ""

    query = template.format(
        topic=topic,
        context=context,
        year=year,
    )
    # Collapse whitespace and trim
    query = re.sub(r"\s+", " ", query).strip()
    # Cap length to avoid overly long queries
    if len(query) > 200:
        query = query[:200].rsplit(" ", 1)[0]
    return query


# ---------------------------------------------------------------------------
# Source credibility tiers (Wave 45 — provenance signal, not content quality)
# ---------------------------------------------------------------------------

# Tier 1: authoritative documentation — highest trust
# Tier 2: educational/government — high trust
# Tier 3: curated community — moderate trust
# Tier 4: general web content — baseline trust
# Tier 5: unknown / unclassified — conservative trust

CREDIBILITY_T1 = 1.0   # docs.python.org, docs.rust-lang.org, etc.
CREDIBILITY_T2 = 0.85  # .edu, .gov, arXiv, RFC
CREDIBILITY_T3 = 0.65  # stackoverflow.com, github.com, wikipedia.org
CREDIBILITY_T4 = 0.45  # medium.com, dev.to, general blogs
CREDIBILITY_T5 = 0.30  # unknown domains

# Domain → tier mapping. Checked via exact match and suffix match.
_DOMAIN_TIER_MAP: dict[str, float] = {
    # Tier 1: official documentation
    "docs.python.org": CREDIBILITY_T1,
    "docs.rust-lang.org": CREDIBILITY_T1,
    "doc.rust-lang.org": CREDIBILITY_T1,
    "devdocs.io": CREDIBILITY_T1,
    "developer.mozilla.org": CREDIBILITY_T1,
    "learn.microsoft.com": CREDIBILITY_T1,
    "cloud.google.com": CREDIBILITY_T1,
    "docs.aws.amazon.com": CREDIBILITY_T1,
    "kubernetes.io": CREDIBILITY_T1,
    "docs.docker.com": CREDIBILITY_T1,
    "nodejs.org": CREDIBILITY_T1,
    "go.dev": CREDIBILITY_T1,
    "docs.oracle.com": CREDIBILITY_T1,
    "react.dev": CREDIBILITY_T1,
    "vuejs.org": CREDIBILITY_T1,
    "angular.dev": CREDIBILITY_T1,
    "docs.djangoproject.com": CREDIBILITY_T1,
    "flask.palletsprojects.com": CREDIBILITY_T1,
    "fastapi.tiangolo.com": CREDIBILITY_T1,
    # Tier 3: curated community
    "stackoverflow.com": CREDIBILITY_T3,
    "github.com": CREDIBILITY_T3,
    "wikipedia.org": CREDIBILITY_T3,
    "en.wikipedia.org": CREDIBILITY_T3,
    "arxiv.org": CREDIBILITY_T2,
    "datatracker.ietf.org": CREDIBILITY_T2,
    # Tier 4: general blogs / platforms
    "medium.com": CREDIBILITY_T4,
    "dev.to": CREDIBILITY_T4,
    "substack.com": CREDIBILITY_T4,
    "hashnode.dev": CREDIBILITY_T4,
    "towardsdatascience.com": CREDIBILITY_T4,
    "freecodecamp.org": CREDIBILITY_T3,
}

# TLD-based fallback tiers
_TLD_TIER_MAP: dict[str, float] = {
    ".edu": CREDIBILITY_T2,
    ".gov": CREDIBILITY_T2,
    ".ac.uk": CREDIBILITY_T2,
    ".gov.uk": CREDIBILITY_T2,
}


def get_source_credibility(domain: str) -> float:
    """Return credibility score for a domain.

    Checks exact match, then suffix match against known domains,
    then TLD-based fallback, then returns T5 (unknown).
    """
    domain = domain.lower().strip()
    if not domain:
        return CREDIBILITY_T5

    # Exact match
    if domain in _DOMAIN_TIER_MAP:
        return _DOMAIN_TIER_MAP[domain]

    # Suffix match (e.g., "api.docs.python.org" → docs.python.org)
    for known_domain, tier in _DOMAIN_TIER_MAP.items():
        if domain.endswith(f".{known_domain}"):
            return tier

    # TLD-based fallback
    for tld, tier in _TLD_TIER_MAP.items():
        if domain.endswith(tld):
            return tier

    return CREDIBILITY_T5


# ---------------------------------------------------------------------------
# Content chunking (Pillar 3A)
# ---------------------------------------------------------------------------


_CHUNK_SIZE = 1500  # characters per chunk
_CHUNK_OVERLAP = 200  # overlap between chunks


def chunk_content(
    text: str,
    *,
    chunk_size: int = _CHUNK_SIZE,
    overlap: int = _CHUNK_OVERLAP,
) -> list[str]:
    """Bounded recursive chunking with overlap.

    Splits on paragraph boundaries first, then sentence boundaries,
    then falls back to character splitting. Keeps the first version
    practical and cheap.
    """
    if not text or not text.strip():
        return []
    text = text.strip()
    if len(text) <= chunk_size:
        return [text]

    # Try paragraph splitting first
    paragraphs = re.split(r"\n\s*\n", text)
    if len(paragraphs) > 1:
        return _merge_segments(paragraphs, chunk_size, overlap)

    # Try sentence splitting
    sentences = re.split(r"(?<=[.!?])\s+", text)
    if len(sentences) > 1:
        return _merge_segments(sentences, chunk_size, overlap)

    # Character-level fallback
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunks.append(text[start:end])
        if end >= len(text):
            break
        start = end - overlap
    return chunks


def _merge_segments(
    segments: list[str],
    chunk_size: int,
    overlap: int,
) -> list[str]:
    """Merge small segments into chunks respecting size limits."""
    chunks: list[str] = []
    current = ""
    for seg in segments:
        seg = seg.strip()
        if not seg:
            continue
        candidate = f"{current}\n\n{seg}" if current else seg
        if len(candidate) > chunk_size and current:
            chunks.append(current.strip())
            # Keep overlap from end of previous chunk
            if overlap > 0 and len(current) > overlap:
                current = current[-overlap:] + "\n\n" + seg
            else:
                current = seg
        else:
            current = candidate
    if current.strip():
        chunks.append(current.strip())
    return chunks


# ---------------------------------------------------------------------------
# Exact-hash deduplication (Pillar 3B)
# ---------------------------------------------------------------------------


def content_hash(text: str) -> str:
    """SHA-256 hash of normalized text for exact deduplication."""
    normalized = re.sub(r"\s+", " ", text.strip().lower())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def deduplicate_chunks(
    chunks: list[str],
    existing_hashes: set[str] | None = None,
) -> tuple[list[str], int]:
    """Remove exact duplicates from chunks.

    Returns (unique_chunks, duplicates_skipped).
    """
    if existing_hashes is None:
        existing_hashes = set()
    unique: list[str] = []
    skipped = 0
    seen = set(existing_hashes)
    for chunk in chunks:
        h = content_hash(chunk)
        if h in seen:
            skipped += 1
        else:
            seen.add(h)
            unique.append(chunk)
    return unique, skipped


# ---------------------------------------------------------------------------
# Entry preparation + admission bridge (Pillar 3C/3D)
# ---------------------------------------------------------------------------


def prepare_forager_entry(
    chunk: str,
    *,
    source_url: str,
    title: str,
    workspace_id: str,
    thread_id: str = "",
    colony_id: str = "",
    domains: list[str] | None = None,
    trigger: str = "",
    query: str = "",
    quality_score: float = 0.5,
    fetch_level: str = "level_1",
) -> dict[str, Any]:
    """Prepare a candidate entry dict from forager-fetched content.

    Maps forager output into the existing MemoryEntry shape with
    conservative priors and auditable provenance metadata.
    """
    now_iso = datetime.now(UTC).isoformat()
    entry_id = f"mem-forager-{content_hash(chunk)[:12]}"

    # Source credibility tier (Wave 45) — provenance signal
    source_domain = _extract_domain(source_url)
    credibility = get_source_credibility(source_domain)

    return {
        "id": entry_id,
        "entry_type": "experience",
        "sub_type": "learning",
        "status": "candidate",
        "polarity": "positive",
        "title": _truncate(title, 120),
        "content": chunk,
        "summary": _truncate(chunk, 100),
        "source_colony_id": colony_id or "forager",
        "source_artifact_ids": [],
        "source_round": 0,
        "source_agent": "forager",
        "source_peer": "",
        "domains": domains or [],
        "tool_refs": [],
        "confidence": 0.5,  # conservative starting confidence
        "scan_status": "pending",
        "created_at": now_iso,
        "workspace_id": workspace_id,
        "thread_id": thread_id,
        # Conservative Bayesian priors — web content must earn trust
        "conf_alpha": 5.0,
        "conf_beta": 5.0,
        "decay_class": "ephemeral",  # web content decays fast
        # Forager provenance metadata (Pillar 3D)
        "forager_provenance": {
            "source_url": source_url,
            "source_domain": source_domain,
            "source_credibility": credibility,
            "fetch_timestamp": now_iso,
            "fetch_level": fetch_level,
            "forager_trigger": trigger,
            "forager_query": query,
            "quality_score": quality_score,
        },
    }


def score_forager_entry(entry: dict[str, Any]) -> AdmissionResult:
    """Score a forager-prepared entry through the existing admission pipeline.

    Uses the standard seven-dimension admission scoring. No special
    treatment — web content must clear the same gate as colony output.
    """
    return evaluate_entry(entry)


# ---------------------------------------------------------------------------
# Domain controls (Pillar 4C)
# ---------------------------------------------------------------------------


@dataclass
class DomainPolicy:
    """Operator-controlled domain trust policy."""

    trusted: set[str] = field(default_factory=lambda: set[str]())
    distrusted: set[str] = field(default_factory=lambda: set[str]())

    def is_allowed(self, domain: str) -> bool:
        """Check if a domain is allowed for fetching.

        Distrusted domains are always blocked. If a trust list exists,
        only trusted domains are allowed. Otherwise, all non-distrusted
        domains are allowed.
        """
        domain = domain.lower().strip()
        if domain in self.distrusted:
            return False
        if self.trusted:
            return domain in self.trusted
        return True

    def trust(self, domain: str) -> None:
        domain = domain.lower().strip()
        self.trusted.add(domain)
        self.distrusted.discard(domain)

    def distrust(self, domain: str) -> None:
        domain = domain.lower().strip()
        self.distrusted.add(domain)
        self.trusted.discard(domain)

    def reset(self, domain: str) -> None:
        domain = domain.lower().strip()
        self.trusted.discard(domain)
        self.distrusted.discard(domain)


# ---------------------------------------------------------------------------
# Fetch protocol (consumed from Team 1's substrate)
# ---------------------------------------------------------------------------


@runtime_checkable
class FetchPort(Protocol):
    """Protocol for content fetching — Team 1 implements the real adapter."""

    async def fetch(self, url: str) -> FetchResult: ...


@dataclass
class FetchResult:
    """Result of fetching a URL."""

    url: str
    text: str = ""
    title: str = ""
    content_type: str = ""
    quality_score: float = 0.5
    fetch_level: str = "level_1"
    error: str = ""

    @property
    def ok(self) -> bool:
        return bool(self.text) and not self.error


# ---------------------------------------------------------------------------
# Forage cycle orchestrator (Pillar 4)
# ---------------------------------------------------------------------------


class ForagerOrchestrator:
    """Runs a bounded forage cycle: search → filter → fetch → chunk → admit.

    This is the main surface-layer coordination path for Wave 44 Team 2.
    It consumes Team 1's fetch substrate and Team 3's event definitions.
    """

    def __init__(
        self,
        *,
        search_adapter: Any,  # WebSearchAdapter from adapters.web_search
        fetch_port: FetchPort | None = None,
        domain_policy: DomainPolicy | None = None,
        existing_hashes: set[str] | None = None,
        search_http_client: Any = None,  # httpx.AsyncClient for search requests
    ) -> None:
        self._search = search_adapter
        self._fetch = fetch_port
        self._domain_policy = domain_policy or DomainPolicy()
        self._existing_hashes = existing_hashes or set()
        self._search_http_client = search_http_client

    async def execute(self, request: ForageRequest) -> ForageCycleResult:
        """Execute a bounded forage cycle.

        Returns a summary of what was found, fetched, and admitted.
        Does NOT emit events directly — the caller (colony_manager or
        runtime) is responsible for event emission.
        """
        start = _time_mod.monotonic()
        result = ForageCycleResult(request=request)

        try:
            # Step 1: Build deterministic query
            query = build_query(request)
            result.queries_executed.append(query)

            # Step 2: Search
            from formicos.adapters.web_search import filter_results  # noqa: PLC0415

            search_resp = await self._search.search(
                query, max_results=request.max_results,
                http_client=self._search_http_client,
            )
            if search_resp.error:
                result.error = f"search_failed: {search_resp.error}"
                return result

            # Step 3: Pre-fetch relevance filter
            filtered = filter_results(search_resp.results, query)
            if not filtered:
                log.info("forager.no_relevant_results", query=query[:80])
                return result

            # Step 4: Domain policy filter
            allowed = [
                r for r in filtered
                if self._domain_policy.is_allowed(_extract_domain(r.url))
            ]
            if not allowed:
                log.info("forager.all_results_blocked_by_domain_policy")
                return result

            # Step 5: Fetch content (if fetch port available)
            if self._fetch is None:
                # No fetch substrate yet (Team 1 hasn't landed).
                # Record what we would have fetched for audit.
                log.info(
                    "forager.fetch_skipped_no_substrate",
                    urls=[r.url for r in allowed[:3]],
                )
                result.urls_fetched = 0
                return result

            entries_to_admit: list[dict[str, Any]] = []

            for search_result in allowed:
                fetch_result = await self._fetch.fetch(search_result.url)
                if not fetch_result.ok:
                    continue
                result.urls_fetched += 1

                # Step 6: Chunk content
                chunks = chunk_content(fetch_result.text)
                result.chunks_produced += len(chunks)

                # Step 7: Deduplicate
                unique, skipped = deduplicate_chunks(
                    chunks, self._existing_hashes,
                )
                result.duplicates_skipped += skipped

                # Step 8: Prepare and score entries
                for chunk in unique:
                    entry = prepare_forager_entry(
                        chunk,
                        source_url=search_result.url,
                        title=fetch_result.title or search_result.title,
                        workspace_id=request.workspace_id,
                        thread_id=request.thread_id,
                        colony_id=request.colony_id,
                        domains=request.domains,
                        trigger=request.trigger,
                        query=query,
                        quality_score=fetch_result.quality_score,
                        fetch_level=fetch_result.fetch_level,
                    )
                    admission = score_forager_entry(entry)
                    if admission.admitted:
                        entries_to_admit.append(entry)
                        result.entries_admitted += 1
                        result.admitted_entry_ids.append(entry["id"])
                        # Track hash to prevent future duplicates
                        self._existing_hashes.add(content_hash(chunk))
                    else:
                        result.entries_rejected += 1
                        log.debug(
                            "forager.entry_rejected",
                            score=admission.score,
                            rationale=admission.rationale,
                        )

        except Exception as exc:  # noqa: BLE001
            result.error = str(exc)
            log.warning("forager.cycle_failed", error=str(exc))
        finally:
            result.duration_ms = int(
                (_time_mod.monotonic() - start) * 1000,
            )

        log.info(
            "forager.cycle_completed",
            workspace_id=request.workspace_id,
            trigger=request.trigger,
            queries=len(result.queries_executed),
            fetched=result.urls_fetched,
            admitted=result.entries_admitted,
            rejected=result.entries_rejected,
            duration_ms=result.duration_ms,
        )
        return result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_domain(url: str) -> str:
    """Extract domain from a URL."""
    # Simple extraction — handles http(s)://domain.com/path
    match = re.match(r"https?://([^/]+)", url)
    return match.group(1).lower() if match else ""


def _truncate(text: str, max_len: int) -> str:
    """Truncate text to max_len, adding ellipsis if needed."""
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


# ---------------------------------------------------------------------------
# ForagerFetchAdapter — bridges FetchPort to Team 1 substrate (Wave 44)
# ---------------------------------------------------------------------------


class ForagerFetchAdapter:
    """Adapts Team 1's EgressGateway + FetchPipeline into the FetchPort protocol.

    This is the concrete bridge that lets ForagerOrchestrator consume
    the bounded egress + graduated extraction substrate without coupling
    the orchestrator directly to adapter-layer classes.
    """

    def __init__(
        self,
        fetch_pipeline: Any,  # adapters.fetch_pipeline.FetchPipeline
        content_quality_fn: Any = None,  # adapters.content_quality.score_content
    ) -> None:
        self._pipeline = fetch_pipeline
        self._quality_fn = content_quality_fn

    async def fetch(self, url: str) -> FetchResult:
        """Fetch a URL through the bounded egress + extraction pipeline."""
        from formicos.adapters.egress_gateway import FetchOrigin  # noqa: PLC0415

        try:
            extraction = await self._pipeline.extract(
                url, origin=FetchOrigin.SEARCH_RESULT,
            )
            if not extraction.success:
                return FetchResult(url=url, error=extraction.error or "extraction_failed")

            # Score content quality if scorer available
            quality_score = 0.5
            if self._quality_fn and extraction.text:
                qr = self._quality_fn(extraction.text)
                quality_score = qr.score

            return FetchResult(
                url=url,
                text=extraction.text,
                title="",  # extraction doesn't provide title
                content_type=extraction.content_type,
                quality_score=quality_score,
                fetch_level=f"level_{extraction.extraction_level}",
            )
        except Exception as exc:  # noqa: BLE001
            return FetchResult(url=url, error=str(exc))


# ---------------------------------------------------------------------------
# ForagerService — lifecycle owner, event emitter, signal consumer (Wave 44)
# ---------------------------------------------------------------------------


class ForagerService:
    """Surface-layer service that owns the forager lifecycle.

    Responsibilities:
    - Receives forage signals (reactive from retrieval, proactive from rules)
    - Emits ForageRequested / ForageCycleCompleted events
    - Writes admitted entries via MemoryEntryCreated
    - Emits DomainStrategyUpdated when strategies change
    - Runs forage cycles as bounded background tasks

    This is the integration seam that closes the Wave 44 loop.
    """

    def __init__(
        self,
        runtime: Any,  # surface.runtime.Runtime
        orchestrator: ForagerOrchestrator,
    ) -> None:
        self._runtime = runtime
        self._orchestrator = orchestrator
        self._running = False

    async def handle_forage_signal(
        self,
        signal: dict[str, Any],
    ) -> None:
        """Process a forage signal detected by retrieval or proactive rules.

        Emits ForageRequested, runs the cycle, emits ForageCycleCompleted,
        and writes admitted entries via MemoryEntryCreated.

        This is a fire-and-forget background task — errors are logged,
        never raised to the caller.
        """
        from formicos.core.events import (  # noqa: PLC0415
            ForageCycleCompleted,
            ForageRequested,
        )

        workspace_id = signal.get("workspace_id", "")
        if not workspace_id:
            log.warning("forager_service.missing_workspace_id")
            return

        # Build ForageRequest from signal
        request = ForageRequest(
            workspace_id=workspace_id,
            trigger=signal.get("trigger", "reactive"),
            gap_description=signal.get("gap_description", ""),
            domains=signal.get("domains", []),
            topic=signal.get("topic", ""),
            context=signal.get("context", ""),
            colony_id=signal.get("colony_id", ""),
            thread_id=signal.get("thread_id", ""),
            max_results=signal.get("max_results", 5),
        )

        # Map trigger to ForageModeName
        trigger = request.trigger
        if trigger.startswith("proactive"):
            mode = "proactive"
        elif trigger == "operator":
            mode = "operator"
        else:
            mode = "reactive"

        # Emit ForageRequested
        forage_event = ForageRequested(
            seq=0,
            timestamp=datetime.now(UTC),
            address=workspace_id,
            workspace_id=workspace_id,
            thread_id=request.thread_id,
            colony_id=request.colony_id,
            mode=mode,
            reason=request.gap_description,
            gap_domain=request.domains[0] if request.domains else "",
            gap_query=request.topic,
            max_results=request.max_results,
        )
        request_seq = await self._runtime.emit_and_broadcast(forage_event)

        # Run the cycle
        try:
            result = await self._orchestrator.execute(request)
        except Exception as exc:  # noqa: BLE001
            log.error("forager_service.cycle_error", error=str(exc))
            # Emit completion with error
            await self._runtime.emit_and_broadcast(ForageCycleCompleted(
                seq=0,
                timestamp=datetime.now(UTC),
                address=workspace_id,
                workspace_id=workspace_id,
                forage_request_seq=request_seq,
                error=str(exc),
            ))
            return

        # MemoryEntryCreated events are emitted in-cycle by
        # ForagerOrchestratorWithEmit as each entry clears admission.

        # Emit ForageCycleCompleted
        await self._runtime.emit_and_broadcast(ForageCycleCompleted(
            seq=0,
            timestamp=datetime.now(UTC),
            address=workspace_id,
            workspace_id=workspace_id,
            forage_request_seq=request_seq,
            queries_issued=len(result.queries_executed),
            pages_fetched=result.urls_fetched,
            pages_rejected=result.entries_rejected,
            entries_admitted=result.entries_admitted,
            entries_deduplicated=result.duplicates_skipped,
            duration_ms=result.duration_ms,
            error=result.error,
        ))

        # Emit domain strategy updates from the fetch pipeline
        await self._emit_domain_strategy_updates(workspace_id)

        log.info(
            "forager_service.cycle_complete",
            workspace_id=workspace_id,
            admitted=result.entries_admitted,
            rejected=result.entries_rejected,
            duration_ms=result.duration_ms,
        )

    async def _emit_domain_strategy_updates(
        self, workspace_id: str,
    ) -> None:
        """Emit DomainStrategyUpdated events for changed strategies."""
        from formicos.core.events import DomainStrategyUpdated  # noqa: PLC0415

        # Access the fetch pipeline's domain strategies if available
        fetch_adapter = self._orchestrator._fetch  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
        if fetch_adapter is None:
            return
        pipeline = getattr(fetch_adapter, "_pipeline", None)
        if pipeline is None:
            return
        strategies = getattr(pipeline, "domain_strategies", {})

        # Compare with projected state
        projected = self._runtime.projections.domain_strategies.get(workspace_id, {})

        for domain, strategy in strategies.items():
            existing = projected.get(domain)
            if existing is None or existing.preferred_level != strategy.preferred_level:
                await self._runtime.emit_and_broadcast(DomainStrategyUpdated(
                    seq=0,
                    timestamp=datetime.now(UTC),
                    address=workspace_id,
                    workspace_id=workspace_id,
                    domain=domain,
                    preferred_level=strategy.preferred_level,
                    success_count=strategy.success_count,
                    failure_count=strategy.failure_count,
                    reason="auto_learned",
                ))


# ---------------------------------------------------------------------------
# Modified orchestrator: emit MemoryEntryCreated for admitted entries
# ---------------------------------------------------------------------------


class ForagerOrchestratorWithEmit(ForagerOrchestrator):
    """Extended orchestrator that emits MemoryEntryCreated during the cycle.

    The base ForagerOrchestrator is caller-agnostic. This subclass
    injects the runtime's emit path so admitted entries are persisted
    as they are produced, not after the cycle completes.
    """

    def __init__(
        self,
        *,
        search_adapter: Any,
        fetch_port: FetchPort | None = None,
        domain_policy: DomainPolicy | None = None,
        existing_hashes: set[str] | None = None,
        search_http_client: Any = None,
        runtime: Any = None,  # surface.runtime.Runtime
    ) -> None:
        super().__init__(
            search_adapter=search_adapter,
            fetch_port=fetch_port,
            domain_policy=domain_policy,
            existing_hashes=existing_hashes,
            search_http_client=search_http_client,
        )
        self._runtime = runtime

    async def execute(self, request: ForageRequest) -> ForageCycleResult:
        """Execute cycle, emitting MemoryEntryCreated for each admitted entry."""
        from formicos.adapters.web_search import filter_results  # noqa: PLC0415
        from formicos.core.events import MemoryEntryCreated  # noqa: PLC0415

        start = _time_mod.monotonic()
        result = ForageCycleResult(request=request)

        try:
            query = build_query(request)
            result.queries_executed.append(query)

            search_resp = await self._search.search(
                query, max_results=request.max_results,
                http_client=self._search_http_client,
            )
            if search_resp.error:
                result.error = f"search_failed: {search_resp.error}"
                return result

            filtered = filter_results(search_resp.results, query)
            if not filtered:
                log.info("forager.no_relevant_results", query=query[:80])
                return result

            allowed = [
                r for r in filtered
                if self._domain_policy.is_allowed(_extract_domain(r.url))
            ]
            if not allowed:
                log.info("forager.all_results_blocked_by_domain_policy")
                return result

            if self._fetch is None:
                log.info(
                    "forager.fetch_skipped_no_substrate",
                    urls=[r.url for r in allowed[:3]],
                )
                return result

            for search_result in allowed:
                fetch_result = await self._fetch.fetch(search_result.url)
                if not fetch_result.ok:
                    continue
                result.urls_fetched += 1

                chunks = chunk_content(fetch_result.text)
                result.chunks_produced += len(chunks)

                unique, skipped = deduplicate_chunks(
                    chunks, self._existing_hashes,
                )
                result.duplicates_skipped += skipped

                for chunk in unique:
                    entry = prepare_forager_entry(
                        chunk,
                        source_url=search_result.url,
                        title=fetch_result.title or search_result.title,
                        workspace_id=request.workspace_id,
                        thread_id=request.thread_id,
                        colony_id=request.colony_id,
                        domains=request.domains,
                        trigger=request.trigger,
                        query=query,
                        quality_score=fetch_result.quality_score,
                        fetch_level=fetch_result.fetch_level,
                    )
                    admission = score_forager_entry(entry)
                    if admission.admitted:
                        # Emit MemoryEntryCreated immediately
                        if self._runtime is not None:
                            await self._runtime.emit_and_broadcast(
                                MemoryEntryCreated(
                                    seq=0,
                                    timestamp=datetime.now(UTC),
                                    address=request.workspace_id,
                                    workspace_id=request.workspace_id,
                                    entry=entry,
                                ),
                            )
                        result.entries_admitted += 1
                        result.admitted_entry_ids.append(entry["id"])
                        self._existing_hashes.add(content_hash(chunk))
                    else:
                        result.entries_rejected += 1
                        log.debug(
                            "forager.entry_rejected",
                            score=admission.score,
                            rationale=admission.rationale,
                        )

        except Exception as exc:  # noqa: BLE001
            result.error = str(exc)
            log.warning("forager.cycle_failed", error=str(exc))
        finally:
            result.duration_ms = int(
                (_time_mod.monotonic() - start) * 1000,
            )

        log.info(
            "forager.cycle_completed",
            workspace_id=request.workspace_id,
            trigger=request.trigger,
            queries=len(result.queries_executed),
            fetched=result.urls_fetched,
            admitted=result.entries_admitted,
            rejected=result.entries_rejected,
            duration_ms=result.duration_ms,
        )
        return result


__all__ = [
    "DomainPolicy",
    "FetchPort",
    "FetchResult",
    "ForageCycleResult",
    "ForageRequest",
    "ForagerFetchAdapter",
    "ForagerOrchestrator",
    "ForagerOrchestratorWithEmit",
    "ForagerService",
    "build_query",
    "chunk_content",
    "content_hash",
    "deduplicate_chunks",
    "get_source_credibility",
    "prepare_forager_entry",
    "score_forager_entry",
]
