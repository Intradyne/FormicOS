# Wave 10 Algorithms — Implementation Reference

**Companion to:** `docs/waves/wave_10/plan.md`
**Purpose:** Concrete implementation patterns for each terminal. Not a spec — coders
should adapt these patterns to the actual codebase they find.

---

## A1. QdrantVectorPort — Adapter Implementation

### Constructor pattern

```python
from qdrant_client import AsyncQdrantClient, models
from collections.abc import Callable, Sequence
import structlog

logger = structlog.get_logger()

class QdrantVectorPort:
    """VectorPort implementation backed by Qdrant.

    The embed_fn is injected at construction — same pattern as LanceDBVectorPort.
    It converts text strings to embedding vectors.
    """

    def __init__(
        self,
        url: str = "http://qdrant:6333",
        embed_fn: Callable[[list[str]], list[list[float]]] | None = None,
        prefer_grpc: bool = True,
        default_collection: str = "skill_bank",
        vector_dimensions: int = 384,
    ):
        self._client = AsyncQdrantClient(url=url, prefer_grpc=prefer_grpc, timeout=30)
        self._embed_fn = embed_fn
        self._default_collection = default_collection
        self._dimensions = vector_dimensions
        self._collections_ensured: set[str] = set()
```

### ensure_collection — idempotent setup

```python
async def ensure_collection(self, name: str | None = None) -> None:
    """Create collection + payload indexes if they don't exist. Idempotent."""
    collection = name or self._default_collection
    if collection in self._collections_ensured:
        return

    try:
        if not await self._client.collection_exists(collection):
            await self._client.create_collection(
                collection_name=collection,
                vectors_config=models.VectorParams(
                    size=self._dimensions,
                    distance=models.Distance.COSINE,
                ),
                hnsw_config=models.HnswConfigDiff(m=16, ef_construct=100),
            )

        # Always ensure indexes (idempotent in Qdrant)
        index_fields = [
            ("namespace", models.PayloadSchemaType.KEYWORD),
            ("confidence", models.PayloadSchemaType.FLOAT),
            ("algorithm_version", models.PayloadSchemaType.KEYWORD),
            ("created_at", models.PayloadSchemaType.DATETIME),
            ("source_colony", models.PayloadSchemaType.KEYWORD),
        ]
        for field, schema in index_fields:
            try:
                if field == "namespace":
                    await self._client.create_payload_index(
                        collection, field,
                        field_schema=models.KeywordIndexParams(
                            type=models.PayloadSchemaType.KEYWORD,
                            is_tenant=True,
                        ),
                    )
                else:
                    await self._client.create_payload_index(collection, field, schema)
            except Exception:
                pass  # Index already exists — Qdrant is idempotent here

        self._collections_ensured.add(collection)
    except Exception as exc:
        logger.warning("qdrant_ensure_collection_failed", error=str(exc))
```

### search — VectorPort.search() implementation

```python
async def search(
    self,
    collection: str,
    query: str,
    top_k: int = 5,
) -> list:  # list[VectorSearchHit]
    """Embed query text, then search Qdrant via query_points()."""
    try:
        await self.ensure_collection(collection)

        if self._embed_fn is None:
            logger.warning("qdrant_search_no_embed_fn")
            return []

        # Embed the query text
        vectors = self._embed_fn([query])
        if not vectors or not vectors[0]:
            return []
        query_vector = vectors[0]

        # Search via query_points (NOT the removed search() method)
        result = await self._client.query_points(
            collection_name=collection,
            query=query_vector,
            limit=top_k,
            with_payload=True,
        )

        # Convert to VectorSearchHit format
        hits = []
        for point in result.points:
            hits.append(_to_search_hit(point))
        return hits

    except Exception as exc:
        logger.warning("qdrant_search_failed", collection=collection, error=str(exc))
        return []
```

### upsert — VectorPort.upsert() implementation

```python
async def upsert(self, collection: str, docs: Sequence) -> int:
    """Embed documents and upsert to Qdrant."""
    try:
        await self.ensure_collection(collection)

        if self._embed_fn is None or not docs:
            return 0

        texts = [doc.content for doc in docs]
        vectors = self._embed_fn(texts)

        points = []
        for doc, vector in zip(docs, vectors):
            payload = {
                "text": doc.content,
                "namespace": doc.metadata.get("namespace", "default"),
                **{k: v for k, v in doc.metadata.items() if k != "namespace"},
            }
            points.append(models.PointStruct(
                id=doc.id,
                vector=vector,
                payload=payload,
            ))

        await self._client.upsert(
            collection_name=collection,
            points=points,
            wait=True,
        )
        return len(points)

    except Exception as exc:
        logger.warning("qdrant_upsert_failed", collection=collection, error=str(exc))
        return 0
```

### Graceful degradation pattern

Every public method follows this pattern:
```python
try:
    # Qdrant operation
    return result
except Exception as exc:
    logger.warning("qdrant_operation_failed", op="search|upsert|delete", error=str(exc))
    return empty_default  # [] for search, 0 for upsert/delete
```

---

## A2. Migration Script

```python
"""scripts/migrate_lancedb_to_qdrant.py — One-shot LanceDB → Qdrant migration."""

import asyncio
import lancedb
from qdrant_client import AsyncQdrantClient, models

async def migrate():
    # 1. Read LanceDB
    db = lancedb.connect("data/formicos_vectors")
    tables = db.table_names()

    qdrant = AsyncQdrantClient(url="http://localhost:6333", prefer_grpc=True)

    for table_name in tables:
        table = db.open_table(table_name)
        df = table.to_pandas()
        if df.empty:
            continue

        # 2. Determine vector dimensions from first row
        first_vec = df.iloc[0]["vector"]
        dims = len(first_vec) if hasattr(first_vec, '__len__') else 384

        # 3. Create Qdrant collection
        if not await qdrant.collection_exists(table_name):
            await qdrant.create_collection(
                table_name,
                vectors_config=models.VectorParams(size=dims, distance=models.Distance.COSINE),
            )

        # 4. Convert and upload
        points = []
        for _, row in df.iterrows():
            vec = row["vector"]
            payload = {k: v for k, v in row.items() if k not in ("vector",)}
            points.append(models.PointStruct(
                id=str(row.get("id", row.name)),
                vector=vec.tolist() if hasattr(vec, 'tolist') else list(vec),
                payload=payload,
            ))

        if points:
            await qdrant.upsert(table_name, points=points, wait=True)

        # 5. Verify
        info = await qdrant.get_collection(table_name)
        assert info.points_count == len(df), (
            f"Migration mismatch for {table_name}: "
            f"expected {len(df)}, got {info.points_count}"
        )
        print(f"Migrated {table_name}: {len(df)} points")

if __name__ == "__main__":
    asyncio.run(migrate())
```

---

## A3. GeminiAdapter — Key Patterns

### Message conversion (FormicOS → Gemini)

The engine sends normalized messages: `{"role": "user"|"assistant", "content": str}`.
The Gemini API expects `{"role": "user"|"model", "parts": [{"text": str}]}`.

Tool results in FormicOS follow the pattern: `{"role": "user", "content": "[Tool result: tool_name]\nresult_text"}`.
The adapter must detect this pattern and convert to Gemini's `functionResponse` format.

```python
import re
TOOL_RESULT_RE = re.compile(r"^\[Tool result: (\w+)\]\n(.+)", re.DOTALL)

def _convert_messages(self, messages: list[dict]) -> list[dict]:
    contents = []
    for msg in messages:
        role = msg["role"]
        if role == "system":
            continue  # handled via systemInstruction
        gemini_role = "model" if role == "assistant" else "user"
        parts = []

        # Tool result detection
        if role == "user" and (m := TOOL_RESULT_RE.match(msg.get("content", ""))):
            tool_name, result_text = m.group(1), m.group(2)
            parts.append({"functionResponse": {
                "name": tool_name,
                "response": {"result": result_text},
            }})
        # Tool calls on assistant messages
        elif role == "assistant" and "tool_calls" in msg:
            for tc in msg["tool_calls"]:
                part = {"functionCall": {"name": tc.name, "args": tc.arguments}}
                if hasattr(tc, '_thought_sig') and tc._thought_sig:
                    part["thoughtSignature"] = tc._thought_sig
                parts.append(part)
        # Plain text
        else:
            text = msg.get("content", "")
            if text:
                parts.append({"text": text})

        if parts:
            contents.append({"role": gemini_role, "parts": parts})
    return contents
```

### Response parsing — tool call detection without finishReason

```python
def _parse_response(self, data: dict) -> LLMResponse:
    candidates = data.get("candidates", [])
    if not candidates:
        return LLMResponse(text="", finish_reason="blocked")

    candidate = candidates[0]
    parts = candidate.get("content", {}).get("parts", [])
    finish = candidate.get("finishReason", "STOP")

    text_parts, tool_calls = [], []
    for part in parts:
        if part.get("thought"):
            continue  # skip thinking summaries
        if "functionCall" in part:
            fc = part["functionCall"]
            tc = ToolCall(name=fc["name"], arguments=fc.get("args", {}))
            if "thoughtSignature" in part:
                tc._thought_sig = part["thoughtSignature"]
            tool_calls.append(tc)
        elif "text" in part:
            text_parts.append(part["text"])

    # Normalize: Gemini uses STOP for both text and tool calls
    if tool_calls:
        norm_finish = "tool_use"
    elif finish in ("SAFETY", "RECITATION", "OTHER"):
        norm_finish = "blocked"
    elif finish == "MAX_TOKENS":
        norm_finish = "length"
    else:
        norm_finish = "stop"

    usage = data.get("usageMetadata", {})
    return LLMResponse(
        text="".join(text_parts) if text_parts else None,
        tool_calls=tool_calls,
        finish_reason=norm_finish,
        input_tokens=usage.get("promptTokenCount", 0),
        output_tokens=usage.get("candidatesTokenCount", 0),
    )
```

### Safety settings for code workloads

```python
SAFETY_SETTINGS = [
    {"category": c, "threshold": "BLOCK_ONLY_HIGH"}
    for c in [
        "HARM_CATEGORY_HARASSMENT",
        "HARM_CATEGORY_HATE_SPEECH",
        "HARM_CATEGORY_SEXUALLY_EXPLICIT",
        "HARM_CATEGORY_DANGEROUS_CONTENT",
    ]
]
```

---

## A4. Defensive Parser — 3-Stage Pipeline

```python
"""adapters/parse_defensive.py"""
import json, re
from dataclasses import dataclass
from difflib import get_close_matches
import json_repair

@dataclass
class ParsedToolCall:
    name: str
    arguments: dict

_FENCE_RE = re.compile(r"```(?:json)?\s*\n?(.*?)\n?\s*```", re.DOTALL)
_BRACE_RE = re.compile(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", re.DOTALL)
_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)

def parse_tool_calls_defensive(
    text: str,
    known_tools: set[str] | None = None,
) -> list[ParsedToolCall]:
    # Stage 1: native parse
    result = _try_parse(text, known_tools)
    if result is not None:
        return result

    # Stage 2: json_repair
    result = _try_repair(text, known_tools)
    if result is not None:
        return result

    # Stage 3: regex extraction
    cleaned = _THINK_RE.sub("", text).strip()
    for pattern in [_FENCE_RE, _BRACE_RE]:
        for match in pattern.finditer(cleaned):
            candidate = match.group(1) if pattern == _FENCE_RE else match.group(0)
            result = _try_repair(candidate.strip(), known_tools)
            if result is not None:
                return result

    return []

def _try_parse(text: str, known_tools: set[str] | None) -> list[ParsedToolCall] | None:
    try:
        obj = json.loads(text)
        return _extract(obj, known_tools)
    except (json.JSONDecodeError, TypeError):
        return None

def _try_repair(text: str, known_tools: set[str] | None) -> list[ParsedToolCall] | None:
    try:
        obj = json_repair.loads(text)
        return _extract(obj, known_tools)
    except Exception:
        return None

def _extract(obj, known_tools: set[str] | None) -> list[ParsedToolCall] | None:
    """Normalize diverse JSON shapes into ParsedToolCall list."""
    calls = []
    candidates = []

    if isinstance(obj, list):
        candidates = obj
    elif isinstance(obj, dict):
        if "name" in obj:
            candidates = [obj]
        for key in ("tool_calls", "function_calls", "calls"):
            if key in obj and isinstance(obj[key], list):
                candidates.extend(obj[key])
        if "function_call" in obj and isinstance(obj["function_call"], dict):
            candidates.append(obj["function_call"])

    for item in candidates:
        if not isinstance(item, dict):
            continue
        name = item.get("name") or item.get("function", {}).get("name")
        if not name:
            continue

        args = (item.get("arguments") or item.get("args") or
                item.get("input") or item.get("parameters") or
                item.get("function", {}).get("arguments") or {})

        # Handle string args (Gemini bug, OpenAI format)
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except json.JSONDecodeError:
                try:
                    args = json_repair.loads(args)
                except Exception:
                    args = {"_raw": args}

        if not isinstance(args, dict):
            args = {"_raw": args}

        # Validate against known tools
        if known_tools and name not in known_tools:
            matches = get_close_matches(name, known_tools, n=1, cutoff=0.6)
            if matches:
                name = matches[0]
            else:
                continue

        calls.append(ParsedToolCall(name=name, arguments=args))

    return calls if calls else None
```

---

## A5. Fallback Chain in Router

The fallback is implemented where the adapter is called, not in the router itself.
The router provides the model address; the caller handles blocked responses.

```python
# In runtime.py or wherever LLM calls are dispatched:

async def complete_with_fallback(
    model_address: str,
    messages: list,
    tools: list | None,
    **kwargs,
) -> LLMResponse:
    """Try primary model. On blocked response, try fallback from routing config."""
    adapter = self._get_adapter(model_address)
    model_name = model_address.split("/", 1)[1]

    response = await adapter.complete(model=model_name, messages=messages, tools=tools, **kwargs)

    if response.finish_reason == "blocked":
        fallback = self._get_fallback(model_address)  # from routing config
        if fallback:
            logger.warning("provider_blocked_fallback",
                          primary=model_address, fallback=fallback)
            fb_adapter = self._get_adapter(fallback)
            fb_model = fallback.split("/", 1)[1]
            response = await fb_adapter.complete(
                model=fb_model, messages=messages, tools=tools, **kwargs)

    return response
```

---

## A6. Skill Browser REST Endpoint

```python
# In surface/view_state.py (or a new surface/skill_endpoints.py):

async def get_skill_bank_detail(
    vector_port,
    sort_by: str = "confidence",
    limit: int = 50,
) -> list[dict]:
    """Fetch skills for the browser UI.

    Strategy: broad search with empty-ish query to retrieve all entries,
    then sort application-side. This works at <1K entries. At scale,
    use Qdrant scroll() (would need VectorPort extension).
    """
    # Use a broad query that will match most skills
    results = await vector_port.search(
        collection="skill_bank",
        query="skill knowledge technique pattern",  # broad retrieval query
        top_k=min(limit, 200),
    )

    entries = []
    for hit in results:
        entries.append({
            "id": hit.id,
            "text_preview": (hit.content or "")[:100],
            "confidence": hit.metadata.get("confidence", 0.5),
            "algorithm_version": hit.metadata.get("algorithm_version", "v1"),
            "extracted_at": hit.metadata.get("extracted_at", ""),
            "source_colony": hit.metadata.get("source_colony", "unknown"),
        })

    # Application-side sort
    if sort_by == "confidence":
        entries.sort(key=lambda e: e["confidence"], reverse=True)
    elif sort_by == "freshness":
        entries.sort(key=lambda e: e["extracted_at"], reverse=True)

    return entries[:limit]
```

Note: this broad-query approach is a pragmatic alpha pattern. At >1K skills, extend
VectorPort with a `list_all()` or `scroll()` method, or use Qdrant's scroll API directly
in the adapter. For now, the broad semantic query retrieves enough entries to populate
the browser.

---

## A7. Frontend Skill Browser Component

```typescript
// frontend/src/components/skill-browser.ts — Lit Web Component

import { LitElement, html, css } from 'lit';
import { customElement, state } from 'lit/decorators.js';
import { sharedStyles } from '../shared.js';

@customElement('skill-browser')
export class SkillBrowser extends LitElement {
  static styles = [sharedStyles, css`
    :host { display: block; }
    .skill-card { /* ... card styles ... */ }
    .confidence-bar { height: 4px; border-radius: 2px; }
    .conf-high { background: var(--color-success); }
    .conf-mid { background: var(--color-warning); }
    .conf-low { background: var(--color-error); }
    .empty-state { color: var(--color-text-muted); padding: 2rem; text-align: center; }
  `];

  @state() private skills: SkillEntry[] = [];
  @state() private sortBy = 'confidence';
  @state() private loading = true;

  async connectedCallback() {
    super.connectedCallback();
    await this.fetchSkills();
  }

  private async fetchSkills() {
    this.loading = true;
    try {
      const resp = await fetch(`/api/v1/skills?sort=${this.sortBy}&limit=50`);
      this.skills = await resp.json();
    } catch { this.skills = []; }
    this.loading = false;
  }

  render() {
    if (this.loading) return html`<div class="loading">Loading skills...</div>`;
    if (!this.skills.length) return html`
      <div class="empty-state">
        No skills yet. Complete a colony to start building the skill bank.
      </div>`;

    return html`
      <div class="controls">
        <select @change=${(e) => { this.sortBy = e.target.value; this.fetchSkills(); }}>
          <option value="confidence">Sort by confidence</option>
          <option value="freshness">Sort by freshness</option>
        </select>
      </div>
      ${this.skills.map(s => html`
        <div class="skill-card">
          <div class="confidence-bar ${this._confClass(s.confidence)}"
               style="width: ${s.confidence * 100}%"></div>
          <div class="text-preview">${s.text_preview}</div>
          <div class="meta">
            <span>conf: ${s.confidence.toFixed(2)}</span>
            <span>from: ${s.source_colony}</span>
            <span>${s.algorithm_version}</span>
          </div>
        </div>
      `)}`;
  }

  private _confClass(c: number) {
    if (c >= 0.6) return 'conf-high';
    if (c >= 0.3) return 'conf-mid';
    return 'conf-low';
  }
}
```

This is a reference pattern — the actual implementation should match the existing
component conventions in the FormicOS frontend (import patterns, shared styles, etc.).
