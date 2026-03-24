"""Federated knowledge catalog -- read-only aggregation over both backends (Wave 27).

Normalizes legacy skill bank entries and institutional memory entries into
a common KnowledgeItem shape.  Read-only -- does not write to either store.
"""

from __future__ import annotations

import asyncio
import math
import time as _time_mod
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from formicos.core.ports import VectorPort
    from formicos.surface.memory_store import MemoryStore
    from formicos.surface.projections import ProjectionStore

log = structlog.get_logger()

_LEGACY_LIST_FETCH_K = 200


# ---------------------------------------------------------------------------
# Wave 41 B3: Retrieval metrics for compounding-curve measurement
# ---------------------------------------------------------------------------


@dataclass
class RetrievalMetrics:
    """Lightweight retrieval contribution tracker.

    Records which knowledge entries were accessed during retrieval so that
    the compounding-curve infrastructure can measure whether earlier-extracted
    knowledge is actually used by later tasks.
    """

    total_queries: int = 0
    total_results_returned: int = 0
    entries_accessed: dict[str, int] = field(default_factory=lambda: dict[str, int]())

    def record_access(self, entry_ids: list[str]) -> None:
        """Record that these entries were returned by a retrieval query."""
        self.total_queries += 1
        self.total_results_returned += len(entry_ids)
        for eid in entry_ids:
            self.entries_accessed[eid] = self.entries_accessed.get(eid, 0) + 1

    def snapshot(self) -> dict[str, Any]:
        """Return a snapshot of current metrics."""
        return {
            "total_queries": self.total_queries,
            "total_results_returned": self.total_results_returned,
            "unique_entries_accessed": len(self.entries_accessed),
            "entries_accessed": dict(self.entries_accessed),
        }

    def reset(self) -> None:
        """Reset metrics for a new measurement period."""
        self.total_queries = 0
        self.total_results_returned = 0
        self.entries_accessed.clear()


@dataclass(frozen=True)
class KnowledgeItem:
    """Normalized read model for unified knowledge display."""

    id: str = ""
    canonical_type: str = "skill"
    source_system: str = ""
    status: str = "active"
    confidence: float = 0.5
    title: str = ""
    summary: str = ""
    content_preview: str = ""
    source_colony_id: str = ""
    source_artifact_ids: list[str] = field(default_factory=lambda: list[str]())
    domains: list[str] = field(default_factory=lambda: list[str]())
    tool_refs: list[str] = field(default_factory=lambda: list[str]())
    created_at: str = ""
    polarity: str = "positive"
    legacy_metadata: dict[str, Any] = field(default_factory=lambda: dict[str, Any]())
    score: float = 0.0
    scope: str = ""  # Wave 50: thread / workspace / global
    sub_type: str = ""  # Wave 58: granular sub-type (technique, trajectory, etc.)


def _normalize_legacy_skill(hit: Any) -> dict[str, Any]:  # noqa: ANN401
    """Convert a VectorSearchHit from skill_bank_v2 into KnowledgeItem dict."""
    meta: dict[str, Any] = hit.metadata if hasattr(hit, "metadata") else {}
    content: str = hit.content if hasattr(hit, "content") else ""
    technique: str = str(meta.get("technique", ""))

    return asdict(KnowledgeItem(
        id=str(hit.id) if hasattr(hit, "id") else "",
        canonical_type="skill",
        source_system="legacy_skill_bank",
        status="active",
        confidence=float(meta.get("confidence", 0.5)),
        title=technique if technique else str(content[:80].split("\n")[0]),
        summary=str(meta.get("when_to_use", "")),
        content_preview=str(content[:500]),
        source_colony_id=str(meta.get(
            "source_colony_id", meta.get("source_colony", ""),
        )),
        source_artifact_ids=[],
        domains=[],
        tool_refs=[],
        created_at=str(meta.get("extracted_at", "")),
        polarity="positive",
        legacy_metadata={
            "conf_alpha": meta.get("conf_alpha"),
            "conf_beta": meta.get("conf_beta"),
            "merge_count": meta.get("merge_count", 0),
            "algorithm_version": meta.get("algorithm_version", ""),
            "failure_modes": meta.get("failure_modes", ""),
        },
        score=float(hit.score) if hasattr(hit, "score") else 0.0,
    ))


def _normalize_institutional(
    entry: dict[str, Any], score: float = 0.0,
    similarity: float = 0.0,
) -> dict[str, Any]:
    """Convert an institutional memory entry into KnowledgeItem dict."""
    result = asdict(KnowledgeItem(
        id=entry.get("id", ""),
        canonical_type=entry.get("entry_type", "skill"),
        source_system="institutional_memory",
        status=entry.get("status", "candidate"),
        confidence=float(entry.get("confidence", 0.5)),
        title=entry.get("title", ""),
        summary=entry.get("summary", ""),
        content_preview=entry.get("content", "")[:500],
        source_colony_id=entry.get("source_colony_id", ""),
        source_artifact_ids=entry.get("source_artifact_ids", []),
        domains=entry.get("domains", []),
        tool_refs=entry.get("tool_refs", []),
        created_at=entry.get("created_at", ""),
        polarity=entry.get("polarity", "positive"),
        legacy_metadata={},
        score=score,
        scope=entry.get("scope", ""),
        sub_type=str(entry.get("sub_type", "") or ""),
    ))
    result["similarity"] = similarity
    return result


def _enrich_trust_provenance(
    item: dict[str, Any], raw_entry: dict[str, Any],
) -> None:
    """Annotate a normalized knowledge item with trust rationale and provenance.

    Wave 37 2C: Adds operator-visible metadata so an operator can answer:
      - Where did this entry come from?
      - Why does the system trust it?
      - Is it local or federated?

    Writes directly into the item dict (mutating).
    """
    from formicos.surface.admission import evaluate_entry  # noqa: PLC0415

    # Provenance metadata with bi-temporal info (Wave 38)
    created_at = raw_entry.get("created_at", "")
    provenance: dict[str, Any] = {
        "source_colony_id": raw_entry.get("source_colony_id", ""),
        "source_round": raw_entry.get("source_round", ""),
        "source_agent": raw_entry.get("source_agent", ""),
        "source_peer": raw_entry.get("source_peer", ""),
        "is_federated": bool(raw_entry.get("source_peer", "")),
        "created_at": created_at,
        "workspace_id": raw_entry.get("workspace_id", ""),
        "thread_id": raw_entry.get("thread_id", ""),
        "decay_class": raw_entry.get("decay_class", "ephemeral"),
        "federation_hop": raw_entry.get("federation_hop", 0),
        # Bi-temporal: transaction_time = when the system learned it
        # validity_time is only available for graph edges, not entry-level
        "transaction_time": created_at,
        "status_changed_at": raw_entry.get("status_changed_at", ""),
        "invalidated_at": raw_entry.get("invalidated_at", ""),
    }
    # Wave 46: expose forager provenance for web-sourced entries
    forager_prov = raw_entry.get("forager_provenance")
    if isinstance(forager_prov, dict):
        provenance["forager_provenance"] = {
            "source_url": forager_prov.get("source_url", ""),
            "source_domain": forager_prov.get("source_domain", ""),
            "source_credibility": forager_prov.get("source_credibility", 0.5),
            "fetch_timestamp": forager_prov.get("fetch_timestamp", ""),
            "forager_trigger": forager_prov.get("forager_trigger", ""),
            "forager_query": forager_prov.get("forager_query", ""),
            "quality_score": forager_prov.get("quality_score", 0.0),
            "fetch_level": forager_prov.get("fetch_level", 1),
        }
    item["provenance"] = provenance

    # Trust rationale via admission scoring
    admission = evaluate_entry(raw_entry)
    item["trust_rationale"] = {
        "admission_score": admission.score,
        "rationale": admission.rationale,
        "flags": admission.flags,
        "admitted": admission.admitted,
        "signal_scores": admission.signal_scores,
    }


def _compute_freshness(created_at: str) -> float:
    """Exponential decay with 90-day half-life. Returns value in [0, 1].

    Ported from engine/context.py. Defaults to 1.0 for empty/invalid strings.
    """
    if not created_at:
        return 1.0
    try:
        ext_dt = datetime.fromisoformat(created_at)
        age_days = (_time_mod.time() - ext_dt.timestamp()) / 86400.0
    except (ValueError, TypeError):
        return 1.0
    return 2.0 ** (-age_days / 90.0)


# Composite sort: Thompson Sampling + semantic + freshness + status + thread + cooccurrence
_STATUS_BONUS: dict[str, float] = {
    "verified": 1.0, "active": 0.8,
    "candidate": 0.5, "stale": 0.0,
}


def _sigmoid_cooccurrence(raw_weight: float) -> float:
    """Normalize co-occurrence weight to [0, 1]. ADR-044 D1."""
    if raw_weight <= 0.0:
        return 0.0
    return 1.0 - math.exp(-0.6 * raw_weight)


def _cooccurrence_score(
    entry_id: str,
    other_ids: list[str],
    projections: Any,  # noqa: ANN401
) -> float:
    """Max sigmoid-normalized co-occurrence weight with any other result."""
    if projections is None:
        return 0.0
    from formicos.surface.projections import cooccurrence_key  # noqa: PLC0415

    max_weight = 0.0
    for other_id in other_ids:
        key = cooccurrence_key(entry_id, other_id)
        entry = projections.cooccurrence_weights.get(key)
        if entry:
            max_weight = max(max_weight, entry.weight)
    return _sigmoid_cooccurrence(max_weight)


def _composite_key(
    item: dict[str, Any],
    weights: dict[str, float] | None = None,
) -> float:
    """Thompson Sampling composite (no co-occurrence). Returns NEGATIVE for ascending sort.

    Used by non-thread-boosted paths where co-occurrence context is unavailable.
    """
    from formicos.surface.trust import federated_retrieval_penalty  # noqa: PLC0415

    if weights is None:
        from formicos.surface.knowledge_constants import COMPOSITE_WEIGHTS  # noqa: PLC0415

        weights = COMPOSITE_WEIGHTS
    W = weights  # noqa: N806

    from formicos.engine.scoring_math import exploration_score  # noqa: PLC0415

    semantic = float(item.get("score", 0.0))
    alpha = float(item.get("conf_alpha", 5.0))
    beta_p = float(item.get("conf_beta", 5.0))
    # Wave 41 A2: unified exploration-confidence via shared helper
    thompson = exploration_score(alpha, beta_p)
    freshness = _compute_freshness(item.get("created_at", ""))
    status = _STATUS_BONUS.get(str(item.get("status", "")), 0.0)
    thread_bonus = float(item.get("_thread_bonus", 0.0))
    # Wave 39: pinned entries get decay protection and retrieval preference
    pin_boost = float(item.get("_pin_boost", 0.0))
    # Wave 38/41: federated entries penalized via posterior-aware trust
    fed_penalty = federated_retrieval_penalty(item)
    raw = (
        W["semantic"] * semantic
        + W["thompson"] * thompson
        + W["freshness"] * freshness
        + W["status"] * status
        + W["thread"] * thread_bonus
        # Wave 59.5: graph_proximity only has real values in _search_thread_boosted;
        # here it's always 0.0 to keep the weight dict consistent across both paths.
        + W.get("graph_proximity", 0.0) * 0.0
        + pin_boost
    )
    return -(raw * fed_penalty)


class KnowledgeCatalog:
    """Federated read facade over legacy skill bank and institutional memory."""

    def __init__(
        self,
        memory_store: MemoryStore | None,
        vector_port: VectorPort | None,
        skill_collection: str,
        projections: ProjectionStore | None = None,
        kg_adapter: Any = None,
    ) -> None:
        self._memory_store = memory_store
        self._vector = vector_port
        self._skill_collection = skill_collection
        self._projections = projections
        self._kg_adapter = kg_adapter  # Wave 59.5: KnowledgeGraphAdapter, optional
        # Wave 41 B3: lightweight retrieval metrics for compounding-curve measurement
        self._retrieval_metrics = RetrievalMetrics()

    _THREAD_BONUS = 1.0  # Wave 32 A3: normalized to [0,1], weight 0.08 scales contribution

    async def search(
        self,
        query: str,
        *,
        source_system: str = "",
        canonical_type: str = "",
        workspace_id: str = "",
        thread_id: str = "",
        source_colony_id: str = "",
        top_k: int = 10,
    ) -> list[dict[str, Any]]:
        """Federated search across both backends in parallel."""
        try:
            return await self._search_vector(
                query,
                source_system=source_system,
                canonical_type=canonical_type,
                workspace_id=workspace_id,
                thread_id=thread_id,
                source_colony_id=source_colony_id,
                top_k=top_k,
            )
        except Exception:  # noqa: BLE001
            log.warning(
                "knowledge_catalog.vector_search_failed_using_keyword_fallback",
                workspace_id=workspace_id,
            )
            return self._projection_keyword_fallback(
                query, workspace_id=workspace_id, top_k=top_k,
            )

    async def _search_vector(
        self,
        query: str,
        *,
        source_system: str,
        canonical_type: str,
        workspace_id: str,
        thread_id: str,
        source_colony_id: str,
        top_k: int,
    ) -> list[dict[str, Any]]:
        """Vector-backed search (primary path)."""

        # Wave 29: thread-scoped two-phase search with boost
        if thread_id:
            return await self._search_thread_boosted(
                query,
                source_system=source_system,
                canonical_type=canonical_type,
                workspace_id=workspace_id,
                thread_id=thread_id,
                source_colony_id=source_colony_id,
                top_k=top_k,
            )

        tasks: list[Any] = []

        # Institutional memory
        if (
            self._memory_store is not None
            and source_system in ("", "institutional_memory")
        ):
            entry_type = canonical_type if canonical_type in ("skill", "experience") else ""
            tasks.append(self._search_institutional(
                query, entry_type=entry_type,
                workspace_id=workspace_id,
                source_colony_id=source_colony_id,
                top_k=top_k,
            ))
        else:
            tasks.append(_empty())

        # Legacy skill bank
        if (
            self._vector is not None
            and source_system in ("", "legacy_skill_bank")
            and canonical_type in ("", "skill")
        ):
            tasks.append(self._search_legacy(
                query, source_colony_id=source_colony_id, top_k=top_k,
            ))
        else:
            tasks.append(_empty())

        institutional, legacy = await asyncio.gather(*tasks)

        # Merge, deduplicate, sort
        seen: set[str] = set()
        merged: list[dict[str, Any]] = []
        for item in institutional + legacy:
            item_id = item.get("id", "")
            if item_id and item_id not in seen:
                seen.add(item_id)
                merged.append(item)

        # Wave 39: apply operator overlays (skip muted/invalidated, boost pinned)
        merged = self._apply_operator_overlays(merged)

        # Wave 35 C2: per-workspace weights (ADR-044 D4)
        from formicos.surface.knowledge_constants import get_workspace_weights  # noqa: PLC0415

        ws_weights = get_workspace_weights(workspace_id, self._projections)
        merged.sort(key=lambda item: _composite_key(item, weights=ws_weights))
        return merged[:top_k]

    def _projection_keyword_fallback(
        self,
        query: str,
        *,
        workspace_id: str,
        top_k: int = 5,
    ) -> list[dict[str, Any]]:
        """BM25 keyword fallback when Qdrant is unavailable."""
        if self._projections is None:
            return []
        entries = [
            e for e in self._projections.memory_entries.values()
            if e.get("workspace_id") == workspace_id
            and e.get("status") in ("verified", "active", "candidate")
        ]
        if not entries:
            return []
        query_words = set(query.lower().split())
        scored: list[tuple[int, dict[str, Any]]] = []
        for e in entries:
            text = (
                f"{e.get('title', '')} {e.get('content', '')} "
                f"{' '.join(e.get('domains', []))}"
            ).lower()
            entry_words = set(text.split())
            overlap = len(query_words & entry_words)
            if overlap > 0:
                scored.append((overlap, e))
        scored.sort(key=lambda x: -x[0])
        results: list[dict[str, Any]] = []
        for _, e in scored[:top_k]:
            item = _normalize_institutional(e, score=0.0)
            item["source"] = "keyword_fallback"
            results.append(item)
        # Wave 39: apply operator overlays
        results = self._apply_operator_overlays(results)
        return results

    async def _search_thread_boosted(
        self,
        query: str,
        *,
        source_system: str,
        canonical_type: str,
        workspace_id: str,
        thread_id: str,
        source_colony_id: str,
        top_k: int,
    ) -> list[dict[str, Any]]:
        """Two-phase search: thread-scoped (boosted) + workspace-wide merge."""
        entry_type = canonical_type if canonical_type in ("skill", "experience") else ""

        # Phase 1: thread-scoped entries (boost score)
        thread_items: list[dict[str, Any]] = []
        if (
            self._memory_store is not None
            and source_system in ("", "institutional_memory")
        ):
            thread_items = await self._search_institutional(
                query, entry_type=entry_type,
                workspace_id=workspace_id,
                thread_id=thread_id,
                source_colony_id=source_colony_id,
                top_k=top_k,
            )
            for item in thread_items:
                item["_thread_bonus"] = self._THREAD_BONUS

        # Phase 2: workspace-wide entries
        ws_items: list[dict[str, Any]] = []
        if (
            self._memory_store is not None
            and source_system in ("", "institutional_memory")
        ):
            ws_items = await self._search_institutional(
                query, entry_type=entry_type,
                workspace_id=workspace_id,
                source_colony_id=source_colony_id,
                top_k=top_k,
            )

        # Merge + deduplicate (thread-boosted version wins)
        seen: set[str] = set()
        merged: list[dict[str, Any]] = []
        for item in thread_items + ws_items:
            item_id = item.get("id", "")
            if item_id and item_id not in seen:
                seen.add(item_id)
                merged.append(item)

        # Add legacy (no thread concept)
        if self._vector:
            legacy = await self._search_legacy(
                query, source_colony_id=source_colony_id, top_k=top_k,
            )
        else:
            legacy = []
        for item in legacy:
            item_id = item.get("id", "")
            if item_id and item_id not in seen:
                seen.add(item_id)
                merged.append(item)

        # Wave 39: apply operator overlays (skip muted/invalidated, boost pinned)
        merged = self._apply_operator_overlays(merged)

        # Wave 59.5: graph-augmented retrieval — discover neighbors of top-3
        graph_scores: dict[str, float] = {}
        if self._kg_adapter is not None and self._projections is not None:
            seed_items = sorted(
                merged, key=lambda x: -float(x.get("score", 0.0)),
            )[:3]
            for seed in seed_items:
                seed_entry_id = seed.get("id", "")
                node_id = self._projections.entry_kg_nodes.get(
                    seed_entry_id, "",
                )
                if not node_id:
                    continue
                try:
                    neighbors = await self._kg_adapter.get_neighbors(
                        node_id,
                        workspace_id=workspace_id,
                    )
                    for nbr in neighbors:
                        # Wave 60: fix node_id bug — get_neighbors()
                        # returns from_node/to_node, not node_id
                        other_node = (
                            nbr["to_node"] if nbr["from_node"] == node_id
                            else nbr["from_node"]
                        )
                        # Reverse lookup: find entry_id for this KG node
                        for eid, nid in (
                            self._projections.entry_kg_nodes.items()
                        ):
                            if nid == other_node and eid not in seen:
                                entry_data = (
                                    self._projections.memory_entries.get(eid)
                                )
                                if entry_data:
                                    item = _normalize_institutional(
                                        entry_data, score=0.0,
                                    )
                                    merged.append(item)
                                    seen.add(eid)
                                    graph_scores[eid] = 1.0
                                break
                except Exception:  # noqa: BLE001
                    log.warning(
                        "knowledge_catalog.graph_neighbor_lookup_failed",
                        seed_id=seed_entry_id,
                    )

        # Wave 34 A3: composite sort with co-occurrence (ADR-044)
        cooc_scores: dict[str, float] = {}
        result_ids = [r.get("id", "") for r in merged]
        for r in merged:
            rid = r.get("id", "")
            others = [oid for oid in result_ids if oid != rid]
            cooc_scores[rid] = _cooccurrence_score(
                rid, others, self._projections,
            )

        # Wave 35 C2: per-workspace weights (ADR-044 D4)
        from formicos.surface.knowledge_constants import get_workspace_weights  # noqa: PLC0415

        _W = get_workspace_weights(workspace_id, self._projections)  # noqa: N806

        from formicos.engine.scoring_math import exploration_score  # noqa: PLC0415
        from formicos.surface.trust import federated_retrieval_penalty  # noqa: PLC0415

        def _keyfn(item: dict[str, Any]) -> float:
            semantic = float(item.get("score", 0.0))
            alpha = float(item.get("conf_alpha", 5.0))
            beta_p = float(item.get("conf_beta", 5.0))
            # Wave 41 A2: unified exploration-confidence via shared helper
            thompson = exploration_score(alpha, beta_p)
            freshness = _compute_freshness(item.get("created_at", ""))
            status_bonus = _STATUS_BONUS.get(
                str(item.get("status", "")), 0.0,
            )
            thread_bonus = float(item.get("_thread_bonus", 0.0))
            cooc = cooc_scores.get(item.get("id", ""), 0.0)
            # Wave 59.5: graph proximity signal
            graph_prox = graph_scores.get(item.get("id", ""), 0.0)
            # Wave 39: pinned entries get retrieval preference
            pin_boost = float(item.get("_pin_boost", 0.0))
            # Wave 38: federated penalty prevents weak foreign dominance
            fed_penalty = federated_retrieval_penalty(item)
            raw_composite = (
                _W["semantic"] * semantic
                + _W["thompson"] * thompson
                + _W["freshness"] * freshness
                + _W["status"] * status_bonus
                + _W["thread"] * thread_bonus
                + _W["cooccurrence"] * cooc
                + _W.get("graph_proximity", 0.0) * graph_prox
                + pin_boost
            )
            composite = -(raw_composite * fed_penalty)
            # Wave 34.5: store intermediate signal values for score breakdown
            item["_semantic_sim"] = semantic
            item["_thompson_draw"] = thompson
            item["_freshness"] = freshness
            item["_status_bonus"] = status_bonus
            item["_thread_bonus"] = thread_bonus
            item["_cooccurrence"] = cooc
            item["_graph_proximity"] = graph_prox
            item["_composite"] = -composite
            return composite

        merged.sort(key=_keyfn)
        top_results = merged[:top_k]

        # Wave 34.5: assemble score breakdown metadata for top-k results
        for item in top_results:
            item["_score_breakdown"] = {
                "semantic": item.get("_semantic_sim", 0.0),
                "thompson": item.get("_thompson_draw", 0.0),
                "freshness": item.get("_freshness", 0.0),
                "status": item.get("_status_bonus", 0.0),
                "thread": item.get("_thread_bonus", 0.0),
                "cooccurrence": item.get("_cooccurrence", 0.0),
                "graph_proximity": item.get("_graph_proximity", 0.0),
                "composite": item.get("_composite", 0.0),
                "weights": dict(_W),
            }

        # Wave 33 A3: prediction error counters (fire-and-forget)
        try:
            if self._projections is not None:
                for item in top_results:
                    raw_semantic = float(item.get("score", 0.0))
                    if raw_semantic < 0.38:
                        entry_id = item.get("id", "")
                        if entry_id and entry_id in self._projections.memory_entries:
                            proj = self._projections.memory_entries[entry_id]
                            prev = proj.get("prediction_error_count", 0)
                            proj["prediction_error_count"] = prev + 1
                            proj["last_prediction_error_at"] = datetime.now(UTC).isoformat()
                            errors: list[str] = proj.get("prediction_error_queries", [])
                            errors.append(query[:200])
                            proj["prediction_error_queries"] = errors[-3:]
        except Exception:  # noqa: BLE001
            pass  # Never block search for prediction error bookkeeping

        # Wave 33 A5: query-result co-occurrence reinforcement (fire-and-forget)
        try:
            if self._projections is not None:
                from formicos.surface.projections import (  # noqa: PLC0415
                    CooccurrenceEntry,
                    cooccurrence_key,
                )

                result_ids = [item["id"] for item in top_results if "id" in item]
                now_iso = datetime.now(UTC).isoformat()
                for i, id_a in enumerate(result_ids):
                    for id_b in result_ids[i + 1 :]:
                        key = cooccurrence_key(id_a, id_b)
                        co_entry = self._projections.cooccurrence_weights.get(key)
                        if co_entry is None:
                            co_entry = CooccurrenceEntry(
                                weight=0.5, last_reinforced=now_iso, reinforcement_count=1,
                            )
                        else:
                            co_entry.weight = min(co_entry.weight * 1.05, 10.0)
                            co_entry.last_reinforced = now_iso
                            co_entry.reinforcement_count += 1
                        self._projections.cooccurrence_weights[key] = co_entry
        except Exception:  # noqa: BLE001
            pass  # Never block search for co-occurrence bookkeeping

        return top_results

    # ------------------------------------------------------------------
    # Wave 34 A1: tiered retrieval with auto-escalation
    # ------------------------------------------------------------------

    async def search_tiered(
        self,
        query: str,
        *,
        workspace_id: str,
        thread_id: str = "",
        source_colony_id: str = "",
        top_k: int = 5,
        tier: str = "auto",
    ) -> list[dict[str, Any]]:
        """Tiered retrieval with auto-escalation.

        Tiers:
          summary: ~15-20 tokens/result (title + one-line summary + confidence)
          standard: ~75 tokens/result (+ 200-char excerpt + domains + decay)
          full: ~200+ tokens/result (full content + metadata + co-occurrence)
          auto: start at summary, escalate if coverage is thin
        """
        # Fetch 2x top_k to have escalation headroom
        results = await self._search_thread_boosted(
            query,
            source_system="institutional_memory",
            canonical_type="",
            workspace_id=workspace_id,
            thread_id=thread_id,
            source_colony_id=source_colony_id,
            top_k=top_k * 2,
        )

        # Wave 41 B3: record retrieval access for compounding-curve measurement
        returned = results[:top_k]
        self._retrieval_metrics.record_access(
            [r.get("id", "") for r in returned if r.get("id")],
        )

        if tier != "auto":
            return self._format_tier(returned, tier)

        # Auto-escalation logic
        unique_sources = len(set(
            r.get("source_colony_id", "")
            for r in results
            if r.get("source_colony_id")
        ))
        top_score = max(
            (r.get("score", 0.0) for r in results), default=0.0,
        )

        # Wave 44: reactive forage trigger detection.
        # When coverage is thin, attach a ForageRequest signal to the
        # result metadata so the caller can hand off to the forager.
        # No network I/O happens here — this is detection only.
        forage_signal = self._detect_forage_trigger(
            returned, query=query, workspace_id=workspace_id,
            thread_id=thread_id, source_colony_id=source_colony_id,
            top_score=top_score, unique_sources=unique_sources,
        )

        if unique_sources >= 2 and top_score > 0.5:
            formatted = self._format_tier(returned, "summary")
        elif unique_sources >= 1 and top_score > 0.35:
            formatted = self._format_tier(returned, "standard")
        else:
            formatted = self._format_tier(returned, "full")

        # Attach forage signal as metadata on the result list
        if forage_signal is not None:
            for item in formatted:
                item["_forage_requested"] = True
            if formatted:
                formatted[0]["_forage_signal"] = forage_signal

        return formatted

    def _format_tier(
        self,
        results: list[dict[str, Any]],
        tier: str,
    ) -> list[dict[str, Any]]:
        """Format results at the specified detail tier."""
        formatted: list[dict[str, Any]] = []
        for r in results:
            item: dict[str, Any] = {
                "id": r.get("id", ""),
                "title": r.get("title", ""),
                "confidence_tier": r.get(
                    "_confidence_tier", "",
                ),
                "tier": tier,
            }
            if tier in ("summary", "standard", "full"):
                summary = r.get("summary", "")
                item["summary"] = (
                    summary[:100] if tier == "summary" else summary
                )

            if tier in ("standard", "full"):
                item["content_preview"] = r.get(
                    "content_preview", "",
                )[:200]
                item["domains"] = r.get("domains", [])
                item["decay_class"] = r.get(
                    "decay_class", "ephemeral",
                )

            if tier in ("standard", "full") and "_score_breakdown" in r:
                sb = r["_score_breakdown"]
                _SIGNAL_KEYS = (
                    "semantic", "thompson", "freshness",
                    "status", "thread", "cooccurrence",
                )
                weights = sb.get("weights", {})
                contributions = {
                    k: sb.get(k, 0.0) * weights.get(k, 0.0)
                    for k in _SIGNAL_KEYS
                }
                dominant = max(contributions, key=lambda k: contributions[k])
                item["ranking_explanation"] = (
                    f"semantic {sb.get('semantic', 0):.2f}, "
                    f"thompson {sb.get('thompson', 0):.2f}, "
                    f"freshness {sb.get('freshness', 0):.2f}, "
                    f"status {sb.get('status', 0):.2f}, "
                    f"thread {sb.get('thread', 0):.2f}, "
                    f"cooccurrence {sb.get('cooccurrence', 0):.2f} "
                    f"(dominant: {dominant})"
                )

            # Wave 45: competing hypothesis annotation
            if tier in ("standard", "full") and self._projections is not None:
                entry_id = r.get("id", "")
                if entry_id:
                    competing = self._projections.get_competing_context(
                        entry_id,
                    )
                    if competing:
                        item["competing_with"] = competing

            if tier == "full":
                item["content"] = r.get("content_preview", "")
                item["conf_alpha"] = r.get("conf_alpha", 5.0)
                item["conf_beta"] = r.get("conf_beta", 5.0)
                item["merged_from"] = r.get("merged_from", [])
                item["co_occurrence_cluster"] = (
                    self._get_cooccurrence_cluster(
                        r.get("id", ""), results,
                    )
                )
                item["score_breakdown"] = r.get("_score_breakdown", {})

            formatted.append(item)
        return formatted

    def _get_cooccurrence_cluster(
        self,
        entry_id: str,
        results: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Return co-occurrence cluster entries for a given result."""
        if self._projections is None or not entry_id:
            return []
        from formicos.surface.projections import cooccurrence_key  # noqa: PLC0415

        cluster: list[dict[str, Any]] = []
        for r in results:
            other_id = r.get("id", "")
            if not other_id or other_id == entry_id:
                continue
            key = cooccurrence_key(entry_id, other_id)
            co_entry = self._projections.cooccurrence_weights.get(key)
            if co_entry and co_entry.weight > 0.1:
                cluster.append({
                    "id": other_id,
                    "title": r.get("title", ""),
                    "weight": round(co_entry.weight, 3),
                })
        return cluster

    def _apply_operator_overlays(
        self, items: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Wave 39: Filter muted/invalidated entries and boost pinned entries.

        Operator overlays are local-first editorial actions that affect retrieval
        without mutating shared Beta confidence truth.
        """
        if self._projections is None:
            return items
        overlays = getattr(self._projections, "operator_overlays", None)
        if overlays is None:
            return items

        filtered: list[dict[str, Any]] = []
        for item in items:
            item_id = item.get("id", "")
            if not item_id:
                filtered.append(item)
                continue
            # Skip muted and invalidated entries from retrieval
            if item_id in overlays.muted_entries:
                continue
            if item_id in overlays.invalidated_entries:
                continue
            # Pinned entries get a retrieval preference boost
            if item_id in overlays.pinned_entries:
                item["_pinned"] = True
                item["_pin_boost"] = 1.0
            filtered.append(item)
        return filtered

    # ------------------------------------------------------------------
    # Wave 44: Reactive forage trigger detection
    # ------------------------------------------------------------------

    _FORAGE_SCORE_THRESHOLD = 0.35  # top-score below this triggers foraging
    _FORAGE_MIN_RESULTS = 2  # fewer unique sources triggers foraging

    def _detect_forage_trigger(
        self,
        results: list[dict[str, Any]],
        *,
        query: str,
        workspace_id: str,
        thread_id: str,
        source_colony_id: str,
        top_score: float,
        unique_sources: int,
    ) -> dict[str, Any] | None:
        """Detect whether retrieval results warrant a forage request.

        Returns a forage signal dict if coverage is thin, else None.
        This is detection only — no network I/O happens here.
        The caller decides whether to act on the signal.
        """
        should_forage = (
            top_score < self._FORAGE_SCORE_THRESHOLD
            or (unique_sources < self._FORAGE_MIN_RESULTS and len(results) < 3)
        )
        if not should_forage:
            return None

        # Extract domains from what little we found
        domains: list[str] = []
        for r in results[:5]:
            for d in r.get("domains", []):
                if d not in domains:
                    domains.append(d)

        log.info(
            "knowledge_catalog.forage_trigger_detected",
            workspace_id=workspace_id,
            query=query[:80],
            top_score=round(top_score, 3),
            unique_sources=unique_sources,
            result_count=len(results),
        )

        return {
            "workspace_id": workspace_id,
            "trigger": "reactive",
            "gap_description": (
                f"Low retrieval coverage for query: {query[:100]}"
            ),
            "domains": domains[:5],
            "topic": query,
            "thread_id": thread_id,
            "colony_id": source_colony_id,
        }

    async def list_all(
        self,
        *,
        source_system: str = "",
        canonical_type: str = "",
        workspace_id: str = "",
        source_colony_id: str = "",
        limit: int = 50,
    ) -> tuple[list[dict[str, Any]], int]:
        """List knowledge items from both backends. Returns (items, total)."""
        items: list[dict[str, Any]] = []

        # Institutional memory from projection state
        if (
            self._projections is not None
            and source_system in ("", "institutional_memory")
        ):
            for entry in self._projections.memory_entries.values():
                if (
                    workspace_id
                    and entry.get("workspace_id") != workspace_id
                    and entry.get("scope") != "global"
                ):
                    continue
                if source_colony_id and entry.get("source_colony_id") != source_colony_id:
                    continue
                if canonical_type and entry.get("entry_type") != canonical_type:
                    continue
                items.append(_normalize_institutional(entry))

        # Legacy skill bank via broad-query listing
        if (
            self._vector is not None
            and source_system in ("", "legacy_skill_bank")
            and canonical_type in ("", "skill")
        ):
            try:
                # Legacy skills live behind vector search rather than a replayed
                # projection, so use a broader fetch window than the UI page size
                # to keep `total` and filtered counts reasonably truthful.
                results = await self._vector.search(
                    collection=self._skill_collection,
                    query="skill knowledge technique pattern",
                    top_k=max(limit, _LEGACY_LIST_FETCH_K),
                )
                for hit in results:
                    item = _normalize_legacy_skill(hit)
                    if source_colony_id and item.get("source_colony_id") != source_colony_id:
                        continue
                    items.append(item)
            except Exception:  # noqa: BLE001
                log.debug("knowledge_catalog.legacy_list_failed")

        items.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        total = len(items)
        return items[:limit], total

    async def get_by_id(self, item_id: str) -> dict[str, Any] | None:
        """Retrieve a single item by ID.

        Guaranteed for institutional memory (projection lookup).
        Best-effort for legacy skills (semantic search fallback).
        """
        # Institutional memory: direct projection lookup
        if self._projections is not None:
            entry = self._projections.memory_entries.get(item_id)
            if entry is not None:
                item = _normalize_institutional(entry)
                item["content"] = entry.get("content", "")
                _enrich_trust_provenance(item, entry)
                return item

        # Legacy: best-effort — search by ID string, check for exact match
        if self._vector is not None:
            try:
                results = await self._vector.search(
                    collection=self._skill_collection,
                    query=item_id,
                    top_k=5,
                )
                for hit in results:
                    if getattr(hit, "id", "") == item_id:
                        item = _normalize_legacy_skill(hit)
                        item["content"] = getattr(hit, "content", "")
                        meta = hit.metadata if hasattr(hit, "metadata") else {}
                        _enrich_trust_provenance(item, meta)
                        return item
            except Exception:  # noqa: BLE001
                log.debug("knowledge_catalog.legacy_get_failed", id=item_id)

        return None

    async def _search_institutional(
        self,
        query: str,
        *,
        entry_type: str,
        workspace_id: str,
        thread_id: str = "",
        source_colony_id: str,
        top_k: int,
    ) -> list[dict[str, Any]]:
        if self._memory_store is None:
            return []
        try:
            results = await self._memory_store.search(
                query=query, entry_type=entry_type,
                workspace_id=workspace_id, thread_id=thread_id,
                top_k=top_k,
            )
            return [
                _normalize_institutional(
                    r, score=float(r.get("score", 0.0)),
                    similarity=float(r.get("similarity", r.get("score", 0.0))),
                )
                for r in results
                if (
                    not source_colony_id
                    or r.get("source_colony_id") == source_colony_id
                )
            ]
        except Exception:  # noqa: BLE001
            log.debug("knowledge_catalog.institutional_search_failed")
            return []

    async def _search_legacy(
        self, query: str, *, source_colony_id: str, top_k: int,
    ) -> list[dict[str, Any]]:
        if self._vector is None:
            return []
        try:
            results = await self._vector.search(
                collection=self._skill_collection,
                query=query, top_k=top_k,
            )
            items = [_normalize_legacy_skill(hit) for hit in results]
            if source_colony_id:
                items = [
                    item for item in items
                    if item.get("source_colony_id") == source_colony_id
                ]
            return items
        except Exception:  # noqa: BLE001
            log.debug("knowledge_catalog.legacy_search_failed")
            return []


async def _empty() -> list[dict[str, Any]]:
    return []


__all__ = ["KnowledgeCatalog", "KnowledgeItem"]
