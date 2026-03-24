# Wave 26 Algorithms -- Implementation Reference

**Wave:** 26 -- "Institutional Memory"
**Purpose:** Technical implementation guide for all three tracks.

---

## S1. Memory Entry Schema (Track 0 / Track A -- A1)

### New Types in core/types.py

```python
class MemoryEntryType(StrEnum):
    """Discriminator for institutional memory entries (Wave 26)."""
    skill = "skill"
    experience = "experience"


class MemoryEntryStatus(StrEnum):
    """Trust lifecycle for memory entries (Wave 26)."""
    candidate = "candidate"
    verified = "verified"
    rejected = "rejected"
    stale = "stale"


class MemoryEntryPolarity(StrEnum):
    """Outcome signal carried by a memory entry (Wave 26)."""
    positive = "positive"
    negative = "negative"
    neutral = "neutral"


class MemoryEntry(BaseModel):
    """Institutional memory entry -- skill or experience (Wave 26).

    Persisted as dicts on MemoryEntryCreated events for replay safety.
    The model is used for construction and validation.
    """
    model_config = FrozenConfig

    id: str = Field(description="Stable ID: mem-{colony_id}-{type[0]}-{index}")
    entry_type: MemoryEntryType = Field(description="skill or experience")
    status: MemoryEntryStatus = Field(default=MemoryEntryStatus.candidate)
    polarity: MemoryEntryPolarity = Field(default=MemoryEntryPolarity.positive)
    title: str = Field(description="Short descriptive title")
    content: str = Field(description="Full entry content -- the actionable knowledge")
    summary: str = Field(default="", description="One-line summary for search result display")
    source_colony_id: str = Field(description="Colony that produced this entry")
    source_artifact_ids: list[str] = Field(
        default_factory=list,
        description="Artifact IDs from which this entry was derived",
    )
    source_round: int = Field(default=0, description="Round number of source material")
    domains: list[str] = Field(default_factory=list, description="Domain tags")
    tool_refs: list[str] = Field(default_factory=list, description="Tool names referenced")
    confidence: float = Field(default=0.5, description="Initial confidence score")
    scan_status: str = Field(default="pending", description="Scanner result tier")
    created_at: str = Field(default="", description="ISO timestamp")
    workspace_id: str = Field(default="", description="Workspace scope")
```

---

## S2. Event Types (Track A -- A2)

### New Events in core/events.py

```python
class MemoryEntryCreated(EventEnvelope):
    """A new institutional memory entry was extracted and persisted (Wave 26)."""
    model_config = FrozenConfig

    type: Literal["MemoryEntryCreated"] = "MemoryEntryCreated"
    entry: dict[str, Any] = Field(
        ..., description="Serialized MemoryEntry dict. Source of truth for replay.",
    )
    workspace_id: str = Field(..., description="Workspace scope.")


class MemoryEntryStatusChanged(EventEnvelope):
    """An entry's trust status changed (Wave 26)."""
    model_config = FrozenConfig

    type: Literal["MemoryEntryStatusChanged"] = "MemoryEntryStatusChanged"
    entry_id: str = Field(..., description="Memory entry being updated.")
    old_status: str = Field(..., description="Previous status.")
    new_status: str = Field(..., description="New status.")
    reason: str = Field(default="", description="Why the status changed.")
    workspace_id: str = Field(..., description="Workspace scope.")
```

```python
class MemoryExtractionCompleted(EventEnvelope):
    """Memory extraction finished for a colony (even if zero entries produced).

    Durable receipt that extraction ran to completion. Without this,
    restart recovery cannot distinguish 'extraction crashed' from
    'extraction ran but found nothing to extract.'
    """
    model_config = FrozenConfig

    type: Literal["MemoryExtractionCompleted"] = "MemoryExtractionCompleted"
    colony_id: str = Field(..., description="Colony whose extraction finished.")
    entries_created: int = Field(..., ge=0, description="Number of MemoryEntryCreated events emitted.")
    workspace_id: str = Field(..., description="Workspace scope.")
```

### Union Update

Add all three to the `FormicOSEvent` union. Update count comment from 37 to 40.

```python
FormicOSEvent: TypeAlias = Annotated[
    Union[
        # ... existing 37 ...
        MemoryEntryCreated,          # Wave 26
        MemoryEntryStatusChanged,    # Wave 26
        MemoryExtractionCompleted,   # Wave 26
    ],
    Field(discriminator="type"),
]
```

---

## S3. Projection Handlers (Track A -- A3)

### In projections.py

```python
# Add to ProjectionStore.__init__:
self.memory_entries: dict[str, dict[str, Any]] = {}
self.memory_extractions_completed: set[str] = set()


def _on_memory_entry_created(store: ProjectionStore, event: FormicOSEvent) -> None:
    e: MemoryEntryCreated = event  # type: ignore[assignment]
    entry = e.entry
    entry_id = entry.get("id", "")
    if entry_id:
        store.memory_entries[entry_id] = dict(entry)
    # Qdrant sync is triggered by the caller (app lifespan or live event subscriber)
    # via memory_store.sync_entry(entry_id, store.memory_entries)
    # The projection handler itself does not call Qdrant -- it only updates in-memory state.


def _on_memory_entry_status_changed(store: ProjectionStore, event: FormicOSEvent) -> None:
    e: MemoryEntryStatusChanged = event  # type: ignore[assignment]
    entry = store.memory_entries.get(e.entry_id)
    if entry is not None:
        entry["status"] = e.new_status
    # After updating projection state, the caller triggers:
    # memory_store.sync_entry(e.entry_id, store.memory_entries)
    # This re-upserts the entry with the new status into Qdrant.


def _on_memory_extraction_completed(store: ProjectionStore, event: FormicOSEvent) -> None:
    e: MemoryExtractionCompleted = event  # type: ignore[assignment]
    store.memory_extractions_completed.add(e.colony_id)
    # This set is used only for startup/backfill bookkeeping.
    # It is the replay-visible durable receipt that extraction settled,
    # even when entries_created == 0.
```

Register all three handlers in the existing `_HANDLERS` dict.

---

## S4. Memory Extraction Pipeline (Track A -- A4)

### Module: surface/memory_extractor.py

```python
"""Institutional memory extraction from colony completion results.

Dual extraction: skills (procedural) + experiences (tactical).
Called by colony_manager after ColonyCompleted is emitted.
Fire-and-forget async task -- does NOT block colony lifecycle.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import structlog

from formicos.core.types import MemoryEntry, MemoryEntryPolarity, MemoryEntryStatus, MemoryEntryType

log = structlog.get_logger()

# Minimum content length to avoid extracting noise
_MIN_CONTENT_LEN = 30

# Maximum artifacts to include in extraction context
_MAX_ARTIFACT_CONTEXT = 5

# Truncation limit for artifact content in prompt
_ARTIFACT_PREVIEW_CHARS = 1500


def _build_extraction_prompt(
    task: str,
    final_output: str,
    artifacts: list[dict[str, Any]],
    colony_status: str,
    failure_reason: str | None,
    contract_result: dict[str, Any] | None,
) -> str:
    """Build the LLM prompt for dual skill+experience extraction."""
    parts = [
        "You are extracting institutional memory from a completed colony run.",
        "",
        f"TASK: {task}",
        f"STATUS: {colony_status}",
    ]

    if failure_reason:
        parts.append(f"FAILURE REASON: {failure_reason}")

    if contract_result:
        satisfied = contract_result.get("satisfied", True)
        missing = contract_result.get("missing", [])
        if not satisfied:
            parts.append(f"CONTRACT: NOT satisfied. Missing: {', '.join(missing)}")
        else:
            parts.append("CONTRACT: Satisfied.")

    if final_output:
        parts.append(f"\nFINAL OUTPUT (truncated):\n{final_output[:2000]}")

    if artifacts:
        parts.append("\nARTIFACTS PRODUCED:")
        for art in artifacts[:_MAX_ARTIFACT_CONTEXT]:
            preview = art.get("content", "")[:_ARTIFACT_PREVIEW_CHARS]
            parts.append(f"- {art.get('name', '?')} ({art.get('artifact_type', 'generic')}): {preview[:200]}")

    parts.append("")

    if colony_status == "completed":
        parts.append(
            "Extract transferable knowledge in two categories.\n\n"
            "SKILLS (reusable procedural patterns):\n"
            "For each skill, provide:\n"
            '- "title": short name for the technique\n'
            '- "content": the minimal actionable instruction for a future agent\n'
            '- "when_to_use": conditions under which this applies\n'
            '- "failure_modes": what can go wrong\n'
            '- "domains": relevant domain tags (e.g. ["python", "testing"])\n'
            '- "tool_refs": tools used (e.g. ["code_execute", "file_write"])\n\n'
            "EXPERIENCES (tactical lessons):\n"
            "For each experience, provide:\n"
            '- "title": short description of the lesson\n'
            '- "content": the minimal warning or tip (1-2 sentences)\n'
            '- "trigger": what environmental condition prompted this\n'
            '- "domains": relevant domain tags\n'
            '- "tool_refs": tools involved\n'
            '- "polarity": "positive" (this worked) or "neutral" (contextual)\n\n'
        )
    else:
        # Failed colony -- experiences only
        parts.append(
            "This colony FAILED. Extract only tactical lessons.\n\n"
            "EXPERIENCES (what went wrong and what to watch for):\n"
            "For each experience, provide:\n"
            '- "title": short description of the failure pattern\n'
            '- "content": the minimal warning for a future agent (1-2 sentences)\n'
            '- "trigger": what condition led to this failure\n'
            '- "domains": relevant domain tags\n'
            '- "tool_refs": tools involved\n'
            '- "polarity": "negative"\n\n'
        )

    parts.append(
        'Return JSON: {"skills": [...], "experiences": [...]}\n'
        "If no transferable knowledge exists, return empty arrays.\n"
        "Be conservative: fewer good entries is better than many noisy ones."
    )

    return "\n".join(parts)


def build_memory_entries(
    raw: dict[str, Any],
    colony_id: str,
    workspace_id: str,
    artifact_ids: list[str],
    colony_status: str,
) -> list[dict[str, Any]]:
    """Convert LLM extraction output into MemoryEntry dicts.

    Returns serialized MemoryEntry dicts ready for event emission.
    """
    entries: list[dict[str, Any]] = []
    now = datetime.now(UTC).isoformat()

    for i, skill in enumerate(raw.get("skills", [])):
        content = skill.get("content", "")
        if len(content) < _MIN_CONTENT_LEN:
            continue

        entry = MemoryEntry(
            id=f"mem-{colony_id}-s-{i}",
            entry_type=MemoryEntryType.skill,
            status=MemoryEntryStatus.candidate,
            polarity=MemoryEntryPolarity.positive,
            title=skill.get("title", f"skill-{i}"),
            content=content,
            summary=skill.get("when_to_use", ""),
            source_colony_id=colony_id,
            source_artifact_ids=artifact_ids,
            source_round=0,
            domains=skill.get("domains", []),
            tool_refs=skill.get("tool_refs", []),
            confidence=0.5,
            scan_status="pending",
            created_at=now,
            workspace_id=workspace_id,
        )
        entries.append(entry.model_dump())

    for i, exp in enumerate(raw.get("experiences", [])):
        content = exp.get("content", "")
        if len(content) < _MIN_CONTENT_LEN:
            continue

        polarity_str = exp.get("polarity", "neutral")
        if colony_status != "completed":
            polarity_str = "negative"

        try:
            polarity = MemoryEntryPolarity(polarity_str)
        except ValueError:
            polarity = MemoryEntryPolarity.neutral

        entry = MemoryEntry(
            id=f"mem-{colony_id}-e-{i}",
            entry_type=MemoryEntryType.experience,
            status=MemoryEntryStatus.candidate,
            polarity=polarity,
            title=exp.get("title", f"experience-{i}"),
            content=content,
            summary=exp.get("trigger", ""),
            source_colony_id=colony_id,
            source_artifact_ids=artifact_ids,
            source_round=0,
            domains=exp.get("domains", []),
            tool_refs=exp.get("tool_refs", []),
            confidence=0.5 if colony_status == "completed" else 0.4,
            scan_status="pending",
            created_at=now,
            workspace_id=workspace_id,
        )
        entries.append(entry.model_dump())

    return entries
```

### Hook in colony_manager.py

After `ColonyCompleted` is emitted (same location as existing skill crystallization):

```python
# After existing skill crystallization:
asyncio.create_task(self._extract_institutional_memory(
    colony_id=colony_id,
    workspace_id=workspace_id,
    colony_status="completed",  # or "failed" for ColonyFailed path
    artifacts=final_artifacts,
    transcript=build_transcript(colony_proj),
    failure_reason=None,
))
```

The `_extract_institutional_memory` method:
1. Builds the extraction prompt from artifacts + transcript + contract result
2. Calls LLM (local model, low temperature)
3. Parses JSON response via `parse_defensive`
4. Calls `build_memory_entries()` to validate and structure
5. For each entry: runs `scan_entry()` synchronously, bakes `scan_status` into the entry dict
6. If scan tier is high/critical: sets `status="rejected"` on the entry dict
7. Emits `MemoryEntryCreated` event via `runtime.emit_and_broadcast()` (with scan_status and status already set)
8. For non-rejected entries from successful colonies: emits `MemoryEntryStatusChanged` (candidate -> verified)

The scanner runs BEFORE event emission. `scan_status` is part of the persisted event payload.
Rejected entries are born rejected -- no separate status-change event needed for the rejection path.

After all entries are emitted (or if zero entries were extracted), emit `MemoryExtractionCompleted`:

```python
await runtime.emit_and_broadcast(MemoryExtractionCompleted(
    seq=0, timestamp=_now(), address=address,
    colony_id=colony_id,
    entries_created=len(emitted_entries),
    workspace_id=workspace_id,
))
```

This event is the durable receipt that extraction ran to completion. It MUST be emitted even when `entries_created=0`.

Fire-and-forget. If any step fails, log and continue. Colony lifecycle is not affected.

**Restart recovery:** On startup after replay, `app.py` compares completed colony IDs (from `ColonyCompleted` events) against colony IDs in `MemoryExtractionCompleted` events. Any completed colony with no corresponding `MemoryExtractionCompleted` is re-queued for extraction. Colonies where extraction legitimately produced zero entries are NOT re-queued because their `MemoryExtractionCompleted` (with `entries_created=0`) serves as the settled marker.

---

## S5. Memory Store -- Qdrant Projection (Track A -- A5)

### Module: surface/memory_store.py

```python
"""Institutional memory store -- Qdrant projection from memory events.

Maintains the institutional_memory collection as a derived index.
Rebuilt from event replay on startup. Updated on new events.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

from formicos.core.types import VectorDocument

if TYPE_CHECKING:
    from formicos.core.ports import VectorPort

log = structlog.get_logger()

COLLECTION_NAME = "institutional_memory"


class MemoryStore:
    """Manages the Qdrant projection for institutional memory."""

    def __init__(self, vector_port: VectorPort) -> None:
        self._vector = vector_port

    async def upsert_entry(self, entry: dict[str, Any]) -> None:
        """Upsert a memory entry into Qdrant with dense + sparse vectors."""
        entry_id = entry.get("id", "")
        if not entry_id:
            return

        # Build embedded text: title + content + summary for dense
        # Tool refs and domains added for sparse/BM25 boost
        embed_text = (
            f"{entry.get('title', '')}. "
            f"{entry.get('content', '')} "
            f"{entry.get('summary', '')} "
            f"tools: {' '.join(entry.get('tool_refs', []))} "
            f"domains: {' '.join(entry.get('domains', []))}"
        )

        doc = VectorDocument(
            id=entry_id,
            content=embed_text,
            metadata={
                "entry_type": entry.get("entry_type", "skill"),
                "status": entry.get("status", "candidate"),
                "polarity": entry.get("polarity", "positive"),
                "title": entry.get("title", ""),
                "content": entry.get("content", ""),
                "summary": entry.get("summary", ""),
                "source_colony_id": entry.get("source_colony_id", ""),
                "source_artifact_ids": entry.get("source_artifact_ids", []),
                "domains": entry.get("domains", []),
                "tool_refs": entry.get("tool_refs", []),
                "confidence": entry.get("confidence", 0.5),
                "scan_status": entry.get("scan_status", "pending"),
                "workspace_id": entry.get("workspace_id", ""),
                "created_at": entry.get("created_at", ""),
            },
        )
        await self._vector.upsert(collection=COLLECTION_NAME, docs=[doc])

    async def sync_entry(self, entry_id: str, projection_entries: dict[str, dict[str, Any]]) -> None:
        """Sync a single entry from projection state into Qdrant.

        Called by both:
        - Live event handlers (after MemoryEntryStatusChanged updates the projection)
        - Startup replay (after all events have rebuilt projection state)

        This is the SINGLE mechanism for keeping Qdrant consistent with event truth.
        Full re-upsert -- no partial payload update shortcut.
        """
        entry = projection_entries.get(entry_id)
        if entry is None:
            log.warning("memory_store.sync_entry.missing", entry_id=entry_id)
            return
        if entry.get("status") == "rejected":
            # Rejected entries should not be in Qdrant. Delete if present.
            await self._vector.delete(collection=COLLECTION_NAME, ids=[entry_id])
            return
        await self.upsert_entry(entry)

    async def search(
        self,
        query: str,
        *,
        entry_type: str = "",
        workspace_id: str = "",
        exclude_statuses: list[str] | None = None,
        top_k: int = 5,
    ) -> list[dict[str, Any]]:
        """Search institutional memory with payload-filtered Qdrant queries.

        Uses qdrant-client directly (not generic VectorPort.search) to apply
        payload filters at the Qdrant query level. This ensures correct results
        regardless of collection size -- rejected entries are never returned,
        type and workspace filtering happens before ranking.
        """
        if exclude_statuses is None:
            exclude_statuses = ["rejected"]

        # Build Qdrant payload filter conditions
        # Implementation note: this requires qdrant_client.models imported
        # in the actual implementation. The filter structure follows Qdrant's
        # Filter/FieldCondition/MatchValue pattern already used in vector_qdrant.py.
        #
        # filter_conditions = [
        #     FieldCondition(key="status", match=MatchExcept(except_values=exclude_statuses))
        # ]
        # if entry_type:
        #     filter_conditions.append(FieldCondition(key="entry_type", match=MatchValue(value=entry_type)))
        # if workspace_id:
        #     filter_conditions.append(FieldCondition(key="workspace_id", match=MatchValue(value=workspace_id)))
        #
        # query_filter = Filter(must=filter_conditions)
        #
        # Qdrant query_points() with query_filter applies ALL filters server-side
        # before ranking, so top_k results are guaranteed to satisfy constraints.

        # For the reference implementation, use the VectorPort with post-filter
        # as a fallback, but the real implementation MUST use payload-filtered
        # Qdrant queries. The vector_qdrant.py adapter already demonstrates
        # this pattern with namespace/confidence payload filters.
        results = await self._vector.search(
            collection=COLLECTION_NAME,
            query=query,
            top_k=top_k * 3,  # over-fetch for fallback path only
        )

        # Post-filter (fallback -- real impl uses Qdrant server-side filters)
        filtered: list[dict[str, Any]] = []
        for hit in results:
            meta = hit.metadata
            if meta.get("status") in exclude_statuses:
                continue
            if entry_type and meta.get("entry_type") != entry_type:
                continue
            if workspace_id and meta.get("workspace_id") != workspace_id:
                continue
            filtered.append({
                "id": hit.id,
                "score": hit.score,
                "entry_type": meta.get("entry_type", "skill"),
                "status": meta.get("status", "candidate"),
                "polarity": meta.get("polarity", "positive"),
                "title": meta.get("title", ""),
                "content": meta.get("content", ""),
                "summary": meta.get("summary", ""),
                "source_colony_id": meta.get("source_colony_id", ""),
                "confidence": meta.get("confidence", 0.5),
                "domains": meta.get("domains", []),
                "tool_refs": meta.get("tool_refs", []),
            })

        # Sort: verified before candidate, then by confidence descending
        status_order = {"verified": 0, "candidate": 1, "stale": 2}
        filtered.sort(key=lambda x: (status_order.get(x["status"], 9), -x["confidence"]))

        return filtered[:top_k]

    async def rebuild_from_projection(self, projection_entries: dict[str, dict[str, Any]]) -> int:
        """Rebuild the entire Qdrant collection from projection state.

        Called once at startup after event replay completes.
        Returns the number of entries upserted.
        """
        count = 0
        for entry_id, entry in projection_entries.items():
            if entry.get("status") == "rejected":
                continue
            await self.upsert_entry(entry)
            count += 1
        log.info("memory_store.rebuilt", entries=count)
        return count
```

---

## S6. Scan-on-Write Validation (Track B -- B1)

### Module: surface/memory_scanner.py

```python
"""Memory entry security scanner -- synchronous, sub-50ms, stdlib only.

Evaluates memory entry content for security risk signals across four axes.
Calibrated against patterns from Turnstone's 25K public skill security audit.
Runs on every MemoryEntryCreated before the entry is upserted into retrieval.
"""

from __future__ import annotations

import re
from typing import Any

# Composite thresholds -> tier
_THRESHOLDS = ((2.8, "critical"), (2.0, "high"), (1.2, "medium"), (0.5, "low"))


def _tier_from_score(score: float) -> str:
    for threshold, label in _THRESHOLDS:
        if score >= threshold:
            return label
    return "safe"


# --- Content risk patterns ---
_RE_EXEC = re.compile(
    r"\beval\s*[(]|\bexec\s*[(]|subprocess\.(?:run|call|Popen)|os\.(?:system|popen)",
    re.IGNORECASE,
)
_RE_SUDO = re.compile(r"\bsudo\s+\S+", re.IGNORECASE)
_RE_EXFIL = re.compile(
    r"curl\s+.*-d\s|wget\s+.*--post|requests\.post\s*\(",
    re.IGNORECASE,
)

# --- Supply chain risk patterns ---
_RE_PIPE_SHELL = re.compile(
    r"(?:curl|wget)\s[^\n|]{0,200}\|\s*(?:ba)?sh\b",
    re.IGNORECASE,
)
_RE_TRANSITIVE_INSTALL = re.compile(
    r"pip\s+install\s+git\+|npm\s+install\s+https?://|npx\s+\S+",
    re.IGNORECASE,
)

# --- Vulnerability risk patterns ---
_RE_PROMPT_INJECT = re.compile(
    r"ignore\s+(?:previous|all|above)\s+instructions|system\s*:\s*you\s+are",
    re.IGNORECASE,
)
_RE_CREDENTIAL = re.compile(
    r"(?:api[_-]?key|password|secret|token)\s*[:=]\s*['\"][^'\"]{8,}",
    re.IGNORECASE,
)

# --- Capability risk: dangerous tool combinations ---
_DANGEROUS_TOOL_COMBOS = [
    {"http_fetch", "file_write"},         # download-then-write
    {"code_execute", "http_fetch"},        # fetch-then-execute
    {"file_write", "code_execute"},        # write-then-execute
]


def scan_entry(entry: dict[str, Any]) -> dict[str, Any]:
    """Scan a memory entry and return risk assessment.

    Returns:
        {
            "tier": "safe" | "low" | "medium" | "high" | "critical",
            "score": float,
            "axes": {
                "content": float,
                "supply_chain": float,
                "vulnerability": float,
                "capability": float,
            },
            "findings": ["list of matched patterns"],
        }
    """
    content = entry.get("content", "") + " " + entry.get("title", "")
    tool_refs = set(entry.get("tool_refs", []))

    scores = {"content": 0.0, "supply_chain": 0.0, "vulnerability": 0.0, "capability": 0.0}
    findings: list[str] = []

    # Content risk
    if _RE_EXEC.search(content):
        scores["content"] += 1.0
        findings.append("exec/eval pattern")
    if _RE_SUDO.search(content):
        scores["content"] += 0.8
        findings.append("sudo usage")
    if _RE_EXFIL.search(content):
        scores["content"] += 1.2
        findings.append("data exfiltration pattern")

    # Supply chain risk
    if _RE_PIPE_SHELL.search(content):
        scores["supply_chain"] += 1.5
        findings.append("pipe-to-shell")
    if _RE_TRANSITIVE_INSTALL.search(content):
        scores["supply_chain"] += 1.0
        findings.append("transitive install from URL/git")

    # Vulnerability risk
    if _RE_PROMPT_INJECT.search(content):
        scores["vulnerability"] += 1.5
        findings.append("prompt injection pattern")
    if _RE_CREDENTIAL.search(content):
        scores["vulnerability"] += 1.0
        findings.append("embedded credential")

    # Capability risk
    for combo in _DANGEROUS_TOOL_COMBOS:
        if combo.issubset(tool_refs):
            scores["capability"] += 0.8
            findings.append(f"dangerous tool combo: {sorted(combo)}")

    composite = sum(scores.values())
    tier = _tier_from_score(composite)

    return {
        "tier": tier,
        "score": composite,
        "axes": scores,
        "findings": findings,
    }
```

### Integration Point -- in the extraction pipeline, BEFORE event emission

The scanner is called in `_extract_institutional_memory` (colony_manager.py),
after `build_memory_entries()` returns but BEFORE any `MemoryEntryCreated`
event is emitted:

```python
from formicos.surface.memory_scanner import scan_entry

for entry in entries:
    # 1. Scan BEFORE event emission
    scan_result = scan_entry(entry)
    entry["scan_status"] = scan_result["tier"]

    # 2. If dangerous, set status to rejected on the entry itself
    if scan_result["tier"] in ("high", "critical"):
        entry["status"] = "rejected"
        log.warning(
            "memory.scan_rejected",
            entry_id=entry["id"],
            tier=scan_result["tier"],
            findings=scan_result["findings"],
        )

    # 3. Emit the event with scan_status and status already baked in
    await runtime.emit_and_broadcast(MemoryEntryCreated(
        seq=0, timestamp=_now(), address=address,
        entry=entry,
        workspace_id=entry.get("workspace_id", ""),
    ))

    # 4. Qdrant upsert via projection handler (only for non-rejected)
    #    The projection handler calls memory_store.sync_entry()
    #    which checks status and skips rejected entries.

    # 5. Verification (only for non-rejected entries from successful colonies)
    if entry["status"] != "rejected" and colony_status == "completed":
        await runtime.emit_and_broadcast(MemoryEntryStatusChanged(
            seq=0, timestamp=_now(), address=address,
            entry_id=entry["id"],
            old_status="candidate",
            new_status="verified",
            reason="source colony completed successfully",
            workspace_id=entry.get("workspace_id", ""),
        ))

# 6. ALWAYS emit the extraction receipt -- even when entries is empty
await runtime.emit_and_broadcast(MemoryExtractionCompleted(
    seq=0, timestamp=_now(), address=address,
    colony_id=colony_id,
    entries_created=len([e for e in entries if e["status"] != "rejected"]),
    workspace_id=workspace_id,
))
```

The critical ordering guarantee: `scan_status` is part of the `MemoryEntryCreated`
event payload. On replay, no re-scanning is needed. Rejected entries are born
rejected. Verification only fires after scanning passes.
`MemoryExtractionCompleted` is ALWAYS emitted as the final step, even when zero
entries were created, to prevent infinite re-queue on restart.

---

## S7. Queen Pre-Spawn Retrieval (Track B -- B2)

### In runtime.py -- before Queen spawn reasoning

```python
async def _retrieve_relevant_memory(
    self,
    task: str,
    workspace_id: str,
) -> str:
    """Deterministic pre-spawn memory retrieval.

    Returns formatted block for Queen context injection.
    """
    if self._memory_store is None:
        return ""

    skills = await self._memory_store.search(
        query=task,
        entry_type="skill",
        workspace_id=workspace_id,
        top_k=3,
    )
    experiences = await self._memory_store.search(
        query=task,
        entry_type="experience",
        workspace_id=workspace_id,
        top_k=2,
    )

    if not skills and not experiences:
        return ""

    lines = ["[Institutional Memory]"]
    for entry in skills:
        status_tag = entry["status"].upper()
        polarity_tag = f", {entry['polarity']}" if entry["polarity"] != "positive" else ""
        lines.append(
            f"[SKILL, {status_tag}{polarity_tag}] \"{entry['title']}\": "
            f"{entry['content'][:300]}"
        )
        lines.append(f"  source: colony {entry['source_colony_id']}, confidence: {entry['confidence']:.1f}")

    for entry in experiences:
        status_tag = entry["status"].upper()
        polarity_tag = f", {entry['polarity']}" if entry["polarity"] != "positive" else ""
        lines.append(
            f"[EXP, {status_tag}{polarity_tag}] \"{entry['title']}\": "
            f"{entry['content'][:300]}"
        )
        lines.append(f"  source: colony {entry['source_colony_id']}, confidence: {entry['confidence']:.1f}")

    return "\n".join(lines)
```

This block is injected as a developer-role message in the Queen's context before the first LLM call on a new task. It is deterministic (always runs), not a nudge.

---

## S8. Queen Memory Search Tool (Track B -- B3)

### Tool Spec

```python
MEMORY_SEARCH_TOOL: LLMToolSpec = {
    "name": "memory_search",
    "description": (
        "Search institutional memory for skills and experiences relevant to a query. "
        "Returns entries with provenance, trust status, and confidence scores."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query -- task description, tool name, error pattern, etc."},
            "entry_type": {
                "type": "string",
                "enum": ["skill", "experience", ""],
                "description": "Filter by entry type. Empty string for both.",
            },
            "limit": {
                "type": "integer",
                "description": "Max results (default 5, max 10).",
            },
        },
        "required": ["query"],
    },
}
```

### Handler in queen_runtime.py

```python
async def _tool_memory_search(self, arguments: dict[str, Any]) -> str:
    """Handle the memory_search Queen tool."""
    if self._memory_store is None:
        return "Institutional memory is not available."

    query = arguments.get("query", "")
    entry_type = arguments.get("entry_type", "")
    limit = min(arguments.get("limit", 5), 10)

    results = await self._memory_store.search(
        query=query,
        entry_type=entry_type,
        workspace_id=self._workspace_id,
        top_k=limit,
    )

    if not results:
        return f"No memory entries found for: {query}"

    lines = [f"Found {len(results)} entries:"]
    for r in results:
        polarity_tag = f" ({r['polarity']})" if r["polarity"] != "positive" else ""
        lines.append(
            f"- [{r['entry_type'].upper()}, {r['status']}]{polarity_tag} "
            f"\"{r['title']}\": {r['content'][:200]}"
        )
        if r.get("domains"):
            lines.append(f"  domains: {', '.join(r['domains'])}")
        lines.append(f"  source: colony {r['source_colony_id']}, confidence: {r['confidence']:.1f}")
    return "\n".join(lines)
```

---

## S9. Metacognition Module (Track C -- C1)

### Module: surface/metacognition.py

```python
"""Metacognitive nudges for institutional memory use (Wave 26).

Pure functions, no I/O. Called by queen_runtime.py.
Separates deterministic triggers from model-facing hints.
"""

from __future__ import annotations

import time
from typing import Any

# Cooldown: minimum seconds between nudges of the same type
_COOLDOWN_SECS = 300.0


# ---------------------------------------------------------------------------
# Nudge templates (model-facing hints, appended as developer messages)
# ---------------------------------------------------------------------------

NUDGE_PRIOR_FAILURES = (
    "Note: Prior colonies encountered failures in domains relevant to this task. "
    "Relevant experiences have been included in your context. "
    "Pay attention to negative-polarity entries -- they describe approaches that failed."
)

NUDGE_SAVE_CORRECTIONS = (
    "Note: You redirected or modified this colony's approach. "
    "Consider whether this correction reflects a transferable lesson. "
    "If so, it will be captured automatically on completion."
)

NUDGE_MEMORY_AVAILABLE = (
    "Note: Institutional memory is available for this workspace. "
    "Relevant skills and experiences have been pre-loaded into your context. "
    "You can also use memory_search to find additional entries."
)


def should_nudge(
    nudge_type: str,
    cooldown_state: dict[str, float],
    cooldown_secs: float = _COOLDOWN_SECS,
) -> bool:
    """Check whether a nudge should fire, respecting cooldown."""
    now = time.monotonic()
    last = cooldown_state.get(nudge_type, 0.0)
    if now - last < cooldown_secs:
        return False
    cooldown_state[nudge_type] = now
    return True


def check_prior_failures(
    task_domains: list[str],
    memory_entries: list[dict[str, Any]],
) -> bool:
    """Return True if negative experiences exist in overlapping domains."""
    if not task_domains or not memory_entries:
        return False
    task_set = set(task_domains)
    for entry in memory_entries:
        if entry.get("polarity") == "negative":
            entry_domains = set(entry.get("domains", []))
            if task_set & entry_domains:
                return True
    return False


def check_memory_available(
    workspace_id: str,
    memory_entry_count: int,
) -> bool:
    """Return True if the workspace has institutional memory entries."""
    return memory_entry_count > 0


def format_nudge(nudge_type: str) -> str:
    """Return the nudge text for a given type, or empty string if unknown."""
    return {
        "prior_failures": NUDGE_PRIOR_FAILURES,
        "save_corrections": NUDGE_SAVE_CORRECTIONS,
        "memory_available": NUDGE_MEMORY_AVAILABLE,
    }.get(nudge_type, "")
```

---

## S10. Memory API Endpoints (Track B -- B4)

### Module: surface/routes/memory_api.py

```python
"""Institutional memory REST API (Wave 26)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from starlette.responses import JSONResponse
from starlette.routing import Route

if TYPE_CHECKING:
    from starlette.requests import Request
    from formicos.surface.memory_store import MemoryStore
    from formicos.surface.projections import ProjectionStore


def routes(
    *,
    projections: ProjectionStore,
    memory_store: MemoryStore | None = None,
    **_unused: Any,
) -> list[Route]:

    async def list_entries(request: Request) -> JSONResponse:
        entry_type = request.query_params.get("type", "")
        status = request.query_params.get("status", "")
        workspace = request.query_params.get("workspace", "")
        domain = request.query_params.get("domain", "")
        limit = min(int(request.query_params.get("limit", "50")), 200)

        entries = list(projections.memory_entries.values())

        if entry_type:
            entries = [e for e in entries if e.get("entry_type") == entry_type]
        if status:
            entries = [e for e in entries if e.get("status") == status]
        if workspace:
            entries = [e for e in entries if e.get("workspace_id") == workspace]
        if domain:
            entries = [e for e in entries if domain in e.get("domains", [])]

        # Sort: newest first
        entries.sort(key=lambda e: e.get("created_at", ""), reverse=True)
        return JSONResponse({"entries": entries[:limit], "total": len(entries)})

    async def get_entry(request: Request) -> JSONResponse:
        entry_id = request.path_params["entry_id"]
        entry = projections.memory_entries.get(entry_id)
        if entry is None:
            return JSONResponse({"error": "entry not found"}, status_code=404)
        return JSONResponse(entry)

    async def search_entries(request: Request) -> JSONResponse:
        if memory_store is None:
            return JSONResponse({"error": "memory store not available"}, status_code=503)

        query = request.query_params.get("q", "")
        if not query:
            return JSONResponse({"error": "query parameter 'q' required"}, status_code=400)

        entry_type = request.query_params.get("type", "")
        workspace = request.query_params.get("workspace", "")
        limit = min(int(request.query_params.get("limit", "10")), 50)

        results = await memory_store.search(
            query=query,
            entry_type=entry_type,
            workspace_id=workspace,
            top_k=limit,
        )
        return JSONResponse({"results": results, "total": len(results)})

    return [
        Route("/api/v1/memory", list_entries, methods=["GET"]),
        Route("/api/v1/memory/search", search_entries, methods=["GET"]),
        Route("/api/v1/memory/{entry_id:str}", get_entry, methods=["GET"]),
    ]
```

---

## S11. Files Changed Summary

### Track A (Coder 1)
| File | Action |
|------|--------|
| `src/formicos/core/types.py` | MemoryEntry, MemoryEntryType, MemoryEntryStatus, MemoryEntryPolarity (~50 LOC) |
| `src/formicos/core/events.py` | MemoryEntryCreated, MemoryEntryStatusChanged, MemoryExtractionCompleted; union 37->40 (~35 LOC) |
| `src/formicos/surface/projections.py` | memory_entries dict + two handlers (~40 LOC) |
| `src/formicos/surface/memory_extractor.py` | New -- dual extraction pipeline (~150 LOC) |
| `src/formicos/surface/colony_manager.py` | Extraction hook after completion (~20 LOC) |
| `src/formicos/surface/memory_store.py` | New -- Qdrant projection + search (~100 LOC) |
| `src/formicos/surface/app.py` | Wire memory store into lifespan (~10 LOC) |

### Track B (Coder 2)
| File | Action |
|------|--------|
| `src/formicos/surface/memory_scanner.py` | New -- scan-on-write validation (~120 LOC) |
| `src/formicos/surface/runtime.py` | Pre-spawn memory retrieval (~40 LOC) |
| `src/formicos/surface/queen_runtime.py` | memory_search tool spec + handler (~40 LOC) |
| `src/formicos/surface/routes/memory_api.py` | New -- REST API (~80 LOC) |
| `src/formicos/surface/app.py` | Wire memory routes (~5 LOC) |

### Track C (Coder 3)
| File | Action |
|------|--------|
| `src/formicos/surface/metacognition.py` | New -- nudge logic + detection (~80 LOC) |
| `src/formicos/surface/queen_runtime.py` | Nudge call sites (~25 LOC, additive) |
| `frontend/src/components/memory-browser.ts` | New -- memory browser (~200 LOC) |
| `frontend/src/components/colony-detail.ts` | Memory count indicator (~15 LOC) |
| `frontend/src/types.ts` | MemoryEntryPreview interface (~15 LOC) |
| `frontend/src/state/store.ts` | Memory API wiring (~20 LOC) |
