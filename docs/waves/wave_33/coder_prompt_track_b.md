# Wave 33 Track B — Security + Self-Guiding API Surfaces

## Role

You are a coder implementing credential scanning, StructuredError wiring across all 5 API surfaces, MCP resources and prompts, AG-UI event promotions, and a dynamic Agent Card. You own the security adapter and all outward-facing API surfaces.

## Coordination rules

- `CLAUDE.md` defines the evergreen repo rules. This prompt overrides root `AGENTS.md` for this dispatch.
- Read `docs/decisions/042-event-union-expansion.md` — you do NOT add events, but you need to understand `MemoryEntryMerged` because it changes the dedup handler (Track C owns the dedup modification).
- Read `docs/API_SURFACE_INTEGRATION_REFERENCE.md` sections 6.2 (error inventory) and 8.1 (StructuredError model).
- The composite scoring weights do NOT change.

## File ownership

You OWN these files:

| File | Status | Changes |
|------|--------|---------|
| `surface/credential_scan.py` | CREATE | ~180 LOC: dual-config scanner, redaction function |
| `surface/memory_scanner.py` | MODIFY | 5th axis wiring for credential scan |
| `surface/structured_error.py` | MODIFY | Extend KNOWN_ERRORS to 35+ entries |
| `surface/mcp_server.py` | MODIFY | StructuredError on all tools, resources, prompts, _next_actions, ResourceUpdatedNotification |
| `surface/routes/a2a.py` | MODIFY | StructuredError wiring, next_actions on status, credential redaction |
| `surface/routes/knowledge_api.py` | MODIFY | StructuredError wiring |
| `surface/routes/api.py` | MODIFY | StructuredError wiring |
| `surface/routes/colony_io.py` | MODIFY | StructuredError wiring, credential redaction on transcript |
| `surface/routes/protocols.py` | MODIFY | Dynamic Agent Card |
| `surface/ws_handler.py` | MODIFY | StructuredError wiring |
| `surface/commands.py` | MODIFY | StructuredError wiring |
| `surface/event_translator.py` | MODIFY | 4 AG-UI event promotions |
| `surface/agui_endpoint.py` | MODIFY | StructuredError on error responses |
| `surface/maintenance.py` | MODIFY | credential_sweep handler |
| `surface/app.py` | MODIFY | Register credential_sweep |
| `pyproject.toml` | MODIFY | Add detect-secrets>=1.5,<2.0 |
| `tests/unit/surface/test_credential_scan.py` | CREATE | Credential scanner tests |
| `tests/unit/surface/test_structured_error_wiring.py` | CREATE | StructuredError wiring verification |
| `tests/unit/surface/test_mcp_resources.py` | CREATE | MCP resource + prompt tests |
| `tests/unit/surface/test_agui_promotions.py` | CREATE | AG-UI event promotion tests |

## DO NOT TOUCH

- `surface/colony_manager.py` — Track A owns
- `surface/memory_extractor.py` — Track A owns
- `surface/knowledge_catalog.py` — Track A owns
- `surface/knowledge_constants.py` — Track A owns
- `surface/queen_thread.py` — Track A owns
- `core/events.py` — Track C owns
- `docs/contracts/events.py` — Track C owns
- `core/crdt.py` — Track C owns
- `core/vector_clock.py` — Track C owns
- `surface/trust.py` — Track C owns
- `surface/federation.py` — Track C owns
- `surface/conflict_resolution.py` — Track C owns
- `surface/transcript_view.py` — Track C owns
- `adapters/federation_transport.py` — Track C owns

## Overlap rules

- `surface/app.py`: You register `credential_sweep` handler (B3). Track A registers `cooccurrence_decay` handler (A5). Both are `service_router.register_handler()` calls in the handler registration block (lines 519-534). Add yours AFTER the existing handlers. No conflict — different handler names and different service types.
- `surface/maintenance.py`: You add `make_credential_sweep_handler()` (new function). Track A adds `make_cooccurrence_decay_handler()` (new function) + prediction error criteria to `_handle_stale()` (line 204). Track C modifies `_handle_dedup()` (line 25, replacing `MemoryEntryStatusChanged` emission with `MemoryEntryMerged`). All three touch different functions — no conflict, but verify after integration.
- `surface/projections.py`: You may need to read projection state for MCP resources. Track A and Track C add new projection fields. Read-only access is fine.

---

## B1. Credential scanning via detect-secrets

### What

Create `surface/credential_scan.py` (~180 LOC) wrapping detect-secrets with dual-config for mixed prose/code content.

### Key constraints (from research)

- detect-secrets has NO string-scanning API. Must write to temp files via `SecretsCollection.scan_file()`.
- `transient_settings` modifies global state and is NOT thread-safe. Use multiprocessing for parallel scans, never threading.
- PEM keys detected by header line only — multi-line redaction requires custom post-processing.
- `PotentialSecret.secret_value` is populated during live scans (not from serialized baselines).

### Implementation

```python
"""Credential scanning via detect-secrets with dual-config strategy."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from detect_secrets import settings
from detect_secrets.core.scan import scan_file
from detect_secrets.settings import transient_settings

# Prose config: regex-only, no entropy (Shannon entropy for English prose
# overlaps Base64 threshold at 4.5 bits — massive false positives)
PROSE_PLUGINS = [
    {"name": "AWSKeyDetector"},
    {"name": "AzureStorageKeyDetector"},
    {"name": "BasicAuthDetector"},
    {"name": "CloudantDetector"},
    {"name": "GitHubTokenDetector"},
    {"name": "IbmCloudIamDetector"},
    {"name": "JwtTokenDetector"},
    {"name": "MailchimpDetector"},
    {"name": "NpmDetector"},
    {"name": "PrivateKeyDetector"},
    {"name": "SlackDetector"},
    {"name": "SoftlayerDetector"},
    {"name": "SquareOAuthDetector"},
    {"name": "StripeDetector"},
    {"name": "TwilioKeyDetector"},
]

# Code config: regex + entropy (safe for code blocks)
CODE_PLUGINS = PROSE_PLUGINS + [
    {"name": "Base64HighEntropyString", "limit": 4.5},
    {"name": "HexHighEntropyString", "limit": 3.0},
]

def scan_text(text: str, *, is_code: bool = False) -> list[dict[str, Any]]:
    """Scan text for credentials. Returns list of findings."""
    plugins = CODE_PLUGINS if is_code else PROSE_PLUGINS
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write(text)
        f.flush()
        tmp_path = f.name
    try:
        with transient_settings({"plugins_used": plugins}):
            secrets = scan_file(tmp_path)
        return [
            {
                "type": s.type,
                "line_number": s.line_number,
                "secret_value": s.secret_value,
            }
            for s in secrets
        ]
    finally:
        Path(tmp_path).unlink(missing_ok=True)

def scan_mixed_content(text: str) -> list[dict[str, Any]]:
    """Dual-config scan: prose config on full text, code config on code blocks."""
    findings = scan_text(text, is_code=False)  # Pass 1: regex-only on full text
    # Pass 2: extract code blocks and scan with entropy
    code_blocks = _extract_code_blocks(text)
    for block_text, line_offset in code_blocks:
        code_findings = scan_text(block_text, is_code=True)
        for f in code_findings:
            f["line_number"] += line_offset
        findings.extend(code_findings)
    return _deduplicate_findings(findings)

def redact_credentials(text: str) -> tuple[str, int]:
    """Redact detected credentials. Returns (redacted_text, redaction_count)."""
    findings = scan_mixed_content(text)
    if not findings:
        return text, 0
    lines = text.split("\n")
    count = 0
    # Sort by line number descending for safe in-place replacement
    for finding in sorted(findings, key=lambda f: f["line_number"], reverse=True):
        line_idx = finding["line_number"] - 1
        if 0 <= line_idx < len(lines) and finding["secret_value"]:
            lines[line_idx] = lines[line_idx].replace(
                finding["secret_value"],
                f"[REDACTED:{finding['type']}]",
            )
            count += 1
    return "\n".join(lines), count

def _extract_code_blocks(text: str) -> list[tuple[str, int]]:
    """Extract fenced code blocks with their line offsets."""
    # Split on ``` markers, track line offsets
    ...

def _deduplicate_findings(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Remove duplicate findings (same line + same type)."""
    ...
```

### Dependency

Add to `pyproject.toml`:
```toml
"detect-secrets>=1.5,<2.0",
```

### Tests

- Text with `sk-proj-test123abc` → detected as API key
- Text with `AKIA1234567890ABCDEF` → detected as AWS key
- Prose with high-entropy English words → NOT flagged (prose config, no entropy)
- Code block with base64 string → flagged (code config, entropy enabled)
- `redact_credentials()` replaces secret with `[REDACTED:type]`
- PEM key header detected
- Empty text → no findings

---

## B2. Credential redaction on transcript exports

### Where

- `surface/routes/a2a.py` — `get_task_result()` at line 242. Before returning the transcript, call `redact_credentials()`.
- `surface/routes/colony_io.py` — `get_transcript()` at line 264. Same pattern.

### Implementation

```python
from formicos.surface.credential_scan import redact_credentials

# In get_task_result():
transcript = build_transcript(colony)
# Redact all text fields that might contain tool outputs
for round_data in transcript.get("round_summaries", []):
    for agent in round_data.get("agents", []):
        summary = agent.get("output_summary", "")
        if summary:
            agent["output_summary"], _ = redact_credentials(summary)
```

### Tests

- Transcript with API key in tool output → redacted in response
- Transcript with no secrets → unchanged

---

## B3. Retroactive credential sweep maintenance handler

### Where

`surface/maintenance.py` — new handler function. Register in `surface/app.py` (line 519-534 area).

### Implementation

```python
def make_credential_sweep_handler(runtime: Runtime):
    async def _handle_credential_sweep(query_text: str, ctx: dict[str, Any]) -> str:
        """Re-scan existing entries with current detect-secrets plugins."""
        from formicos.surface.credential_scan import scan_mixed_content
        current_version = 1  # Bump when adding new plugins
        swept = 0
        flagged = 0
        for entry_id, entry in runtime.projections.memory_entries.items():
            scanned_version = entry.get("credential_scan_version", 0)
            if scanned_version >= current_version:
                continue
            content = entry.get("content", "")
            findings = scan_mixed_content(content)
            entry["credential_scan_version"] = current_version
            swept += 1
            if findings:
                # Emit status change to rejected
                await runtime.emit_and_broadcast(
                    MemoryEntryStatusChanged(
                        # ... standard fields ...
                        entry_id=entry_id,
                        old_status=entry.get("status", "candidate"),
                        new_status="rejected",
                        reason=f"credential_sweep:v{current_version}:{findings[0]['type']}",
                        workspace_id=entry.get("workspace_id", ""),
                    )
                )
                flagged += 1
        return f"Swept {swept} entries, flagged {flagged} with credentials"
    return _handle_credential_sweep
```

Register as `"service:consolidation:credential_sweep"` in `app.py`.

### Tests

- Entry with embedded credential + version 0 → scanned, rejected
- Entry with version >= current → skipped
- Entry with no credentials → version updated, not rejected

---

## B4. Wire StructuredError across all 5 surfaces

### What

The `KNOWN_ERRORS` dict in `structured_error.py` (line 144) has 11+ entries. Extend to 35+ entries covering all error paths from the API Surface Integration Reference Section 6.2.

### Existing mappers (verified at lines 57-132)

- `to_mcp_tool_error()` (line 57) — MCP tool errors (dual: text content + structuredContent)
- `to_mcp_protocol_error()` (line 80) — JSON-RPC errors
- `to_http_error()` (line 107) — HTTP status + body + headers
- `to_a2a_task_status()` (line 117) — A2A task status
- `to_ws_error()` (line 132) — WebSocket frames

### Wiring pattern

For each surface, replace inline error strings with structured errors:

**MCP tools** (mcp_server.py, 20 @mcp.tool() decorators starting at line 57):
```python
# Before:
return {"error": "Workspace not found"}
# After:
return to_mcp_tool_error(KNOWN_ERRORS["WORKSPACE_NOT_FOUND"])
```

**A2A routes** (routes/a2a.py):
```python
# Before:
return JSONResponse({"error": "Colony not found"}, status_code=404)
# After:
status, body, headers = to_http_error(KNOWN_ERRORS["COLONY_NOT_FOUND"])
return JSONResponse(body, status_code=status, headers=headers)
```

**WebSocket** (ws_handler.py):
```python
# Before:
await ws.send_json({"error": "Unknown command"})
# After:
await ws.send_json(to_ws_error(KNOWN_ERRORS["INVALID_COMMAND"]))
```

**REST routes** (routes/api.py, routes/knowledge_api.py, routes/colony_io.py): Same as A2A.

**AG-UI** (agui_endpoint.py): Same as REST.

### New KNOWN_ERRORS to add

Audit each surface file for inline `{"error": ...}` patterns. Expected additions include:
- `THREAD_NOT_FOUND`, `COLONY_RUNNING` (cannot modify), `BUDGET_EXCEEDED`
- `INVALID_CASTES`, `MODEL_NOT_AVAILABLE`, `EMBEDDING_UNAVAILABLE`
- `APPROVAL_NOT_FOUND`, `STEP_NOT_FOUND`, `TEMPLATE_NOT_FOUND` (some may exist)
- `INVALID_COMMAND`, `RATE_LIMITED`, `CONTEXT_TOO_LARGE`
- Surface-specific variants as discovered during audit

Each KNOWN_ERROR entry needs: error_code, message, http_status, recovery_hint, suggested_action.

### Tests

- Each surface returns StructuredError format on known error condition
- MCP tool error has both text content AND structuredContent
- HTTP errors include correct status codes
- WebSocket errors match ws_error frame format

---

## B5. MCP resources for knowledge catalog and workflow state

### Where

`surface/mcp_server.py` — inside `create_mcp_server()` (line 49).

### Implementation

Five resources using the `@mcp.resource()` decorator:

```python
@mcp.resource("formicos://knowledge")
async def knowledge_catalog(
    workspace: str = "",
    domain: str = "",
    min_confidence: float = 0.0,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """List knowledge entries with optional filters."""
    entries = runtime.projections.memory_entries
    # Filter by workspace, domain, min confidence
    # Return list of entry summaries (id, title, type, confidence, domains)
    ...

@mcp.resource("formicos://knowledge/{entry_id}")
async def knowledge_entry(entry_id: str) -> dict[str, Any]:
    """Get a single knowledge entry."""
    ...

@mcp.resource("formicos://threads/{workspace_id}")
async def workspace_threads(workspace_id: str) -> list[dict[str, Any]]:
    """List threads in a workspace."""
    ...

@mcp.resource("formicos://threads/{workspace_id}/{thread_id}")
async def thread_detail(workspace_id: str, thread_id: str) -> dict[str, Any]:
    """Get thread detail with workflow steps."""
    ...

@mcp.resource("formicos://colonies/{colony_id}")
async def colony_detail(colony_id: str) -> dict[str, Any]:
    """Get colony status, stats, and outcome."""
    ...
```

**ResourceUpdatedNotification:** After mutating tools (spawn_colony, chat_colony, etc.) that change knowledge, thread, or colony state, call:
```python
await mcp.notify_resource_updated("formicos://knowledge")
await mcp.notify_resource_updated(f"formicos://colonies/{colony_id}")
```

ResourcesAsTools transform (registered in Wave 32.5) automatically exposes these as tools for Cursor/Windsurf.

### Tests

- `formicos://knowledge` returns entries from projection
- `formicos://knowledge/{id}` returns single entry or error
- Mutation → ResourceUpdatedNotification sent

---

## B6. MCP prompts for structured interaction

### Where

`surface/mcp_server.py` — inside `create_mcp_server()`.

### Implementation

```python
@mcp.prompt("knowledge-query")
async def knowledge_query_prompt(domain: str, question: str) -> str:
    """Build a prompt with relevant knowledge entries and the user's question."""
    entries = await _search_knowledge(domain, question, top_k=5)
    context = "\n".join(f"- {e['title']}: {e['content'][:200]}" for e in entries)
    return f"Based on this knowledge:\n{context}\n\nAnswer: {question}"

@mcp.prompt("plan-task")
async def plan_task_prompt(goal: str, workspace_id: str) -> str:
    """Build a prompt with workspace context for task planning."""
    threads = _get_workspace_threads(workspace_id)
    templates = _get_templates()
    return f"Goal: {goal}\n\nActive threads:\n{threads}\n\nAvailable templates:\n{templates}"
```

PromptsAsTools transform (registered in Wave 32.5) exposes as tools for clients without native prompt support.

### Tests

- `knowledge-query` prompt includes relevant entries
- `plan-task` prompt includes workspace threads

---

## B7. Extend _next_actions to all mutating MCP tools + A2A status

### Where

`surface/mcp_server.py` — all 11 mutating tools. Currently only `spawn_colony` (line 100) has `_next_actions`.

### Implementation

Each mutating tool's return dict gets `_next_actions` and `_context`. The 11 mutating MCP tools (8 _MUT + 3 _DEST, excluding `approve` which returns the colony status directly) are:

| Tool | Annotation | _next_actions | _context |
|------|------------|---------------|----------|
| `create_workspace` | _MUT | `["create_thread", "list_workspaces"]` | workspace_id |
| `create_thread` | _MUT | `["spawn_colony", "chat_queen"]` | thread_id |
| `spawn_colony` | _MUT | `["get_status", "chat_colony"]` | colony_id *(already has this from Wave 32.5)* |
| `chat_queen` | _MUT | `["spawn_colony", "get_status"]` | thread_id |
| `create_merge` | _MUT | `["get_status"]` | edge_id |
| `broadcast` | _MUT | `["get_status"]` | colony_id |
| `activate_service` | _MUT | `["query_service", "get_status"]` | colony_id |
| `kill_colony` | _DEST | `["spawn_colony", "list_workspaces"]` | colony_id |
| `prune_merge` | _DEST | `["get_status"]` | edge_id |
| `approve` | _DEST | `["get_status"]` | request_id |
| `deny` | _DEST | `["get_status"]` | request_id |

**Verify tool names against the actual `@mcp.tool()` functions in `mcp_server.py`** before implementing. The 8 read-only tools (`list_workspaces`, `get_status`, `list_templates`, `get_template_detail`, `suggest_team`, `code_execute`, `query_service`, `chat_colony`) do NOT get `_next_actions`.

**A2A status envelope** — in `routes/a2a.py`, add `next_actions` to status:
- Running tasks: `["poll", "attach", "cancel"]`
- Completed tasks: `["result"]`
- Failed tasks: `["result", "retry"]`

### Tests

- Each mutating MCP tool returns `_next_actions` array
- A2A running task status includes `["poll", "attach", "cancel"]`

---

## B8. AG-UI event promotions (4 remaining)

### Where

`surface/event_translator.py` — `translate_event()` at line 150. The Wave 32.5 pattern for APPROVAL_NEEDED is at line 171-174.

### Implementation

Add 4 more handlers before the `else` clause, following the same pattern:

```python
# Existing (Wave 32.5):
if isinstance(event, ApprovalRequested):
    yield {"type": "CUSTOM", "name": "APPROVAL_NEEDED", "data": json.dumps({...})}

# New promotions:
elif isinstance(event, MemoryEntryCreated):
    entry = event.entry
    yield {"type": "CUSTOM", "name": "KNOWLEDGE_EXTRACTED", "data": json.dumps({
        "entry_id": entry.get("id", ""),
        "entry_type": entry.get("entry_type", ""),
        "domains": entry.get("domains", []),
        "scan_status": entry.get("scan_status", "pending"),
    })}

elif isinstance(event, MemoryConfidenceUpdated):
    yield {"type": "CUSTOM", "name": "CONFIDENCE_UPDATED", "data": json.dumps({
        "entry_id": event.entry_id,
        "old_confidence": event.old_alpha / (event.old_alpha + event.old_beta),
        "new_confidence": event.new_confidence,
        "reason": event.reason,
    })}

elif isinstance(event, KnowledgeAccessRecorded):
    yield {"type": "CUSTOM", "name": "KNOWLEDGE_ACCESSED", "data": json.dumps({
        "colony_id": event.colony_id,
        "access_mode": event.access_mode,
        "item_count": len(event.items),
    })}

elif isinstance(event, WorkflowStepCompleted):
    yield {"type": "CUSTOM", "name": "STEP_COMPLETED", "data": json.dumps({
        "step_index": event.step_index,
        "colony_id": event.colony_id,
        "success": event.success,
    })}
```

### Tests

- MemoryEntryCreated → KNOWLEDGE_EXTRACTED SSE frame (not generic CUSTOM)
- MemoryConfidenceUpdated → CONFIDENCE_UPDATED frame with old/new confidence
- KnowledgeAccessRecorded → KNOWLEDGE_ACCESSED frame
- WorkflowStepCompleted → STEP_COMPLETED frame

---

## B9. Dynamic Agent Card with live state

### Where

`surface/routes/protocols.py` — `agent_card()` at line 25.

### Implementation

Enrich the static agent card with computed fields from projections:

```python
async def agent_card(request: Request) -> JSONResponse:
    runtime = request.app.state.runtime
    proj = runtime.projections

    # Compute knowledge domains with counts and avg confidence
    domains = _compute_domain_stats(proj.memory_entries)

    card = {
        # ... existing static fields ...
        "knowledge": {
            "total_entries": len(proj.memory_entries),
            "domains": domains,  # [{name, count, avg_confidence}]
        },
        "threads": {
            "active_count": sum(1 for t in proj.threads.values() if t.get("status") == "active"),
        },
        "federation": {
            "enabled": hasattr(runtime, "federation_manager"),
            "peer_count": 0,  # populated when federation lands
            "trust_scores": {},
        },
        "hardware": {
            "gpu_available": _check_gpu(),
        },
    }
    return JSONResponse(card)
```

### Tests

- Agent Card includes knowledge_domains with entry counts
- Agent Card includes active thread count
- Agent Card includes federation section (enabled=False when not configured)

---

## Validation

Run after all changes:
```bash
ruff check src/ && pyright src/ && python scripts/lint_imports.py && pytest
```

All must pass. Pay special attention to imports — `surface/credential_scan.py` imports from detect-secrets (external dep), which is fine for surface layer. Do NOT import detect-secrets from core or engine.
