# Web Foraging Implementation Reference

Current-state reference for FormicOS web foraging: bounded web acquisition,
egress gateway, graduated fetch pipeline, content quality scoring, search
adapters, domain strategy, and operator controls. Code-anchored to Wave 59.

---

## Architecture Overview

Web foraging adds a second knowledge input channel (alongside colony extraction).
When retrieval exposes a gap, the system searches, fetches, extracts, and admits
content through the existing `MemoryEntryCreated` path at `candidate` status
with conservative priors.

```
Gap detected (reactive/proactive/operator)
  |
  v
ForagerService.handle_forage_signal()  [surface/forager.py]
  |-- emit ForageRequested event
  |-- ForagerOrchestrator.execute(request)
  |     |-- build_query() -> deterministic query
  |     |-- WebSearchAdapter.search() -> SearchResponse
  |     |-- filter_results() -> relevant results
  |     |-- DomainPolicy.is_allowed() -> domain filter
  |     |-- EgressGateway.fetch() -> rate-limited HTTP
  |     |-- FetchPipeline.extract() -> graduated extraction
  |     |-- chunk_content() -> bounded chunks
  |     |-- deduplicate_chunks() -> hash dedup
  |     |-- prepare_forager_entry() -> candidate dict
  |     \-- score_forager_entry() -> admission gate
  |-- emit MemoryEntryCreated for admitted entries
  |-- emit DomainStrategyUpdated for strategy changes
  \-- emit ForageCycleCompleted
```

---

## Trigger Modes

| Mode | Source | Priority |
|------|--------|----------|
| `reactive` | Live-task retrieval gap in knowledge_catalog | Highest |
| `proactive` | Briefing rules via MaintenanceDispatcher | Background |
| `operator` | Manual trigger | Explicit |

### Reactive Gap Detection (`surface/knowledge_catalog.py`)

```python
_FORAGE_SCORE_THRESHOLD = 0.35  # top-score below this triggers forage
_FORAGE_MIN_RESULTS = 2         # fewer unique sources triggers forage
```

Triggers when `top_score < 0.35` OR (`unique_sources < 2` AND `results < 3`).
Does not perform network I/O inline — hands off to forager path via
`_forage_signal` metadata on retrieval results.

### Proactive Trigger

Three briefing rules emit `forage_signal` metadata: confidence_decline,
coverage_gap, stale_cluster. MaintenanceDispatcher hands signals to
ForagerService via background `asyncio.create_task()`.

---

## Forager Orchestrator (`surface/forager.py`)

### ForageRequest

```python
@dataclass
class ForageRequest:
    workspace_id: str
    trigger: str              # reactive|proactive:*|operator
    gap_description: str
    domains: list[str] = []
    topic: str = ""
    context: str = ""
    colony_id: str = ""
    thread_id: str = ""
    max_results: int = 5
    budget_limit: float = 0.50
```

### Deterministic Query Templates

```python
_QUERY_TEMPLATES = {
    "reactive":                      "{topic} {context}",
    "proactive:confidence_decline":  "{topic} latest {year}",
    "proactive:prediction_error":    "{topic} {context} correct approach",
    "proactive:stale_cluster":       "{topic} reference guide {year}",
    "proactive:coverage_gap":        "{topic} how to {context}",
    "proactive:knowledge_roi":       "{topic} best practices tutorial",
    "default":                       "{topic} {context}",
}
```

`build_query(request)` expands template with year, topic, context. Collapses
whitespace, trims to 200 chars. No LLM rewriting.

### Source Credibility Tiers

| Tier | Score | Examples |
|------|-------|---------|
| T1 | 1.0 | docs.python.org, MDN, AWS, Kubernetes docs |
| T2 | 0.85 | .edu, .gov, arXiv, RFC |
| T3 | 0.65 | stackoverflow.com, github.com, wikipedia.org |
| T4 | 0.45 | medium.com, dev.to, general blogs |
| T5 | 0.30 | Unknown domains |

### Content Chunking

- `_CHUNK_SIZE = 1500` chars, `_CHUNK_OVERLAP = 200` chars.
- Recursive: paragraph splitting -> sentence splitting -> character fallback.
- Small segments merged respecting chunk_size limits.

### Exact-Hash Deduplication

SHA-256 of normalized text (whitespace collapsed, lowercase). Tracks seen
hashes across all input to prevent both intra-cycle and cross-cycle duplicates.

### Entry Preparation

Each admitted chunk becomes a candidate entry:
- `id`: `mem-forager-{content_hash[:12]}`
- `entry_type`: "experience", `sub_type`: "learning"
- `status`: "candidate"
- `conf_alpha/beta`: 5.0/5.0 (conservative prior)
- `decay_class`: "ephemeral" (web content decays fast)
- `forager_provenance`: source_url, source_domain, source_credibility,
  fetch_timestamp, fetch_level, forager_trigger, forager_query, quality_score.

Admission uses the standard 7-signal pipeline (`surface/admission.py`).
No special treatment for web content.

---

## Egress Gateway (`adapters/egress_gateway.py`)

Rate-limited, domain-controlled HTTP egress.

### EgressPolicy

| Parameter | Default | Purpose |
|-----------|---------|---------|
| `max_response_bytes` | 500,000 | Size cap per response |
| `timeout_seconds` | 15.0 | Request timeout |
| `rate_limit_per_second` | 2.0 | Per-domain rate |
| `rate_burst` | 5 | Token bucket burst |
| `respect_robots_txt` | True | Check robots.txt |
| `user_agent` | FormicOS-Forager/0.1 | HTTP user agent |

### Enforcement Order

1. Validate origin (must be `SEARCH_RESULT` or `OPERATOR_APPROVED`).
2. Parse domain from URL.
3. Domain policy check (denylist > operator-approved > allowlist).
4. Rate limit check (per-domain token bucket).
5. Robots.txt check (cached 1 hour).
6. Fetch via httpx with size limit enforcement.

### Domain Policy

- Denylist always wins.
- Operator-approved domains bypass allowlist.
- For search results: if allowlist set, domain must match; else all allowed.

---

## Fetch Pipeline (`adapters/fetch_pipeline.py`)

Graduated extraction with domain-adaptive strategy.

### Extraction Levels

| Level | Method | Fallback |
|-------|--------|----------|
| 1 | trafilatura (markdown mode, no_fallback=True) | — |
| 2 | trafilatura (favor_recall=True) | readability-lxml |
| 3 | Browser rendering (deferred) | — |

Non-HTML bypasses: plaintext passthrough, JSON passthrough.

### Escalation Logic

`_should_escalate(text, html)` returns True if:
- Text length < `_MIN_TEXT_LENGTH` (100 chars).
- Text-to-markup ratio < `_MIN_TEXT_TO_MARKUP_RATIO` (0.1).
- Noscript markers detected (JavaScript hydration indicators).

### Domain Strategy

```python
@dataclass
class DomainStrategy:
    domain: str
    preferred_level: int = LEVEL_1
    success_count: int = 0
    failure_count: int = 0
    last_updated: float = 0.0
```

- `record_success(level)`: increment count, set level.
- `record_failure(level)`: increment count, escalate level (min level+1, LEVEL_2).
- `should_reprobe_down()`: after 7 days with >= 3 successes, try lower level.

Known-difficult domains (medium.com, dev.to, substack.com) default to LEVEL_2.

---

## Content Quality Scoring (`adapters/content_quality.py`)

Deterministic scoring without LLM. Five signals:

| Signal | Weight | Measures |
|--------|--------|----------|
| Text-to-markup | 0.15 | text_len / html_len (sigmoid) |
| Information density | 0.25 | Unique words / total words |
| Readability | 0.20 | Sentence length distribution (Flesch-like) |
| Structural quality | 0.15 | Headings, paragraphs, lists |
| Spam score | 0.25 | 17 spam patterns (buy now, click here, etc.) |

Returns `ContentQualityResult(score, signal_scores, flags, text_length, word_count)`.
Flags: "very_short", "spam_indicators", "low_diversity", "poor_readability",
"low_structure".

---

## Web Search Adapter (`adapters/web_search.py`)

Pluggable search backend via `SearchBackend` protocol.

### Backends

**DuckDuckGo HTML** — no API key required. POSTs to `lite.duckduckgo.com/lite/`,
parses HTML for result links and snippets.

**Serper** — Google Search via serper.dev API. Requires `X-API-KEY` header.
POSTs to `google.serper.dev/search`.

**Selection**: `WebSearchAdapter.create(serper_api_key="")` prefers Serper if
key provided, else DDG.

### Pre-Fetch Relevance Filter

`filter_results(results, query, min_overlap=1)` — word-level overlap between
query and title+snippet. Protects fetch budget from irrelevant results.

---

## Operator Domain Controls

### API Endpoint

`PUT /api/v1/workspaces/{workspace_id}/forager-domain-control`

```json
{
    "domain": "stackoverflow.com",
    "action": "trust|distrust|reset",
    "actor": "operator",
    "reason": "Optional reason"
}
```

Emits `ForagerDomainOverride` event. Applied live to `DomainPolicy` on
ForagerOrchestrator.

### DomainPolicy

```python
class DomainPolicy:
    trusted: set[str]       # if set, only these allowed
    distrusted: set[str]    # always blocked
```

Methods: `is_allowed(domain)`, `trust(domain)`, `distrust(domain)`, `reset(domain)`.

---

## Events (4 types, event numbers 59-62)

| Event | Fields |
|-------|--------|
| `ForageRequested` | workspace_id, mode (reactive/proactive/operator), reason, gap_domain, gap_query, max_results (1-20) |
| `ForageCycleCompleted` | forage_request_seq, queries_issued, pages_fetched, pages_rejected, entries_admitted, entries_deduplicated, duration_ms, error |
| `DomainStrategyUpdated` | domain, preferred_level (1-3), success_count, failure_count, reason |
| `ForagerDomainOverride` | domain, action (trust/distrust/reset), actor, reason |

Individual search/fetch/rejection stays log-only — not event-sourced.

---

## Domain Strategy Persistence

Persisted via `DomainStrategyUpdated` events. Projection stores:
- `store.domain_strategies[workspace_id][domain]`: preferred_level,
  success_count, failure_count, level_changes.
- `store.domain_overrides[workspace_id][domain]`: action, actor, reason.
  Deleted on "reset".

Survives replay.

---

## Key Constants

| Constant | Value | Location |
|----------|-------|----------|
| `_CHUNK_SIZE` | 1500 | `forager.py` |
| `_CHUNK_OVERLAP` | 200 | `forager.py` |
| `_FORAGE_SCORE_THRESHOLD` | 0.35 | `knowledge_catalog.py` |
| `_FORAGE_MIN_RESULTS` | 2 | `knowledge_catalog.py` |
| `max_response_bytes` | 500,000 | `egress_gateway.py` |
| `timeout_seconds` | 15.0 | `egress_gateway.py` |
| `rate_limit_per_second` | 2.0 | `egress_gateway.py` |
| `rate_burst` | 5 | `egress_gateway.py` |
| `_ROBOTS_CACHE_TTL` | 3600 | `egress_gateway.py` |
| `_MIN_TEXT_LENGTH` | 100 | `fetch_pipeline.py` |
| `_MIN_TEXT_TO_MARKUP_RATIO` | 0.1 | `fetch_pipeline.py` |
| `LEVEL_1` | 1 | `fetch_pipeline.py` |
| `LEVEL_2` | 2 | `fetch_pipeline.py` |
| `LEVEL_3` | 3 | `fetch_pipeline.py` |

---

## Key Source Files

| File | Purpose |
|------|---------|
| `surface/forager.py` | ForagerService, ForagerOrchestrator, query templates, chunking, dedup |
| `adapters/egress_gateway.py` | EgressGateway, rate limiting, domain policy, robots.txt |
| `adapters/fetch_pipeline.py` | FetchPipeline, graduated extraction, domain strategy |
| `adapters/content_quality.py` | Deterministic content-quality scoring |
| `adapters/web_search.py` | DuckDuckGo + Serper backends, relevance filter |
| `surface/knowledge_catalog.py` | Reactive gap detection, forage trigger |
| `surface/self_maintenance.py` | Proactive forage signal dispatch |
| `surface/admission.py` | 7-signal admission scoring (shared with colony extraction) |
| `surface/routes/api.py` | Domain control REST endpoint |
