"""Institutional memory store -- Qdrant projection from memory events (Wave 26).

Maintains the ``institutional_memory`` collection as a derived index.
Rebuilt from event replay on startup.  Updated live via ``emit_and_broadcast``
which calls ``sync_entry`` after each memory event (Wave 26.5).

Search uses ``qdrant-client`` directly -- NOT generic ``VectorPort.search()``
-- so that ``status``, ``entry_type``, and ``workspace_id`` filters are applied
server-side at query time.  Rejected entries never appear in results.
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

    # ------------------------------------------------------------------
    # Write path (Track A owns these -- stubs for co-ownership)
    # ------------------------------------------------------------------

    async def upsert_entry(self, entry: dict[str, Any]) -> None:
        """Upsert a memory entry into Qdrant with dense + sparse vectors."""
        entry_id = entry.get("id", "")
        if not entry_id:
            return

        embed_text = (
            f"{entry.get('title', '')}. "
            f"{entry.get('content', '')} "
            f"{entry.get('summary', '')} "
            f"tools: {' '.join(entry.get('tool_refs', []))} "
            f"domains: {' '.join(entry.get('domains', []))}"
        )
        # Wave 58: include trajectory tool sequence in embedding text
        traj = entry.get("trajectory_data", [])
        if traj:
            tool_seq = " -> ".join(str(s.get("tool", "")) for s in traj[:20])
            embed_text += f" trajectory: {tool_seq}"

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
                "thread_id": entry.get("thread_id", ""),
                "created_at": entry.get("created_at", ""),
                "trajectory_data": entry.get("trajectory_data", []),
                "sub_type": str(entry.get("sub_type", "")),
            },
        )
        await self._vector.upsert(collection=COLLECTION_NAME, docs=[doc])

    async def sync_entry(
        self,
        entry_id: str,
        projection_entries: dict[str, dict[str, Any]],
    ) -> None:
        """Sync a single entry from projection state into Qdrant.

        Single mechanism for keeping Qdrant consistent with event truth.
        Full re-upsert -- no partial payload update shortcut.
        """
        entry = projection_entries.get(entry_id)
        if entry is None:
            log.warning("memory_store.sync_entry.missing", entry_id=entry_id)
            return
        if entry.get("status") == "rejected":
            await self._vector.delete(collection=COLLECTION_NAME, ids=[entry_id])
            return
        await self.upsert_entry(entry)

    async def rebuild_from_projection(
        self,
        projection_entries: dict[str, dict[str, Any]],
    ) -> int:
        """Rebuild the entire Qdrant collection from projection state.

        Called once at startup after event replay completes.
        Returns the number of entries upserted.
        """
        count = 0
        for _entry_id, entry in projection_entries.items():
            if entry.get("status") == "rejected":
                continue
            await self.upsert_entry(entry)
            count += 1
        log.info("memory_store.rebuilt", entries=count)
        return count

    # ------------------------------------------------------------------
    # Search path (Track B owns this)
    # ------------------------------------------------------------------

    async def search(
        self,
        query: str,
        *,
        entry_type: str = "",
        workspace_id: str = "",
        thread_id: str = "",
        exclude_statuses: list[str] | None = None,
        top_k: int = 5,
        include_global: bool = True,
    ) -> list[dict[str, Any]]:
        """Search institutional memory with payload-filtered Qdrant queries.

        Prefers ``qdrant-client`` directly for server-side filtering.
        Falls back to ``VectorPort.search()`` with Python post-filtering.
        Rejected entries are never returned.

        Wave 50: when *include_global* is True (default) and *workspace_id*
        is given, performs a two-phase search: workspace-scoped first, then
        global entries. Global entries receive a slight relevance discount.
        """
        if exclude_statuses is None:
            exclude_statuses = ["rejected", "stale"]

        qdrant_client = getattr(self._vector, "_client", None)
        if qdrant_client is not None:
            results = await self._search_qdrant_filtered(
                qdrant_client, query,
                entry_type=entry_type, workspace_id=workspace_id,
                thread_id=thread_id,
                exclude_statuses=exclude_statuses, top_k=top_k,
            )
        else:
            results = await self._search_fallback(
                query,
                entry_type=entry_type,
                workspace_id=workspace_id,
                thread_id=thread_id,
                exclude_statuses=exclude_statuses,
                top_k=top_k,
            )

        # Wave 50: two-phase global search
        if include_global and workspace_id:
            remaining = top_k - len(results)
            if remaining > 0:
                results = await self._merge_global_results(
                    query, results, remaining,
                    entry_type=entry_type,
                    exclude_statuses=exclude_statuses,
                )
        return results

    async def _merge_global_results(
        self,
        query: str,
        workspace_results: list[dict[str, Any]],
        budget: int,
        *,
        entry_type: str,
        exclude_statuses: list[str],
    ) -> list[dict[str, Any]]:
        """Fetch global-scoped entries and merge with workspace results (Wave 50).

        Global entries receive a 0.9x score discount to prevent crowding out
        workspace-specific knowledge.
        """
        # Search without workspace filter to find global entries
        qdrant_client = getattr(self._vector, "_client", None)
        if qdrant_client is not None:
            global_hits = await self._search_qdrant_filtered(
                qdrant_client, query,
                entry_type=entry_type, workspace_id="",
                exclude_statuses=exclude_statuses, top_k=budget * 2,
            )
        else:
            global_hits = await self._search_fallback(
                query,
                entry_type=entry_type, workspace_id="",
                exclude_statuses=exclude_statuses, top_k=budget * 2,
            )

        # Filter to only global-scoped and apply discount
        ws_ids = {r.get("id") for r in workspace_results}
        for hit in global_hits:
            if hit.get("id") in ws_ids:
                continue
            # Only include entries with scope=global
            if hit.get("scope") != "global":
                continue
            hit["score"] = float(hit.get("score", 0.0)) * 0.9
            workspace_results.append(hit)

        return self._rank_and_trim(workspace_results, len(ws_ids) + budget)

    async def _search_qdrant_filtered(
        self,
        client: Any,  # noqa: ANN401 -- AsyncQdrantClient
        query: str,
        *,
        entry_type: str,
        workspace_id: str,
        thread_id: str = "",
        exclude_statuses: list[str],
        top_k: int,
    ) -> list[dict[str, Any]]:
        """Payload-filtered hybrid search via qdrant-client directly."""
        from qdrant_client import models  # noqa: PLC0415

        must_conditions: list[models.FieldCondition] = []
        should_conditions: list[models.FieldCondition] = []

        if exclude_statuses:
            must_conditions.append(
                models.FieldCondition(
                    key="status",
                    match=models.MatchExcept(  # pyright: ignore[reportCallIssue]
                        **{"except": exclude_statuses},
                    ),
                ),
            )
        if entry_type:
            must_conditions.append(
                models.FieldCondition(
                    key="entry_type",
                    match=models.MatchValue(value=entry_type),
                ),
            )
        if workspace_id:
            must_conditions.append(
                models.FieldCondition(
                    key="workspace_id",
                    match=models.MatchValue(value=workspace_id),
                ),
            )
        # Wave 29: thread_id filter as a should clause (boost, not exclude)
        if thread_id:
            should_conditions.append(
                models.FieldCondition(
                    key="thread_id",
                    match=models.MatchValue(value=thread_id),
                ),
            )

        filter_kwargs: dict[str, Any] = {}
        if must_conditions:
            filter_kwargs["must"] = must_conditions
        if should_conditions:
            filter_kwargs["should"] = should_conditions
        query_filter = models.Filter(**filter_kwargs) if filter_kwargs else None

        # Embed the query using the vector port's embedding pipeline
        embed_fn = getattr(self._vector, "_embed_texts", None)
        if embed_fn is None:
            log.warning("memory_store.search.no_embed")
            return []

        vectors = await embed_fn([query], is_query=True)
        if not vectors or not vectors[0]:
            return []

        # Ensure collection exists
        ensure = getattr(self._vector, "ensure_collection", None)
        if ensure is not None:
            await ensure(COLLECTION_NAME)

        # Try hybrid search first, fall back to dense-only
        embed_client = getattr(self._vector, "_embed_client", None)
        overfetch = top_k * 4

        try:
            if embed_client is not None:
                # Hybrid: dense + BM25 sparse with RRF fusion
                result = await client.query_points(
                    collection_name=COLLECTION_NAME,
                    prefetch=[
                        models.Prefetch(
                            query=vectors[0],
                            using="dense",
                            limit=overfetch,
                        ),
                        models.Prefetch(
                            query=models.Document(
                                text=query,
                                model="Qdrant/bm25",
                            ),
                            using="sparse",
                            limit=overfetch,
                        ),
                    ],
                    query=models.FusionQuery(fusion=models.Fusion.RRF),
                    query_filter=query_filter,
                    limit=top_k * 2,
                    with_payload=True,
                )
            else:
                # Dense-only
                result = await client.query_points(
                    collection_name=COLLECTION_NAME,
                    query=vectors[0],
                    query_filter=query_filter,
                    limit=top_k * 2,
                    with_payload=True,
                )
        except Exception:
            log.warning("memory_store.qdrant_search_failed", exc_info=True)
            return await self._search_fallback(
                query,
                entry_type=entry_type,
                workspace_id=workspace_id,
                exclude_statuses=exclude_statuses,
                top_k=top_k,
            )

        hits = self._points_to_results(result.points)
        return self._rank_and_trim(hits, top_k)

    async def _search_fallback(
        self,
        query: str,
        *,
        entry_type: str,
        workspace_id: str,
        thread_id: str = "",
        exclude_statuses: list[str],
        top_k: int,
    ) -> list[dict[str, Any]]:
        """Fallback: VectorPort.search() + Python post-filter."""
        try:
            results = await self._vector.search(
                collection=COLLECTION_NAME,
                query=query,
                top_k=top_k * 3,
            )
        except Exception:
            log.warning("memory_store.fallback_search_failed", exc_info=True)
            return []

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
                "similarity": hit.score,  # raw vector similarity
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
                "scan_status": meta.get("scan_status", "pending"),
                "created_at": meta.get("created_at", ""),
            })

        return self._rank_and_trim(filtered, top_k)

    @staticmethod
    def _points_to_results(points: Any) -> list[dict[str, Any]]:  # noqa: ANN401
        """Convert Qdrant ScoredPoint list to result dicts."""
        results: list[dict[str, Any]] = []
        for point in points:
            payload: dict[str, Any] = dict(point.payload) if point.payload else {}
            # Use _original_id from payload when available (matches projection
            # entry IDs). Qdrant stores UUID5-hashed point IDs, but the
            # original mem-colony-* ID is preserved in payload by the adapter.
            original_id = str(payload.pop("_original_id", point.id)) if point.id else ""
            raw_score = float(point.score) if point.score else 0.0
            results.append({
                "id": original_id,
                "score": raw_score,
                "similarity": raw_score,  # raw vector similarity before composite ranking
                "entry_type": payload.get("entry_type", "skill"),
                "status": payload.get("status", "candidate"),
                "polarity": payload.get("polarity", "positive"),
                "title": payload.get("title", ""),
                "content": payload.get("content", ""),
                "summary": payload.get("summary", ""),
                "source_colony_id": payload.get("source_colony_id", ""),
                "confidence": payload.get("confidence", 0.5),
                "domains": payload.get("domains", []),
                "tool_refs": payload.get("tool_refs", []),
                "scan_status": payload.get("scan_status", "pending"),
                "created_at": payload.get("created_at", ""),
            })
        return results

    @staticmethod
    def _rank_and_trim(
        results: list[dict[str, Any]],
        top_k: int,
    ) -> list[dict[str, Any]]:
        """Sort by raw Qdrant score and truncate.

        Wave 57 audit: previously applied a 4-signal composite formula here
        (0.40*semantic + 0.25*thompson + 0.15*freshness + 0.12*status) that
        competed with knowledge_catalog's canonical 6-signal composite.
        The double-ranking could discard entries that the canonical formula
        would rank higher.

        Now sorts by raw score only (Qdrant's cosine similarity or RRF
        fusion score). The canonical composite ranking belongs exclusively
        in knowledge_catalog._composite_key().
        """
        results.sort(key=lambda e: float(e.get("score", 0.0)), reverse=True)
        return results[:top_k]


__all__ = ["COLLECTION_NAME", "MemoryStore"]
