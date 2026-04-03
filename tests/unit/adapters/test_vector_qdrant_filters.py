"""Tests for Qdrant payload filter behavior (ADR-013).

Verifies that payload indexes are created with correct types and that
metadata fields are properly stored for filtering.
"""

from __future__ import annotations

import hashlib
import struct
from typing import Any
from unittest.mock import AsyncMock, MagicMock, call

import pytest
from qdrant_client import models

from formicos.adapters.vector_qdrant import QdrantVectorPort
from formicos.core.types import VectorDocument


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _embed(texts: list[str], *, is_query: bool = False) -> list[list[float]]:
    vectors: list[list[float]] = []
    for text in texts:
        digest = hashlib.sha256(text.encode()).digest()
        raw = list(struct.unpack("<8f", digest[:32]))
        mag = max(sum(x * x for x in raw) ** 0.5, 1e-9)
        vectors.append([x / mag for x in raw])
    return vectors


def _doc(id_: str, content: str, **meta: Any) -> VectorDocument:
    return VectorDocument(id=id_, content=content, metadata=meta)


# ---------------------------------------------------------------------------
# Payload index creation
# ---------------------------------------------------------------------------


class TestPayloadIndexes:
    """Verify that ensure_collection creates the required payload indexes."""

    @pytest.mark.anyio()
    async def test_namespace_index_is_tenant(self) -> None:
        port = QdrantVectorPort(embed_fn=_embed)
        port._client = AsyncMock()
        port._client.collection_exists = AsyncMock(return_value=False)
        port._client.create_collection = AsyncMock()
        port._client.create_payload_index = AsyncMock()

        await port.ensure_collection("col")

        # Find the namespace index call
        namespace_calls = [
            c for c in port._client.create_payload_index.call_args_list
            if c.args[1] == "namespace" or (len(c.args) > 1 and c.args[1] == "namespace")
        ]
        assert len(namespace_calls) == 1
        # Verify is_tenant=True via KeywordIndexParams
        kw = namespace_calls[0].kwargs.get("field_schema")
        assert kw is not None
        assert isinstance(kw, models.KeywordIndexParams)
        assert kw.is_tenant is True

    @pytest.mark.anyio()
    async def test_confidence_index_is_float(self) -> None:
        port = QdrantVectorPort(embed_fn=_embed)
        port._client = AsyncMock()
        port._client.collection_exists = AsyncMock(return_value=False)
        port._client.create_collection = AsyncMock()
        port._client.create_payload_index = AsyncMock()

        await port.ensure_collection("col")

        # Find confidence index call
        conf_calls = [
            c for c in port._client.create_payload_index.call_args_list
            if len(c.args) > 2 and c.args[2] == models.PayloadSchemaType.FLOAT
        ]
        assert len(conf_calls) == 1
        assert conf_calls[0].args[1] == "confidence"

    @pytest.mark.anyio()
    async def test_all_seven_indexes_created(self) -> None:
        port = QdrantVectorPort(embed_fn=_embed)
        port._client = AsyncMock()
        port._client.collection_exists = AsyncMock(return_value=False)
        port._client.create_collection = AsyncMock()
        port._client.create_payload_index = AsyncMock()

        await port.ensure_collection("col")

        indexed_fields = {
            c.args[1]
            for c in port._client.create_payload_index.call_args_list
        }
        assert indexed_fields == {
            "namespace", "confidence", "algorithm_version",
            "extracted_at", "source_colony", "source_colony_id",
            "hierarchy_path",
        }


# ---------------------------------------------------------------------------
# Payload filter data — metadata stored correctly
# ---------------------------------------------------------------------------


class TestFilterableMetadata:
    """Verify that metadata fields are stored in the payload for filtering."""

    @pytest.mark.anyio()
    async def test_confidence_stored_in_payload(self) -> None:
        port = QdrantVectorPort(embed_fn=_embed)
        port._collections_ensured.add("skill_bank")
        port._client = AsyncMock()
        port._client.upsert = AsyncMock()

        docs = [_doc("s1", "skill text", confidence=0.85)]
        await port.upsert("skill_bank", docs)

        points = port._client.upsert.call_args.kwargs.get(
            "points", port._client.upsert.call_args[1].get("points", []),
        )
        assert points[0].payload["confidence"] == 0.85

    @pytest.mark.anyio()
    async def test_algorithm_version_stored(self) -> None:
        port = QdrantVectorPort(embed_fn=_embed)
        port._collections_ensured.add("skill_bank")
        port._client = AsyncMock()
        port._client.upsert = AsyncMock()

        docs = [_doc("s1", "skill", algorithm_version="v2")]
        await port.upsert("skill_bank", docs)

        points = port._client.upsert.call_args.kwargs.get(
            "points", port._client.upsert.call_args[1].get("points", []),
        )
        assert points[0].payload["algorithm_version"] == "v2"

    @pytest.mark.anyio()
    async def test_source_colony_stored(self) -> None:
        port = QdrantVectorPort(embed_fn=_embed)
        port._collections_ensured.add("skill_bank")
        port._client = AsyncMock()
        port._client.upsert = AsyncMock()

        docs = [_doc("s1", "skill", source_colony="col-abc123")]
        await port.upsert("skill_bank", docs)

        points = port._client.upsert.call_args.kwargs.get(
            "points", port._client.upsert.call_args[1].get("points", []),
        )
        assert points[0].payload["source_colony"] == "col-abc123"

    @pytest.mark.anyio()
    async def test_created_at_stored(self) -> None:
        port = QdrantVectorPort(embed_fn=_embed)
        port._collections_ensured.add("skill_bank")
        port._client = AsyncMock()
        port._client.upsert = AsyncMock()

        docs = [_doc("s1", "skill", created_at="2026-03-14T10:00:00Z")]
        await port.upsert("skill_bank", docs)

        points = port._client.upsert.call_args.kwargs.get(
            "points", port._client.upsert.call_args[1].get("points", []),
        )
        assert points[0].payload["created_at"] == "2026-03-14T10:00:00Z"

    @pytest.mark.anyio()
    async def test_combined_metadata_fields(self) -> None:
        port = QdrantVectorPort(embed_fn=_embed)
        port._collections_ensured.add("col")
        port._client = AsyncMock()
        port._client.upsert = AsyncMock()

        docs = [_doc(
            "s1", "technique: do X",
            confidence=0.7,
            algorithm_version="v1",
            source_colony="col-xyz",
            namespace="ws-default",
            created_at="2026-03-14T12:00:00Z",
        )]
        await port.upsert("col", docs)

        points = port._client.upsert.call_args.kwargs.get(
            "points", port._client.upsert.call_args[1].get("points", []),
        )
        payload = points[0].payload
        assert payload["confidence"] == 0.7
        assert payload["algorithm_version"] == "v1"
        assert payload["source_colony"] == "col-xyz"
        assert payload["namespace"] == "ws-default"
        assert payload["created_at"] == "2026-03-14T12:00:00Z"
        assert payload["text"] == "technique: do X"
