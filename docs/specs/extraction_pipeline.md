# Extraction Pipeline Implementation Reference

Current-state reference for FormicOS knowledge extraction: post-colony memory
extraction, transcript harvest, security scanning, admission scoring, trajectory
extraction, and the full extraction-to-event flow. Code-anchored to Wave 59.

---

## Extraction Flow Overview

```
Colony Completion
  |
  v
extract_institutional_memory()  [surface/colony_manager.py]
  |-- classify_task(colony.task) -> (task_class, category_dict)
  |-- fetch existing_entries (Wave 59 curation context)
  |-- build_extraction_prompt(..., task_class, existing_entries)
  |-- LLM call (archivist model, temp=0.0, max_tokens=2048)
  |-- parse_extraction_response() -> raw JSON
  |-- Wave 59: dispatch CREATE/REFINE/MERGE/NOOP actions
  |-- build_memory_entries(raw, colony_id, workspace_id, artifact_ids, status)
  |     |-- filter by _MIN_CONTENT_LEN (30 chars)
  |     \-- filter by is_environment_noise_text()
  |-- stamp primary_domain = task_class (Wave 58.5)
  |-- for each entry:
  |     |-- quality gate: _check_extraction_quality(entry)
  |     |-- inline dedup: _check_inline_dedup(content, ws_id, succeeded)
  |     |-- security scan: scan_entry(entry) -> bake scan_status
  |     |-- admission: evaluate_entry(entry, scanner_result)
  |     |-- emit MemoryEntryCreated
  |     \-- if not rejected + succeeded: emit MemoryEntryStatusChanged
  |-- Wave 59: emit MemoryEntryRefined for REFINE actions
  |-- Wave 59: emit MemoryEntryMerged for MERGE actions
  \-- emit MemoryExtractionCompleted
```

---

## Memory Extraction (`surface/memory_extractor.py`)

### build_extraction_prompt

```python
def build_extraction_prompt(
    task: str, final_output: str, artifacts: list[dict[str, Any]],
    colony_status: str, failure_reason: str | None,
    contract_result: dict[str, Any] | None,
    task_class: str = "generic",
    existing_entries: list[dict[str, Any]] | None = None,
) -> str
```

Two extraction modes based on parameters:

**Legacy mode** (no `existing_entries`): Prompt requests dual extraction.
Returns `{"skills": [...], "experiences": [...]}`. Skills require: title,
content, when_to_use, failure_modes, domains, tool_refs, sub_type. Experiences
require: title, content, trigger, domains, tool_refs, polarity, sub_type.

**Curating mode** (Wave 59, `existing_entries` provided + completed status):
Shows up to 10 existing entries with id, title, confidence, access_count,
primary_domain, and content preview (200 chars). Returns
`{"actions": [{type: "CREATE"|"REFINE"|"MERGE"|"NOOP", ...}]}`.

- `CREATE`: All entry fields (same as legacy).
- `REFINE`: `entry_id` + `new_content` + optional `new_title`.
- `MERGE`: `target_id` + `source_id` + `merged_content`.
- `NOOP`: Existing coverage adequate.

Both modes include `decay_class` classification and `primary_domain` tagging.

Failed colonies only extract experiences with `polarity: "negative"`.

### build_memory_entries

```python
def build_memory_entries(
    raw: dict[str, Any], colony_id: str, workspace_id: str,
    artifact_ids: list[str], colony_status: str,
) -> list[dict[str, Any]]
```

Converts LLM output into `MemoryEntry` dicts. For each skill/experience:

1. Skip if content < `_MIN_CONTENT_LEN` (30 chars).
2. Skip if `is_environment_noise_text()` matches.
3. Parse `decay_class` and `sub_type` enums with fallback defaults.
4. Set initial confidence: 0.5 for completed colonies, 0.4 for failed.
5. All entries start as `status=candidate`, `scan_status=pending`.
6. IDs: `mem-{colony_id}-s-{i}` for skills, `mem-{colony_id}-e-{i}` for experiences.

### parse_extraction_response

```python
def parse_extraction_response(text: str) -> dict[str, Any]
```

Defensive JSON parser:
1. Strip markdown code fences.
2. Try direct `json.loads()`.
3. Wave 59: warn if both `actions` and legacy keys present (mixed format).
4. Fall back to balanced-brace extraction.
5. Wave 58: `json_repair` library fallback for malformed JSON.
6. Return `{"skills": [], "experiences": []}` on all failures.

### Environment Noise Filtering

`is_environment_noise_text(text)` returns True when text matches environment
chatter patterns. Detection logic: text is flagged if ANY phrase matches OR
(ANY context AND ANY error pattern both match).

**Phrases** (16 entries): "workspace not configured", "workspace directory
remains unconfigured", "workspace configuration issues", "not available in
the current environment", "git command is unavailable", "git command is not
available", "tool call failure", "pytest is not installed", "test runner fails
due to missing", "test runner not available", "module not found", "pip install",
"package not installed", "import error", "no module named", "extracting
transferable knowledge".

**Contexts** (10): workspace, environment, git, tool, command, sandbox,
install, pytest, pip, import.

**Errors** (8): command not found, permission denied, no such file or
directory, unavailable, not configured, not installed, missing module,
cannot import.

---

## Transcript Harvest

Second extraction pass on full colony transcript (Wave 33, hook position 4.5).

### build_harvest_prompt

```python
def build_harvest_prompt(turns: list[dict[str, Any]]) -> str
```

Each turn dict has: `agent_id`, `caste`, `content` (truncated to 500 chars),
`event_kind`, `round_number`. Requests JSON:
`{"entries": [{"turn_index": N, "type": "...", "summary": "..."}]}`.

### Harvest Type Mappings

```python
HARVEST_TYPES = {"bug": "experience", "decision": "experience",
                 "convention": "skill", "learning": "experience"}

HARVEST_SUB_TYPE_MAP = {"bug": "bug", "decision": "decision",
                        "convention": "convention", "learning": "learning"}
```

### parse_harvest_response

```python
def parse_harvest_response(text: str) -> list[dict[str, Any]]
```

Returns validated list of `{turn_index, type, summary}`. Validates type
against `HARVEST_TYPES`, requires both type and summary, filters environment
noise.

---

## Task Classification (`surface/task_classifier.py`)

```python
def classify_task(description: str) -> tuple[str, dict[str, Any]]
```

Keyword overlap matching. Categories: `code_implementation`, `code_review`,
`research`, `design`, `creative`, `generic` (fallback). Returns
`(category_name, category_dict)` where dict contains `default_castes`,
`default_outputs`, `default_rounds`, `default_budget`, `default_strategy`.

Used for:
- Stamping `primary_domain` on extracted entries (Wave 58.5).
- Domain-boundary filtering in context assembly.
- Operational playbook resolution.

---

## Quality Gate (`surface/colony_manager.py`)

`_check_extraction_quality(entry)` returns empty string if passes, or a
reason string if rejected.

**Constants**: `_SHORT_CONTENT_CHARS = 40`, `_SHORT_TITLE_CHARS = 15`.

**Generic phrases** (frozenset): "general knowledge", "common practice",
"best practice", "standard approach", "typical pattern", "well known",
"as expected", "nothing special", "no issues".

**Rejection rules** (multiple signals required):
1. `is_empty` (content < 5 chars) -> "empty_content"
2. `is_short AND has_generic_phrase` -> "short_and_generic"
3. `is_short AND has_weak_title AND has_no_domains` -> "short_weak_title_no_domains"
4. `has_generic_phrase AND has_no_domains AND has_weak_title` -> "generic_no_domains_weak_title"

---

## Inline Deduplication

`_check_inline_dedup(entry_content, workspace_id, succeeded)` checks for
near-duplicates before emission.

- Threshold: cosine similarity > 0.92 (`_INLINE_DEDUP_THRESHOLD`).
- If match found: skip new entry, emit `MemoryConfidenceUpdated` to
  reinforce existing entry.
- Returns existing `entry_id` or `None`.

---

## Security Scanning (`surface/memory_scanner.py`)

5-axis scoring system. Each axis contributes to a composite score mapped
to severity tiers.

### Axes

| Axis | Patterns | Score |
|------|----------|-------|
| Content risk | eval/exec/subprocess/os.system | +1.0 |
| Content risk | sudo commands | +0.8 |
| Content risk | curl -d/wget --post/requests.post | +1.2 |
| Supply chain | curl\|sh, wget\|sh | +1.5 |
| Supply chain | pip install git+, npm install https://, npx | +1.0 |
| Prompt injection | "ignore previous instructions", "system: you are" | +1.5 |
| Credential | api_key=/password=/secret=/token= (8+ chars) | +1.0 |
| Capability | Dangerous tool combos ({http_fetch, file_write}, etc.) | +0.8 each |

### Tier Mapping

| Score | Tier |
|-------|------|
| >= 2.8 | critical |
| >= 2.0 | high |
| >= 1.2 | medium |
| >= 0.5 | low |
| < 0.5 | safe |

### Credential Scanning (`surface/credential_scan.py`)

Dual-config detect-secrets integration:
- **Prose config**: 15 regex-only detectors (no entropy) — safe for natural language.
- **Code config**: Prose + 2 entropy detectors (Base64 limit 4.5, Hex limit 3.0).

Functions: `scan_text()`, `scan_mixed_content()` (dual-pass: prose on full
text, code on extracted code blocks), `redact_credentials()`.

---

## Admission Scoring (`surface/admission.py`)

```python
def evaluate_entry(
    entry: dict[str, Any], *,
    scanner_result: dict[str, Any] | None = None,
    peer_trust_score: float | None = None,
) -> AdmissionResult
```

### Seven Signals (sum to 1.0)

| Signal | Weight | Computation |
|--------|--------|-------------|
| Confidence | 0.20 | Posterior mean = alpha / (alpha + beta) |
| Provenance | 0.15 | has_source (0.4) + has_content (0.3) + has_title (0.3) |
| Scanner | 0.25 | safe=1.0, low=0.7, medium=0.4, high=0.1, critical=0.0, pending=0.6 |
| Federation | 0.10 | local=1.0, federated_unknown=0.3, federated_known=peer_trust*0.8 |
| Observation mass | 0.10 | 1 - e^(-0.05 * (alpha + beta)) |
| Content-type prior | 0.10 | Per-type defaults (skill=0.7, technique=0.75, convention=0.8, etc.) |
| Recency | 0.10 | 2^(-age_days / 90) |

### Admission Decision

- Hard reject: `scan_tier in ("critical", "high")` OR `score < 0.25`.
- Soft demotion to candidate: `is_federated AND score < 0.40`, or `score < 0.35`.
- Otherwise: admitted, no override.

---

## Trajectory Extraction

`_hook_trajectory_extraction()` in `colony_manager.py` — deterministic,
no LLM. Called after colony completion.

### Gates

- `quality < 0.30` -> skip.
- `productive_ratio < 0.6` (productive_calls / total_calls) -> skip.

### Entry Creation

- Reads `round_records` from colony projection.
- Builds compressed step list: `[{tool, agent_id, round_number}, ...]` (max 30 steps).
- Content: `"Successful {task_class} pattern ({rounds} rounds, quality {quality:.2f}, productivity {ratio:.0%}): {tool_seq}."`
- Fields: `entry_type=skill`, `sub_type=trajectory`, `status=verified` (immediately),
  `decay_class=stable`, `scan_status=safe`, `conf_alpha=max(2.0, quality*10)`,
  `conf_beta=max(2.0, (1-quality)*10)`, `domains=[task_class]`.

---

## Knowledge Feedback Tool

`make_knowledge_feedback_fn()` in `surface/runtime.py` creates an async
callback for agent-provided quality feedback.

### Flow

1. Fetch entry from projections.
2. Apply gamma-decay from last update using decay_class rates:
   `ephemeral=0.98`, `stable=0.995`, `permanent=1.0`.
   Formula: `decayed_alpha = gamma_eff * old_alpha + (1 - gamma_eff) * PRIOR_ALPHA`.
   Elapsed days capped at 180.
3. Update: positive adds +1.0 to alpha; negative adds +1.0 to beta and
   increments `prediction_error_count`.
4. Emit `MemoryConfidenceUpdated` event.

---

## Wave 59 Curation Events

When curating extraction encounters existing entries:

- `MemoryEntryRefined`: `entry_id`, `old_content`, `new_content`, `new_title`,
  `refinement_source="extraction"`, `source_colony_id`.
- `MemoryEntryMerged`: `target_id`, `source_id`, `merged_content`,
  `merged_domains`, `merged_from`, `content_strategy="llm_selected"`,
  `merge_source="extraction"`.

---

## Primary Domain Stamping (Wave 58.5)

Every extracted entry receives `entry["primary_domain"] = task_class` after
`model_dump()`. This field is NOT part of the `MemoryEntry` Pydantic model
(`extra="forbid"`), so it must be stamped on the dict after construction.
Used by the domain-boundary filter in context assembly.

---

## Key Source Files

| File | Purpose |
|------|---------|
| `surface/memory_extractor.py` | Prompt building, parsing, noise filter, harvest |
| `surface/colony_manager.py` | Orchestration, quality gate, trajectory, inline dedup |
| `surface/task_classifier.py` | Task classification for primary_domain |
| `surface/memory_scanner.py` | 5-axis security scoring |
| `surface/credential_scan.py` | detect-secrets credential scanning |
| `surface/admission.py` | 7-signal admission scoring |
| `surface/runtime.py` | Knowledge feedback tool factory |
| `surface/knowledge_constants.py` | PRIOR_ALPHA/BETA, GAMMA_RATES, MAX_ELAPSED_DAYS |
