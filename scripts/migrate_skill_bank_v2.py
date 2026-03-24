#!/usr/bin/env python3
"""One-shot migration: skill_bank → skill_bank_v2 (Wave 13).

Creates the ``skill_bank_v2`` collection with named dense (1024-dim COSINE)
and sparse (IDF-weighted BM25) vector configs, re-embeds all existing skills
via the Qwen3-Embedding sidecar, upserts with both vector types, and swaps
the ``skill_bank_active`` alias.

Usage::

    python scripts/migrate_skill_bank_v2.py [--qdrant-url URL] [--embed-url URL] [--old-collection NAME]

Requirements:
    - Qdrant running (default: localhost:6333)
    - Qwen3-Embedding sidecar running (default: localhost:8200)
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time

import httpx
import structlog
from qdrant_client import QdrantClient, models

# Re-use the embedding helper from the adapter
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent / "src"))
from formicos.adapters.embedding_qwen3 import Qwen3Embedder  # noqa: E402

logger = structlog.get_logger("migrate_skill_bank_v2")

OLD_COLLECTION = "skill_bank"
NEW_COLLECTION = "skill_bank_v2"
ALIAS = "skill_bank_active"

PAYLOAD_INDEXES: list[tuple[str, models.PayloadSchemaType]] = [
    ("namespace", models.PayloadSchemaType.KEYWORD),
    ("confidence", models.PayloadSchemaType.FLOAT),
    ("algorithm_version", models.PayloadSchemaType.KEYWORD),
    ("extracted_at", models.PayloadSchemaType.DATETIME),
    ("source_colony", models.PayloadSchemaType.KEYWORD),
    ("source_colony_id", models.PayloadSchemaType.KEYWORD),
]


def create_collection(client: QdrantClient) -> None:
    """Create skill_bank_v2 with named dense + sparse vector config."""
    if client.collection_exists(NEW_COLLECTION):
        logger.info("collection_exists", collection=NEW_COLLECTION)
        return

    client.create_collection(
        collection_name=NEW_COLLECTION,
        vectors_config={
            "dense": models.VectorParams(
                size=1024,
                distance=models.Distance.COSINE,
            ),
        },
        sparse_vectors_config={
            "sparse": models.SparseVectorParams(
                modifier=models.Modifier.IDF,
            ),
        },
    )
    logger.info("collection_created", collection=NEW_COLLECTION)

    # Create payload indexes
    for field, schema in PAYLOAD_INDEXES:
        try:
            if field == "namespace":
                client.create_payload_index(
                    NEW_COLLECTION,
                    field,
                    field_schema=models.KeywordIndexParams(
                        type="keyword",  # type: ignore[arg-type]
                        is_tenant=True,
                    ),
                )
            else:
                client.create_payload_index(NEW_COLLECTION, field, schema)
        except Exception:  # noqa: BLE001
            pass  # idempotent
    logger.info("payload_indexes_created", collection=NEW_COLLECTION)


async def migrate_points(
    client: QdrantClient,
    embedder: Qwen3Embedder,
    old_collection: str,
) -> int:
    """Scroll old collection, re-embed, upsert to new collection."""
    if not client.collection_exists(old_collection):
        logger.warning("old_collection_missing", collection=old_collection)
        return 0

    # Scroll all points from old collection
    points_migrated = 0
    offset = None
    batch_size = 50

    while True:
        scroll_result = client.scroll(
            collection_name=old_collection,
            limit=batch_size,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        points, next_offset = scroll_result

        if not points:
            break

        # Extract text from each point's payload
        texts: list[str] = []
        valid_points: list[object] = []
        for p in points:
            payload = p.payload or {}
            text = str(
                payload.get("text")
                or payload.get("text_preview")
                or payload.get("description")
                or ""
            )
            if text.strip():
                texts.append(text)
                valid_points.append(p)

        if texts:
            # Re-embed with Qwen3-Embedding (document mode, no instruction prefix)
            dense_vectors = await embedder.embed(texts, is_query=False)

            if len(dense_vectors) == len(valid_points):
                upsert_points: list[models.PointStruct] = []
                for p, dense_vec, text in zip(valid_points, dense_vectors, texts, strict=True):
                    upsert_points.append(
                        models.PointStruct(
                            id=p.id,  # type: ignore[union-attr]
                            payload=dict(p.payload) if p.payload else {},  # type: ignore[union-attr]
                            vector={
                                "dense": dense_vec,
                                "sparse": models.Document(
                                    text=text,
                                    model="Qdrant/bm25",
                                ),
                            },
                        )
                    )

                client.upsert(
                    collection_name=NEW_COLLECTION,
                    points=upsert_points,
                    wait=True,
                )
                points_migrated += len(upsert_points)
                logger.info("batch_migrated", count=len(upsert_points), total=points_migrated)

        if next_offset is None:
            break
        offset = next_offset

    return points_migrated


def swap_alias(client: QdrantClient) -> None:
    """Atomic alias swap: skill_bank_active → skill_bank_v2."""
    try:
        client.update_collection_aliases(
            change_aliases_operations=[
                # Delete old alias binding (ignore if missing)
                models.DeleteAliasOperation(
                    delete_alias=models.DeleteAlias(alias_name=ALIAS),
                ),
            ],
        )
    except Exception:  # noqa: BLE001
        pass  # alias didn't exist yet

    client.update_collection_aliases(
        change_aliases_operations=[
            models.CreateAliasOperation(
                create_alias=models.CreateAlias(
                    collection_name=NEW_COLLECTION,
                    alias_name=ALIAS,
                ),
            ),
        ],
    )
    logger.info("alias_swapped", alias=ALIAS, target=NEW_COLLECTION)


async def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate skill_bank to v2 (1024-dim hybrid)")
    parser.add_argument("--qdrant-url", default="http://localhost:6333")
    parser.add_argument("--embed-url", default="http://localhost:8200/v1/embeddings")
    parser.add_argument("--old-collection", default=OLD_COLLECTION)
    parser.add_argument("--drop-old", action="store_true", help="Drop old collection after migration")
    args = parser.parse_args()

    client = QdrantClient(url=args.qdrant_url)
    embedder = Qwen3Embedder(url=args.embed_url)

    t0 = time.monotonic()

    # Step 1: Create new collection
    create_collection(client)

    # Step 2: Re-embed and migrate
    count = await migrate_points(client, embedder, args.old_collection)
    logger.info("migration_complete", points=count, elapsed=f"{time.monotonic() - t0:.2f}s")

    # Step 3: Swap alias
    swap_alias(client)

    # Step 4: Optionally drop old collection
    if args.drop_old and client.collection_exists(args.old_collection):
        client.delete_collection(args.old_collection)
        logger.info("old_collection_dropped", collection=args.old_collection)

    await embedder.close()
    client.close()

    logger.info(
        "done",
        new_collection=NEW_COLLECTION,
        alias=ALIAS,
        points=count,
        elapsed=f"{time.monotonic() - t0:.2f}s",
    )


if __name__ == "__main__":
    asyncio.run(main())
