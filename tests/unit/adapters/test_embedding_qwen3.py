"""Unit tests for the Qwen3-Embedding-0.6B sidecar client."""

from __future__ import annotations

import math
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from formicos.adapters.embedding_qwen3 import (
    EOS_TOKEN,
    Qwen3Embedder,
    _l2_normalize,
)


# ── _l2_normalize ────────────────────────────────────────────


class TestL2Normalize:
    def test_unit_vector_unchanged(self) -> None:
        vec = [1.0, 0.0, 0.0]
        result = _l2_normalize(vec)
        assert result == pytest.approx([1.0, 0.0, 0.0])

    def test_scales_to_unit_length(self) -> None:
        vec = [3.0, 4.0]
        result = _l2_normalize(vec)
        assert result == pytest.approx([0.6, 0.8])
        norm = math.sqrt(sum(x * x for x in result))
        assert norm == pytest.approx(1.0)

    def test_all_equal_components(self) -> None:
        vec = [1.0, 1.0, 1.0, 1.0]
        result = _l2_normalize(vec)
        expected = 1.0 / 2.0  # 1/sqrt(4)
        assert result == pytest.approx([expected] * 4)

    def test_zero_vector_unchanged(self) -> None:
        vec = [0.0, 0.0, 0.0]
        result = _l2_normalize(vec)
        assert result == [0.0, 0.0, 0.0]

    def test_negative_components(self) -> None:
        vec = [-3.0, 4.0]
        result = _l2_normalize(vec)
        assert result == pytest.approx([-0.6, 0.8])

    def test_high_dimensional(self) -> None:
        vec = [float(i) for i in range(1024)]
        result = _l2_normalize(vec)
        norm = math.sqrt(sum(x * x for x in result))
        assert norm == pytest.approx(1.0, abs=1e-6)


# ── Qwen3Embedder ───────────────────────────────────────────


class TestQwen3Embedder:
    @pytest.fixture()
    def embedder(self) -> Qwen3Embedder:
        return Qwen3Embedder(url="http://test:8200/v1/embeddings")

    @pytest.mark.anyio()
    async def test_empty_input_returns_empty(self, embedder: Qwen3Embedder) -> None:
        result = await embedder.embed([])
        assert result == []

    @pytest.mark.anyio()
    async def test_document_encoding_appends_eos(self, embedder: Qwen3Embedder) -> None:
        """Document mode: no instruction prefix, only EOS appended."""
        fake_response = MagicMock()
        fake_response.raise_for_status = MagicMock()
        fake_response.json.return_value = {
            "data": [{"embedding": [3.0, 4.0]}],
        }
        mock_post = AsyncMock(return_value=fake_response)

        with patch.object(embedder._client, "post", new=mock_post):
            result = await embedder.embed(["hello world"], is_query=False)

        # Verify EOS appended, no instruction prefix
        call_args = mock_post.call_args
        inputs = call_args.kwargs["json"]["input"]
        assert len(inputs) == 1
        assert inputs[0] == f"hello world{EOS_TOKEN}"
        assert "Instruct:" not in inputs[0]

        # Result should be L2-normalized
        assert result == [pytest.approx([0.6, 0.8])]

    @pytest.mark.anyio()
    async def test_query_encoding_has_instruction_prefix(self, embedder: Qwen3Embedder) -> None:
        """Query mode: instruction prefix + EOS appended."""
        fake_response = MagicMock()
        fake_response.raise_for_status = MagicMock()
        fake_response.json.return_value = {
            "data": [{"embedding": [1.0, 0.0]}],
        }
        mock_post = AsyncMock(return_value=fake_response)

        with patch.object(embedder._client, "post", new=mock_post):
            result = await embedder.embed(["test query"], is_query=True)

        call_args = mock_post.call_args
        inputs = call_args.kwargs["json"]["input"]
        assert len(inputs) == 1
        assert inputs[0].startswith("Instruct: ")
        assert "Query:test query" in inputs[0]
        assert inputs[0].endswith(EOS_TOKEN)

        assert len(result) == 1

    @pytest.mark.anyio()
    async def test_batch_embedding(self, embedder: Qwen3Embedder) -> None:
        """Multiple texts are batched in a single request."""
        fake_response = MagicMock()
        fake_response.raise_for_status = MagicMock()
        fake_response.json.return_value = {
            "data": [
                {"embedding": [1.0, 0.0]},
                {"embedding": [0.0, 1.0]},
                {"embedding": [3.0, 4.0]},
            ],
        }

        with patch.object(embedder._client, "post", new=AsyncMock(return_value=fake_response)):
            result = await embedder.embed(["a", "b", "c"], is_query=False)

        assert len(result) == 3
        # Each vector should be L2-normalized
        for vec in result:
            norm = math.sqrt(sum(x * x for x in vec))
            assert norm == pytest.approx(1.0)

    @pytest.mark.anyio()
    async def test_http_error_returns_empty(self, embedder: Qwen3Embedder) -> None:
        """Graceful degradation on HTTP errors."""
        import httpx

        with patch.object(
            embedder._client,
            "post",
            side_effect=httpx.ConnectError("connection refused"),
        ):
            result = await embedder.embed(["some text"])

        assert result == []

    @pytest.mark.anyio()
    async def test_output_is_normalized(self, embedder: Qwen3Embedder) -> None:
        """Output vectors are L2-normalized even when server returns unnormalized."""
        raw_vec = [10.0, 20.0, 30.0]
        fake_response = MagicMock()
        fake_response.raise_for_status = MagicMock()
        fake_response.json.return_value = {
            "data": [{"embedding": raw_vec}],
        }

        with patch.object(embedder._client, "post", new=AsyncMock(return_value=fake_response)):
            result = await embedder.embed(["test"])

        assert len(result) == 1
        norm = math.sqrt(sum(x * x for x in result[0]))
        assert norm == pytest.approx(1.0)
