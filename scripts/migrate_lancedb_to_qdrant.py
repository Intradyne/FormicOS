"""One-shot LanceDB → Qdrant migration (ADR-013).

Reads all LanceDB tables, preserves vectors and metadata, uploads to Qdrant
without re-embedding. Verifies source count == destination count.

Usage:
    python scripts/migrate_lancedb_to_qdrant.py [--data-dir ./data] [--qdrant-url http://localhost:6333]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


async def migrate(
    data_dir: str = "./data",
    qdrant_url: str = "http://localhost:6333",
) -> None:
    """Migrate all LanceDB tables to Qdrant collections."""
    import lancedb  # pyright: ignore[reportMissingTypeStubs]
    from qdrant_client import AsyncQdrantClient, models

    lance_path = Path(data_dir) / "vectors"
    if not lance_path.exists():
        logger.info("migration.no_lancedb", path=str(lance_path))
        return

    db: Any = lancedb.connect(str(lance_path))  # pyright: ignore[reportUnknownMemberType]
    table_names_resp: Any = db.list_tables()  # pyright: ignore[reportUnknownMemberType]
    if hasattr(table_names_resp, "tables"):
        table_names: list[str] = table_names_resp.tables  # pyright: ignore[reportUnknownMemberType]
    else:
        table_names = list(table_names_resp)  # pyright: ignore[reportUnknownArgumentType]

    if not table_names:
        logger.info("migration.empty_lancedb")
        return

    qdrant = AsyncQdrantClient(url=qdrant_url, prefer_grpc=True)

    for table_name in table_names:
        table: Any = db.open_table(table_name)  # pyright: ignore[reportUnknownMemberType]
        rows: list[dict[str, Any]] = table.to_list()  # pyright: ignore[reportUnknownMemberType,reportUnknownVariableType]
        if not rows:
            logger.info("migration.empty_table", table=table_name)
            continue

        # Determine vector dimensions from first row
        first_vec = rows[0].get("vector", [])
        dims = len(first_vec) if hasattr(first_vec, "__len__") else 384

        # Create Qdrant collection if needed
        if not await qdrant.collection_exists(table_name):
            await qdrant.create_collection(
                table_name,
                vectors_config=models.VectorParams(
                    size=dims, distance=models.Distance.COSINE,
                ),
            )

        # Convert and upload
        points: list[models.PointStruct] = []
        for row in rows:
            vec = row.get("vector", [])
            if hasattr(vec, "tolist"):
                vec = vec.tolist()  # pyright: ignore[reportUnknownMemberType]
            else:
                vec = list(vec)

            # Build payload from all non-vector fields
            payload: dict[str, Any] = {}
            for k, v in row.items():
                if k == "vector":
                    continue
                # Parse JSON metadata if stored as string
                if k == "metadata" and isinstance(v, str):
                    try:
                        payload.update(json.loads(v))
                    except json.JSONDecodeError:
                        payload[k] = v
                else:
                    payload[k] = v

            point_id = str(row.get("id", len(points)))
            points.append(models.PointStruct(
                id=point_id,
                vector=vec,
                payload=payload,
            ))

        if points:
            await qdrant.upsert(table_name, points=points, wait=True)

        # Verify count
        info = await qdrant.get_collection(table_name)
        expected = len(rows)
        actual = info.points_count or 0
        if actual != expected:
            logger.error(
                "migration.count_mismatch",
                table=table_name, expected=expected, actual=actual,
            )
            sys.exit(1)

        logger.info(
            "migration.table_complete",
            table=table_name, points=expected,
        )

    await qdrant.close()
    logger.info("migration.complete")


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Migrate LanceDB to Qdrant")
    parser.add_argument(
        "--data-dir", default="./data",
        help="FormicOS data directory (default: ./data)",
    )
    parser.add_argument(
        "--qdrant-url", default="http://localhost:6333",
        help="Qdrant endpoint URL (default: http://localhost:6333)",
    )
    args = parser.parse_args()
    asyncio.run(migrate(data_dir=args.data_dir, qdrant_url=args.qdrant_url))


if __name__ == "__main__":
    main()
