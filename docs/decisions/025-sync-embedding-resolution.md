# ADR-025: Sync Embedding Resolution for Qwen3 Sidecar

**Status:** Accepted
**Date:** 2026-03-14
**Context:** Wave 14 Stream B pre-requisite decision. Resolves Wave 13 Residual #4.

---

## Problem

Three consumers depend on a sync `embed_fn: Callable[[list[str]], list[list[float]]]`:

| Consumer | File | What it does | Current state |
|---|---|---|---|
| `RoundRunner._compute_convergence_embed()` | `engine/runner.py` | Cosine similarity between round summaries and goal for convergence quality | **DEGRADED** -- falls back to Jaccard word-overlap heuristic |
| `StigmergicStrategy.__init__(embed_fn=...)` | `engine/strategies/stigmergic.py` | Embeds agent descriptors to build DyTopo communication topology | **DISABLED** -- falls back to `SequentialStrategy` |
| `KnowledgeGraphAdapter.__init__(embed_fn=...)` | `adapters/knowledge_graph.py` | Cosine similarity for entity resolution (dedup) | **DEGRADED** -- falls back to exact normalized name matching |

The Qwen3-Embedding-0.6B sidecar (`adapters/embedding_qwen3.py`) is async-only (httpx). The `_build_embed_fn()` in `surface/app.py` explicitly returns `None` when the configured model is `qwen3-embedding-*`, because the sidecar can't be loaded via `SentenceTransformer()`.

Result: with the default config, `embed_fn = None` for all three consumers. The QdrantVectorPort is NOT affected -- it has a separate `embed_client` parameter that receives the async `Qwen3Embedder` directly.

## Decision

Add an optional `async_embed_fn` parameter to all three consumers. Wire `Qwen3Embedder.embed` as the async path. This is additive -- the sync `embed_fn` remains as a fallback for testing and for non-sidecar models.

## Why this works

All three consumers are already called from async contexts:
- `RoundRunner.run_round()` is async
- `StigmergicStrategy.resolve_topology()` is async
- `KnowledgeGraphAdapter` methods are async (aiosqlite)

The embed call is the only sync blocker inside these async methods. Making the embed call awaitable unblocks all three without changing the async/sync boundary of the outer methods.

## Implementation

### 1. RoundRunner (Stream B owns)

```python
class RoundRunner:
    def __init__(
        self,
        emit: ...,
        embed_fn: Callable[[list[str]], list[list[float]]] | None = None,
        async_embed_fn: Callable[[list[str]], Awaitable[list[list[float]]]] | None = None,
        ...
    ):
        self._embed_fn = embed_fn
        self._async_embed_fn = async_embed_fn

    async def _get_embeddings(self, texts: list[str]) -> list[list[float]] | None:
        """Best-effort embedding: async sidecar > sync model > None."""
        if self._async_embed_fn is not None:
            return await self._async_embed_fn(texts)
        if self._embed_fn is not None:
            return self._embed_fn(texts)
        return None
```

Change `_compute_convergence` to call `await self._get_embeddings(texts)` instead of `self._embed_fn(texts)`.

### 2. StigmergicStrategy (Stream B owns)

```python
class StigmergicStrategy:
    def __init__(
        self,
        embed_fn: Callable[[list[str]], list[list[float]]] | None = None,
        async_embed_fn: Callable[[list[str]], Awaitable[list[list[float]]]] | None = None,
        tau: float = 0.35,
        k_in: int = 5,
    ):
        self._embed_fn = embed_fn
        self._async_embed_fn = async_embed_fn

    async def resolve_topology(self, ...):
        if self._async_embed_fn is not None:
            embeddings = await self._async_embed_fn(all_texts)
        elif self._embed_fn is not None:
            embeddings = self._embed_fn(all_texts)
        else:
            return [[a.id] for a in agents]  # no embedding = sequential fallback
```

This also removes the need for the `_STIGMERGIC_AVAILABLE` feature flag in `colony_manager.py` -- the strategy can always be instantiated; it just needs at least one embed path.

### 3. KnowledgeGraphAdapter (Stream B or D owns)

```python
class KnowledgeGraphAdapter:
    def __init__(
        self,
        db_path: ...,
        embed_fn: Callable | None = None,
        async_embed_fn: Callable | None = None,
        similarity_threshold: float = 0.85,
        ...
    ):
        self._embed_fn = embed_fn
        self._async_embed_fn = async_embed_fn

    async def _embed_for_similarity(self, texts: list[str]) -> list[list[float]] | None:
        if self._async_embed_fn is not None:
            return await self._async_embed_fn(texts)
        if self._embed_fn is not None:
            return self._embed_fn(texts)
        return None
```

### 4. Wiring in surface/app.py and colony_manager.py

```python
# surface/app.py -- when building KG adapter:
kg_adapter = KnowledgeGraphAdapter(
    db_path=...,
    embed_fn=embed_fn,                    # sync fallback (may be None)
    async_embed_fn=embed_client.embed if embed_client else None,
    ...
)

# surface/colony_manager.py -- when building RoundRunner:
runner = RoundRunner(
    emit=...,
    embed_fn=self._runtime.embed_fn,
    async_embed_fn=self._runtime.embed_client.embed if self._runtime.embed_client else None,
    ...
)
```

Note: `Runtime` needs to expose `embed_client` (the `Qwen3Embedder` instance) alongside the existing `embed_fn`. Currently `app.py` creates `embed_client` locally but only passes `embed_fn` to `Runtime.__init__`. Stream B adds `embed_client` as a `Runtime` attribute.

## Consequences

| Consumer | Before | After |
|---|---|---|
| Convergence | Jaccard heuristic | 1024-dim cosine via sidecar |
| Stigmergic strategy | Disabled (sequential fallback) | Active with sidecar embeddings |
| KG entity resolution | Exact name match only | Cosine similarity at 0.85 threshold |
| Test environments | Still work with sync embed_fn or no embed at all | No change -- graceful fallback chain |

## What Stream B does

1. Add `async_embed_fn` parameter to `RoundRunner`, `StigmergicStrategy`, `KnowledgeGraphAdapter`
2. Add `embed_client` attribute to `Runtime`
3. Update `colony_manager.py` to pass async embed fn to runner and strategy
4. Update `app.py` to pass async embed fn to KG adapter and store embed_client on runtime
5. Remove the `_STIGMERGIC_AVAILABLE` feature flag -- strategy always instantiable
6. Measure and log: convergence embed latency, stigmergic topology build latency, KG resolution latency
