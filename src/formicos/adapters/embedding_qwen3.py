"""Qwen3-Embedding-0.6B sidecar client (Wave 13).

Embeds text via llama.cpp's OpenAI-compatible ``/v1/embeddings`` endpoint
on port 8200. Three mandatory steps that the server doesn't handle:

1. Prepend instruction prefix for **queries** (not documents).
2. Append ``<|endoftext|>`` to **all** inputs (decoder model requirement).
3. L2-normalize the output vectors (server returns raw logits).

The endpoint URL and instruction text are configurable so surface wiring
can override from ``formicos.yaml``.
"""

from __future__ import annotations

import math

import httpx
import structlog

logger = structlog.get_logger(__name__)

DEFAULT_URL = "http://localhost:8200/v1/embeddings"
DEFAULT_INSTRUCTION = (
    "Given a skill description, retrieve the matching agent capability"
)
EOS_TOKEN = "<|endoftext|>"


def _l2_normalize(vec: list[float]) -> list[float]:
    """L2-normalize a dense vector.  Pure-Python — no numpy dependency."""
    norm = math.sqrt(sum(x * x for x in vec))
    if norm == 0.0:
        return vec
    return [x / norm for x in vec]


class Qwen3Embedder:
    """Async embedding client for the Qwen3-Embedding-0.6B sidecar."""

    def __init__(
        self,
        url: str = DEFAULT_URL,
        instruction: str = DEFAULT_INSTRUCTION,
        timeout: float = 30.0,
    ) -> None:
        self._url = url
        self._instruction = instruction
        self._client = httpx.AsyncClient(timeout=timeout)

    async def embed(
        self,
        texts: list[str],
        *,
        is_query: bool = False,
    ) -> list[list[float]]:
        """Embed a batch of texts.

        Parameters
        ----------
        texts:
            Raw text strings to embed.
        is_query:
            If ``True``, prepend the instruction prefix (asymmetric
            query encoding).  Documents are encoded without prefix.

        Returns
        -------
        List of L2-normalized 1024-dim dense vectors.
        """
        if not texts:
            return []

        if is_query:
            inputs = [
                f"Instruct: {self._instruction}\nQuery:{t}{EOS_TOKEN}"
                for t in texts
            ]
        else:
            inputs = [f"{t}{EOS_TOKEN}" for t in texts]

        try:
            resp = await self._client.post(
                self._url,
                json={"input": inputs, "encoding_format": "float"},
            )
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("qwen3_embed.request_failed", error=str(exc))
            return []

        data = resp.json().get("data", [])
        raw: list[list[float]] = [d["embedding"] for d in data]
        normalized = [_l2_normalize(v) for v in raw]

        logger.debug(
            "qwen3_embed.ok",
            count=len(normalized),
            dim=len(normalized[0]) if normalized else 0,
            is_query=is_query,
        )
        return normalized

    async def close(self) -> None:
        """Close the underlying httpx client."""
        await self._client.aclose()


__all__ = ["Qwen3Embedder", "_l2_normalize"]
