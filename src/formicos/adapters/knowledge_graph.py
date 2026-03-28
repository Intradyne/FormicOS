"""SQLite-backed knowledge graph adapter for Archivist TKG tuples.

Stores entity nodes and bi-temporal relationship edges in the existing
``formicos.db`` file.  Emits KG events via an injected callback (Wave 14).

Schema follows algorithms.md §4 and the Graphiti-inspired bi-temporal model.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Coroutine
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import aiosqlite
import structlog

logger = structlog.get_logger(__name__)

# Callback type for KG event emission (Wave 14).
# Signature: async (event_type, **payload) -> None
KGEventCallback = Callable[..., Coroutine[Any, Any, None]]

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_SIMILARITY_THRESHOLD = 0.85
HIGH_CONFIDENCE_THRESHOLD = 0.95

VALID_ENTITY_TYPES = frozenset({
    "MODULE", "CONCEPT", "SKILL", "TOOL", "PERSON", "ORGANIZATION",
})

DEFAULT_PREDICATES = frozenset({
    "DEPENDS_ON", "ENABLES", "IMPLEMENTS",
    "VALIDATES", "MIGRATED_TO", "FAILED_ON",
    "SUPERSEDES",     # Wave 59.5: refinement — new content replaces old
    "DERIVED_FROM",   # Wave 59.5: merge — merged entry derives from sources
    "RELATED_TO",     # Wave 59.5: extraction co-occurrence within same colony
})

# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

_SCHEMA_SQL = """\
CREATE TABLE IF NOT EXISTS kg_nodes (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    summary TEXT,
    source_colony TEXT,
    workspace_id TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_kg_nodes_name ON kg_nodes(name);
CREATE INDEX IF NOT EXISTS idx_kg_nodes_type ON kg_nodes(entity_type);
CREATE INDEX IF NOT EXISTS idx_kg_nodes_ws   ON kg_nodes(workspace_id);

CREATE TABLE IF NOT EXISTS kg_edges (
    id TEXT PRIMARY KEY,
    from_node TEXT NOT NULL REFERENCES kg_nodes(id),
    to_node TEXT NOT NULL REFERENCES kg_nodes(id),
    predicate TEXT NOT NULL,
    confidence REAL DEFAULT 0.7,
    valid_at TEXT,
    invalid_at TEXT,
    source_colony TEXT,
    source_round INTEGER,
    workspace_id TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_kg_edges_from ON kg_edges(from_node);
CREATE INDEX IF NOT EXISTS idx_kg_edges_to   ON kg_edges(to_node);
CREATE INDEX IF NOT EXISTS idx_kg_edges_ws   ON kg_edges(workspace_id);
"""


# ---------------------------------------------------------------------------
# Data containers (plain dicts to avoid core type additions)
# ---------------------------------------------------------------------------


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _normalize(name: str) -> str:
    """Lowercase, collapse whitespace, replace underscores with spaces."""
    return re.sub(r"\s+", " ", name.strip().lower().replace("_", " "))


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------


class KnowledgeGraphAdapter:
    """SQLite adjacency-table knowledge graph.

    Satisfies the KG storage contract from Wave 13 plan.md §T3.
    Not a core port — injected directly by surface wiring.
    """

    def __init__(
        self,
        db_path: str | Path,
        embed_fn: Callable[[list[str]], list[list[float]]] | None = None,
        async_embed_fn: Callable[[list[str]], Any] | None = None,
        similarity_threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
        predicates: frozenset[str] | None = None,
        event_cb: KGEventCallback | None = None,
    ) -> None:
        self._db_path = Path(db_path)
        self._embed_fn = embed_fn
        self._async_embed_fn = async_embed_fn
        self._similarity_threshold = similarity_threshold
        self._predicates = predicates or DEFAULT_PREDICATES
        self._db: aiosqlite.Connection | None = None
        self._event_cb = event_cb

    async def _emit(self, event_type: str, **kwargs: Any) -> None:
        """Fire-and-forget KG event via the injected callback."""
        if self._event_cb is not None:
            try:
                await self._event_cb(event_type, **kwargs)
            except Exception:  # noqa: BLE001
                logger.warning("knowledge_graph.event_emit_failed", event_type=event_type)

    async def _embed_for_similarity(self, texts: list[str]) -> list[list[float]] | None:
        """Unified embedding helper: async > sync > None (ADR-025)."""
        if self._async_embed_fn is not None:
            return await self._async_embed_fn(texts)  # type: ignore[return-value]
        if self._embed_fn is not None:
            return self._embed_fn(texts)
        return None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def _ensure_db(self) -> aiosqlite.Connection:
        if self._db is not None:
            return self._db

        logger.info("knowledge_graph.opening", path=str(self._db_path))
        db = await aiosqlite.connect(str(self._db_path))
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("PRAGMA foreign_keys=ON")
        await db.executescript(_SCHEMA_SQL)
        await db.commit()
        db.row_factory = aiosqlite.Row  # pyright: ignore[reportAttributeAccessIssue]
        self._db = db
        return db

    async def close(self) -> None:
        if self._db is not None:
            await self._db.close()
            self._db = None

    # ------------------------------------------------------------------
    # Entity resolution (algorithms.md §4)
    # ------------------------------------------------------------------

    async def resolve_entity(
        self,
        name: str,
        entity_type: str,
        workspace_id: str,
        source_colony: str | None = None,
        summary: str | None = None,
    ) -> str:
        """Find or create an entity.  Returns the entity ID."""
        normalized = _normalize(name)

        # Step 1: Exact match on normalized name
        existing = await self._find_by_name(normalized, workspace_id)
        if existing is not None:
            return existing  # type: ignore[return-value]

        # Step 2: Fuzzy match via embedding similarity (ADR-025: async > sync > None)
        if self._async_embed_fn is not None or self._embed_fn is not None:
            candidates = await self._find_similar(
                name, workspace_id, self._similarity_threshold,
            )
            if candidates:
                # High-confidence auto-merge
                best_id, best_sim = candidates[0]
                if best_sim >= HIGH_CONFIDENCE_THRESHOLD:
                    # Emit merge event — new name resolved to existing entity
                    new_id = str(uuid4())  # conceptual merged-away ID
                    await self._emit(
                        "KnowledgeEntityMerged",
                        survivor_id=best_id, merged_id=new_id,
                        similarity_score=best_sim, merge_method="auto",
                        workspace_id=workspace_id,
                    )
                    return best_id

        # No match — create new entity
        return await self._create_entity(
            name, entity_type, workspace_id,
            source_colony=source_colony,
            summary=summary,
        )

    async def _find_by_name(
        self, normalized_name: str, workspace_id: str,
    ) -> str | None:
        db = await self._ensure_db()
        cursor = await db.execute(
            "SELECT id FROM kg_nodes WHERE LOWER(REPLACE(name, '_', ' ')) = ? AND workspace_id = ?",
            [normalized_name, workspace_id],
        )
        row = await cursor.fetchone()
        return row["id"] if row else None  # pyright: ignore[reportIndexIssue]

    async def _find_similar(
        self,
        name: str,
        workspace_id: str,
        threshold: float,
    ) -> list[tuple[str, float]]:
        """Return [(entity_id, similarity)] for candidates above threshold."""
        db = await self._ensure_db()

        cursor = await db.execute(
            "SELECT id, name FROM kg_nodes WHERE workspace_id = ?",
            [workspace_id],
        )
        rows = await cursor.fetchall()
        if not rows:
            return []

        # Embed query + all candidate names in one batch (ADR-025)
        candidate_names = [row["name"] for row in rows]  # pyright: ignore[reportIndexIssue]
        candidate_ids = [row["id"] for row in rows]  # pyright: ignore[reportIndexIssue]
        all_texts = [name] + candidate_names
        embeddings = await self._embed_for_similarity(all_texts)
        if embeddings is None:
            return []

        query_vec = embeddings[0]
        results: list[tuple[str, float]] = []
        for i, cand_vec in enumerate(embeddings[1:]):
            sim = _cosine_similarity(query_vec, cand_vec)
            if sim >= threshold:
                results.append((candidate_ids[i], sim))

        results.sort(key=lambda x: x[1], reverse=True)
        return results

    async def _create_entity(
        self,
        name: str,
        entity_type: str,
        workspace_id: str,
        source_colony: str | None = None,
        summary: str | None = None,
    ) -> str:
        db = await self._ensure_db()
        entity_id = str(uuid4())
        await db.execute(
            "INSERT INTO kg_nodes (id, name, entity_type, summary, source_colony, workspace_id) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            [entity_id, name, entity_type, summary, source_colony, workspace_id],
        )
        await db.commit()
        logger.info(
            "knowledge_graph.entity_created",
            entity_id=entity_id, name=name, entity_type=entity_type,
            workspace_id=workspace_id,
        )
        await self._emit(
            "KnowledgeEntityCreated",
            entity_id=entity_id, name=name, entity_type=entity_type,
            workspace_id=workspace_id, source_colony_id=source_colony,
        )
        return entity_id

    # ------------------------------------------------------------------
    # Edge CRUD (bi-temporal)
    # ------------------------------------------------------------------

    async def add_edge(
        self,
        from_node: str,
        to_node: str,
        predicate: str,
        workspace_id: str,
        confidence: float = 0.7,
        source_colony: str | None = None,
        source_round: int | None = None,
        valid_at: str | None = None,
    ) -> str:
        """Create a new edge.  Invalidates any existing edge with the same
        (from_node, to_node, predicate) that is still active."""
        db = await self._ensure_db()

        # Invalidate prior version of this relationship
        now = _now()
        await db.execute(
            "UPDATE kg_edges SET invalid_at = ? "
            "WHERE from_node = ? AND to_node = ? AND predicate = ? "
            "AND workspace_id = ? AND invalid_at IS NULL",
            [now, from_node, to_node, predicate, workspace_id],
        )

        edge_id = str(uuid4())
        await db.execute(
            "INSERT INTO kg_edges "
            "(id, from_node, to_node, predicate, confidence, valid_at, "
            " source_colony, source_round, workspace_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [edge_id, from_node, to_node, predicate, confidence,
             valid_at or now, source_colony, source_round, workspace_id],
        )
        await db.commit()
        await self._emit(
            "KnowledgeEdgeCreated",
            edge_id=edge_id, from_entity_id=from_node, to_entity_id=to_node,
            predicate=predicate, confidence=confidence,
            workspace_id=workspace_id, source_colony_id=source_colony,
            source_round=source_round,
        )
        return edge_id

    async def invalidate_edge(self, edge_id: str) -> None:
        """Mark an edge as no longer valid (soft-delete)."""
        db = await self._ensure_db()
        await db.execute(
            "UPDATE kg_edges SET invalid_at = ? WHERE id = ? AND invalid_at IS NULL",
            [_now(), edge_id],
        )
        await db.commit()

    # ------------------------------------------------------------------
    # BFS traversal (algorithms.md §4)
    # ------------------------------------------------------------------

    async def get_neighbors(
        self,
        entity_id: str,
        depth: int = 1,
        workspace_id: str | None = None,
        *,
        include_invalidated: bool = False,
        valid_before: str | None = None,
    ) -> list[dict[str, Any]]:
        """1-hop BFS from an entity.  Returns relationship triples.

        Wave 38: includes bi-temporal fields (valid_at, invalid_at, created_at)
        so operators can distinguish when the system learned a fact vs when
        it was considered true.

        Args:
            include_invalidated: If True, also return invalidated edges
                so temporal history is visible.
        """
        db = await self._ensure_db()

        query = (
            "SELECT e.id, e.predicate, e.from_node, e.to_node, e.confidence, "
            "       e.valid_at, e.invalid_at, e.created_at, "
            "       n1.name AS from_name, n2.name AS to_name "
            "FROM kg_edges e "
            "JOIN kg_nodes n1 ON e.from_node = n1.id "
            "JOIN kg_nodes n2 ON e.to_node = n2.id "
            "WHERE (e.from_node = ? OR e.to_node = ?) "
        )
        if not include_invalidated:
            query += "  AND e.invalid_at IS NULL"
        params: list[Any] = [entity_id, entity_id]
        if workspace_id:
            query += " AND e.workspace_id = ?"
            params.append(workspace_id)
        # Wave 60: temporal query — filter edges by creation time
        if valid_before:
            query += " AND (e.valid_at IS NULL OR e.valid_at <= ?)"
            params.append(valid_before)

        cursor = await db.execute(query, params)
        rows = await cursor.fetchall()

        return [
            {
                "id": row["id"],  # pyright: ignore[reportIndexIssue]
                "subject": row["from_name"],  # pyright: ignore[reportIndexIssue]
                "predicate": row["predicate"],  # pyright: ignore[reportIndexIssue]
                "object": row["to_name"],  # pyright: ignore[reportIndexIssue]
                "from_node": row["from_node"],  # pyright: ignore[reportIndexIssue]
                "to_node": row["to_node"],  # pyright: ignore[reportIndexIssue]
                "confidence": row["confidence"],  # pyright: ignore[reportIndexIssue]
                # Bi-temporal fields (Wave 38)
                "valid_at": row["valid_at"],  # pyright: ignore[reportIndexIssue]
                "invalid_at": row["invalid_at"],  # pyright: ignore[reportIndexIssue]
                "transaction_time": row["created_at"],  # pyright: ignore[reportIndexIssue]
            }
            for row in rows
        ]

    async def get_edge_history(
        self,
        from_node: str,
        to_node: str,
        predicate: str,
        workspace_id: str,
    ) -> list[dict[str, Any]]:
        """Return full temporal history of a relationship (all versions).

        Wave 38 bi-temporal surfacing: shows when facts were learned,
        when they were considered true, and when they were invalidated.
        """
        db = await self._ensure_db()
        cursor = await db.execute(
            "SELECT e.id, e.confidence, e.valid_at, e.invalid_at, e.created_at, "
            "       e.source_colony, e.source_round "
            "FROM kg_edges e "
            "WHERE e.from_node = ? AND e.to_node = ? AND e.predicate = ? "
            "  AND e.workspace_id = ? "
            "ORDER BY e.created_at ASC",
            [from_node, to_node, predicate, workspace_id],
        )
        rows = await cursor.fetchall()
        return [
            {
                "id": row["id"],  # pyright: ignore[reportIndexIssue]
                "confidence": row["confidence"],  # pyright: ignore[reportIndexIssue]
                "valid_at": row["valid_at"],  # pyright: ignore[reportIndexIssue]
                "invalid_at": row["invalid_at"],  # pyright: ignore[reportIndexIssue]
                "transaction_time": row["created_at"],  # pyright: ignore[reportIndexIssue]
                "source_colony": row["source_colony"],  # pyright: ignore[reportIndexIssue]
                "source_round": row["source_round"],  # pyright: ignore[reportIndexIssue]
                "is_current": row["invalid_at"] is None,  # pyright: ignore[reportIndexIssue]
            }
            for row in rows
        ]

    async def search_entities(
        self,
        text: str,
        workspace_id: str,
    ) -> list[dict[str, Any]]:
        """Find entities whose names appear in *text*.  Simple substring match."""
        db = await self._ensure_db()
        cursor = await db.execute(
            "SELECT id, name, entity_type, summary FROM kg_nodes WHERE workspace_id = ?",
            [workspace_id],
        )
        rows = await cursor.fetchall()

        normalized_text = _normalize(text)
        results: list[dict[str, Any]] = []
        for row in rows:
            if _normalize(row["name"]) in normalized_text:  # pyright: ignore[reportIndexIssue]
                results.append({  # pyright: ignore[reportUnknownMemberType]
                    "id": row["id"],  # pyright: ignore[reportIndexIssue]
                    "name": row["name"],  # pyright: ignore[reportIndexIssue]
                    "entity_type": row["entity_type"],  # pyright: ignore[reportIndexIssue]
                    "summary": row["summary"],  # pyright: ignore[reportIndexIssue]
                })
        return results

    # ------------------------------------------------------------------
    # Tuple ingestion (called from runner after compress)
    # ------------------------------------------------------------------

    async def ingest_tuples(
        self,
        tuples: list[dict[str, str]],
        workspace_id: str,
        source_colony: str | None = None,
        source_round: int | None = None,
    ) -> int:
        """Ingest Archivist TKG tuples into the knowledge graph.

        Each tuple is ``{"subject": ..., "predicate": ..., "object": ...,
        "subject_type": ..., "object_type": ...}``.

        Returns the number of edges created.
        """
        created = 0
        for t in tuples:
            subject = t.get("subject", "")
            predicate = t.get("predicate", "")
            obj = t.get("object", "")
            subject_type = t.get("subject_type", "CONCEPT")
            object_type = t.get("object_type", "CONCEPT")

            if not subject or not predicate or not obj:
                continue
            if predicate not in self._predicates:
                logger.warning(
                    "knowledge_graph.unknown_predicate",
                    predicate=predicate, subject=subject, object=obj,
                )
                continue

            from_id = await self.resolve_entity(
                subject, subject_type, workspace_id,
                source_colony=source_colony,
            )
            to_id = await self.resolve_entity(
                obj, object_type, workspace_id,
                source_colony=source_colony,
            )
            await self.add_edge(
                from_id, to_id, predicate, workspace_id,
                source_colony=source_colony,
                source_round=source_round,
            )
            created += 1

        logger.info(
            "knowledge_graph.tuples_ingested",
            count=created, workspace_id=workspace_id,
            source_colony=source_colony,
        )
        return created

    # ------------------------------------------------------------------
    # Wave 67.5: Embedding-based entity matching for PPR seeding
    # ------------------------------------------------------------------

    async def match_entities_by_embedding(
        self,
        query: str,
        workspace_id: str,
        *,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """Find KG entities semantically similar to query.

        Falls back to normalized substring matching on entity names
        if no embedding function is available.
        """
        db = await self._ensure_db()
        cursor = await db.execute(
            "SELECT id, name, entity_type, summary FROM kg_nodes WHERE workspace_id = ?",
            [workspace_id],
        )
        rows = list(await cursor.fetchall())
        if not rows:
            return []

        # Bound cost: skip embedding for large workspaces
        if len(rows) > 500 or (self._async_embed_fn is None and self._embed_fn is None):
            return self._substring_entity_match(query, rows, limit)

        candidate_texts = [
            f"{row['name']} {row['summary'] or ''}"  # pyright: ignore[reportIndexIssue]
            for row in rows
        ]
        all_texts = [query] + candidate_texts
        embeddings = await self._embed_for_similarity(all_texts)
        if embeddings is None:
            return self._substring_entity_match(query, rows, limit)

        query_vec = embeddings[0]
        scored: list[tuple[float, dict[str, Any]]] = []
        for i, cand_vec in enumerate(embeddings[1:]):
            sim = _cosine_similarity(query_vec, cand_vec)
            scored.append((sim, {
                "id": rows[i]["id"],  # pyright: ignore[reportIndexIssue]
                "name": rows[i]["name"],  # pyright: ignore[reportIndexIssue]
                "entity_type": rows[i]["entity_type"],  # pyright: ignore[reportIndexIssue]
                "score": sim,
            }))
        scored.sort(key=lambda x: -x[0])
        return [item for _, item in scored[:limit]]

    @staticmethod
    def _substring_entity_match(
        query: str,
        rows: list[Any],
        limit: int,
    ) -> list[dict[str, Any]]:
        """Fallback: substring matching on entity names."""
        normalized_query = _normalize(query)
        results: list[dict[str, Any]] = []
        for row in rows:
            if _normalize(row["name"]) in normalized_query:  # pyright: ignore[reportIndexIssue]
                results.append({
                    "id": row["id"],  # pyright: ignore[reportIndexIssue]
                    "name": row["name"],  # pyright: ignore[reportIndexIssue]
                    "entity_type": row["entity_type"],  # pyright: ignore[reportIndexIssue]
                    "score": 1.0,
                })
                if len(results) >= limit:
                    break
        return results

    # ------------------------------------------------------------------
    # Wave 67.5: Personalized PageRank (ADR-050 D1)
    # ------------------------------------------------------------------

    async def personalized_pagerank(
        self,
        seed_ids: list[str],
        workspace_id: str,
        *,
        damping: float = 0.5,
        iterations: int = 20,
    ) -> dict[str, float]:
        """Iterative PPR from seed entities.

        Builds a bounded local adjacency list by expanding outward from seeds
        up to 3 hops, then runs power iteration with restart bias toward seeds.
        Returns {entity_id: score} normalized so max = 1.0.
        """
        if not seed_ids:
            return {}

        # Build local adjacency via bounded expansion (3 hops)
        adj_sets: dict[str, set[str]] = {}
        frontier = set(seed_ids)
        visited: set[str] = set()

        for _hop in range(3):
            next_frontier: set[str] = set()
            for node_id in frontier:
                if node_id in visited:
                    continue
                visited.add(node_id)
                try:
                    neighbors = await self.get_neighbors(
                        node_id, workspace_id=workspace_id,
                    )
                except Exception:  # noqa: BLE001
                    continue
                node_adj = adj_sets.setdefault(node_id, set())
                for nbr in neighbors:
                    other = (
                        nbr["to_node"] if nbr["from_node"] == node_id
                        else nbr["from_node"]
                    )
                    node_adj.add(other)
                    adj_sets.setdefault(other, set()).add(node_id)
                    next_frontier.add(other)
            frontier = next_frontier - visited

        # Convert to lists for iteration; sets above prevent duplicate
        # edges when the same relationship is discovered from both endpoints.
        adjacency: dict[str, list[str]] = {k: list(v) for k, v in adj_sets.items()}
        all_nodes = set(adjacency.keys())
        if not all_nodes:
            return {}

        # Initialize reset vector: uniform over seeds
        reset: dict[str, float] = {}
        valid_seeds = [s for s in seed_ids if s in all_nodes]
        if not valid_seeds:
            return {}
        seed_weight = 1.0 / len(valid_seeds)
        for s in valid_seeds:
            reset[s] = seed_weight

        # Initialize PR scores
        pr: dict[str, float] = {n: reset.get(n, 0.0) for n in all_nodes}

        # Power iteration
        for _ in range(iterations):
            new_pr: dict[str, float] = {}
            for node in all_nodes:
                incoming_mass = 0.0
                for neighbor in adjacency.get(node, []):
                    degree = len(adjacency.get(neighbor, []))
                    if degree > 0:
                        incoming_mass += pr.get(neighbor, 0.0) / degree
                new_pr[node] = (1 - damping) * reset.get(node, 0.0) + damping * incoming_mass
            pr = new_pr

        # Normalize max score to 1.0
        max_score = max(pr.values()) if pr else 1.0
        if max_score > 0:
            pr = {k: v / max_score for k, v in pr.items()}

        return pr

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    async def stats(self, workspace_id: str | None = None) -> dict[str, int]:
        """Return node/edge counts."""
        db = await self._ensure_db()
        if workspace_id:
            params: list[Any] = [workspace_id]
            cur_n = await db.execute(
                "SELECT COUNT(*) FROM kg_nodes WHERE workspace_id = ?", params,
            )
            cur_e = await db.execute(
                "SELECT COUNT(*) FROM kg_edges WHERE workspace_id = ? AND invalid_at IS NULL",
                params,
            )
        else:
            params = []
            cur_n = await db.execute("SELECT COUNT(*) FROM kg_nodes")
            cur_e = await db.execute(
                "SELECT COUNT(*) FROM kg_edges WHERE invalid_at IS NULL",
            )
        row_n = await cur_n.fetchone()
        row_e = await cur_e.fetchone()
        return {
            "nodes": row_n[0] if row_n else 0,  # pyright: ignore[reportIndexIssue]
            "edges": row_e[0] if row_e else 0,  # pyright: ignore[reportIndexIssue]
        }


# ---------------------------------------------------------------------------
# Math helper
# ---------------------------------------------------------------------------


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)
