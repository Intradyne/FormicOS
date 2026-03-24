# Wave 52 — Control-Plane Coherence Findings

## Purpose

Ordered findings from the Wave 52 capability/control-plane audit.
Distinguishes truth mismatches from intentional asymmetry, and identifies
the bounded fix set for a potential Wave 52 execution packet.

---

## Final Answers

### What is the canonical external contract today?

The **Agent Card** at `/.well-known/agent.json` is the only surface that
describes the whole system in a single response. It is dynamically generated,
includes live state (knowledge stats, thread count, specialist status, GPU),
and accurately describes all three protocol endpoints.

Internally, the **CapabilityRegistry** (ADR-036) is the programmatic source
of truth, exposed at `GET /debug/inventory`.

### What are the 3 highest-value coherence fixes?

1. **Event count drift in CLAUDE.md** — says "64 events", multiple older docs still say 62.
   Multiple wave docs say 62. Simple text fix, high confusion potential.

2. **Protocol transport naming inconsistency** — registry says
   `"Streamable HTTP"`, view_state fallback says `"streamable_http"`.
   Frontend displays whichever it receives. Should be consistent.

3. **REST-only forager controls have no MCP equivalent** — forager trigger
   and domain override are powerful capabilities only reachable via REST.
   Adding MCP tools would make them programmatically accessible to
   integrators without going through the operator UI.

### What should remain intentionally asymmetric?

- **Queen vs MCP tool sets:** Queen has redirect/escalate/workflow tools
  because those require LLM judgment and thread context. MCP has
  code_execute/configure_scoring because those are operator-initiated.
  This split is correct.
- **A2A deterministic team selection:** A2A intentionally avoids LLM for
  team suggestion to keep the external intake path predictable.
- **WS rename commands:** Rename is a UI convenience, not a programmatic
  need. WS-only is fine.
- **REST diagnostic endpoints:** Retrieval diagnostics, knowledge graph,
  colony audit, thread timeline are operator dashboard features.
  MCP equivalents would add complexity without clear integrator value.

### What should definitely NOT be expanded yet?

- No new protocol implementations (AG-UI Tier 2, A2A JSON-RPC conformance)
- No MCP equivalents for colony I/O (file upload/export) — these are
  operator workflow features
- No Queen tools for caste/model CRUD — these are admin operations
- No federation protocol expansion
- No token-level AG-UI streaming (ADR-035 decision is sound)

---

## Findings by Severity

### S1: Truth Mismatch (docs/code disagree about current state)

#### F1: Event count drift across documentation

**Where:** CLAUDE.md line 5 says "64 events", Wave 51
`backend_capability_inventory.md` says "62 events", Wave 46 docs say "62",
`session_decisions_2026_03_19.md` says "62 events (+2 = 64)".

**Actual:** 64 event types in the `FormicOSEvent` union.

**Fix:** Update older docs that still say 62 so the packet aligns on 64.

#### F2: Protocol transport naming inconsistency

**Where:** `registry.py` registers MCP transport as `"Streamable HTTP"`.
`view_state.py` fallback (line 328) uses `"streamable_http"` (snake_case).

**Impact:** Frontend settings-view displays the raw transport string. If
the registry path is used (normal case), operator sees "Streamable HTTP".
If fallback triggers, operator sees "streamable_http". Inconsistent.

**Fix:** Normalize fallback to `"Streamable HTTP"` to match registry.

#### F3: ADR status labels outdated

**Where:** ADR-045 (ParallelPlanCreated, KnowledgeDistilled), ADR-046
(MaintenanceDispatcher autonomy levels), ADR-047 (ColonyOutcome metrics)
are all marked "Proposed" in their documents.

**Actual:** All three are fully implemented, tested, and operational.
Events are in the union, code is in production paths.

**Fix:** Update ADR status to "Accepted" or "Implemented".

---

### S2: Stale Fallback / Dead Code (currently harmless, future risk)

#### F4: AG-UI "Not implemented · planned" text in settings-view

**Where:** `settings-view.ts` line 75:
```
: 'Not implemented · planned'
```

**Context:** AG-UI status is always `"active"` (both registry and fallback
paths return active). This fallback text can never be reached. But it's
wrong — AG-UI IS implemented. If the registry ever returned inactive, the
UI would display false information.

**Risk:** Low (dead code path). Fix is simple: change to
`'Inactive'` or remove the branch.

#### F5: A2A "Agent Card discovery only" text in settings-view

**Where:** `settings-view.ts` line 77:
```
? (a2aProto?.note ?? 'Agent Card discovery only')
```

**Context:** A2A status is always `"active"`. This text is dead code.
When A2A was planned, "Agent Card discovery only" was accurate. Now it's
stale.

**Risk:** Low. Same fix pattern as F4.

#### F6: Hardcoded fallback tool/event counts in view_state.py

**Where:** `view_state.py` lines 317, 323:
```python
mcp_tools = 19  # known tool count from mcp_server.py
agui_events = 9
```

**Context:** These are fallbacks for when the registry or imports fail.
The primary path uses dynamic counts from the registry. If tools are
added or removed, these fallbacks become wrong.

**Risk:** Low (fallback path rarely triggered). But they accumulate drift.
Consider removing the hardcoded fallbacks entirely — if the import fails,
return 0 with a note instead of a stale number.

#### F7: Agent Card version hardcoded

**Where:** `protocols.py` returns `"version": "0.22.0"` in the agent card.

**Context:** This should come from the package version or registry, not
a hardcoded string.

**Risk:** Medium. External integrators may cache or compare versions.

---

### S3: Capability Gap (powerful but buried or unreachable)

#### F8: Forager controls are REST-only

**Where:** Four forager endpoints exist only in REST:
- `POST /forager/trigger` — manual forage
- `POST /forager/domain-override` — trust/distrust/reset
- `GET /forager/cycles` — cycle history
- `GET /forager/domains` — domain strategies

**Impact:** MCP integrators and the Queen cannot trigger foraging or
manage domain trust programmatically. The operator must use the UI or
make raw HTTP calls.

**Recommendation:** Add MCP tools for `trigger_forage` and
`forager_domain_override`. The read-only endpoints are lower priority.

#### F9: Knowledge promotion is REST-only

**Where:** `POST /knowledge/{id}/promote` exists only in REST.

**Impact:** Queen and MCP integrators cannot promote knowledge entries.
The Queen has `memory_search` but no `promote_entry`. Promotion requires
the operator UI.

**Recommendation:** Consider adding a Queen tool or MCP tool for
knowledge promotion. This aligns with the earned-autonomy story.

#### F10: Colony audit view not surfaced in frontend

**Where:** `GET /colonies/{id}/audit` returns structured audit data.
No frontend component consumes it.

**Impact:** The audit data exists but is only accessible via raw API call.
Could be valuable in the colony detail panel.

**Recommendation:** Defer to a UI wave. The endpoint works correctly.

---

### S4: Naming / Vocabulary Drift (same concept, different names)

#### F11: MCP/Queen template inspection names diverge

**Where:**
- MCP: `get_template_detail`
- Queen: `inspect_template`

**Impact:** Minor cognitive overhead for developers working across surfaces.
Both return the same data.

**Recommendation:** Low priority. Document the equivalence.

#### F12: MCP `chat_queen` vs WS `send_queen_message`

**Where:**
- MCP: `chat_queen(workspace_id, thread_id, content)`
- WS: `send_queen_message` with `{workspaceId, threadId, content}`

**Impact:** Same operation, different names. Parameters also use different
casing conventions (snake_case vs camelCase), which is expected for
MCP vs WS but still adds surface area.

**Recommendation:** Document the equivalence. Don't rename.

---

### S5: Already Good (verified coherent)

#### G1: Single mutation path is consistently enforced

All surfaces — MCP, Queen, WS, REST, A2A, AG-UI — funnel mutations through
`runtime.emit_and_broadcast()`. No shadow databases. No bypassed event
stores. This is the strongest architectural invariant and it holds.

#### G2: Agent Card is dynamically accurate

The agent card at `/.well-known/agent.json` reads live state from
projections, registry, templates, and hardware detection. It does not
hardcode capability claims (except version — see F7). External integrators
get an accurate picture.

#### G3: CapabilityRegistry (ADR-036) is the single internal source

Protocol status flows from registry → view_state → WS snapshot → frontend.
No competing registries. Agent card and debug inventory both read from
the same registry.

#### G4: A2A / AG-UI share event translator

Both external SSE surfaces use the same `event_translator.translate_event()`
function. Event shapes are identical across surfaces. No drift between
A2A events and AG-UI events.

#### G5: WS snapshot includes all protocol status

The `OperatorStateSnapshot` sent on WS subscribe includes `protocolStatus`
with tools/events counts, endpoints, and transports. Frontend gets
accurate protocol information on connect.

#### G6: Error model convergence

StructuredError with KNOWN_ERRORS registry (35+ codes) is used across
all five operator surfaces. Legacy string errors exist in some adapter
paths but are being converged.

#### G7: Knowledge API unification

The old `/api/v1/memory/*` endpoints are deprecated with RFC 8594 Sunset
headers. Unified `/api/v1/knowledge/*` endpoints serve both institutional
memory and legacy skill bank. Clean migration path.

#### G8: A2A task ID === colony ID

No second store for A2A tasks. Task lifecycle maps directly to colony
lifecycle. Status polling reads from the same ProjectionStore as all
other surfaces.

---

## Wave 52 Fix Candidates (if packet is warranted)

| ID | Fix | Scope | Effort |
|----|-----|-------|--------|
| F1 | Update stale event counts in older docs to 64 | Docs only | Trivial |
| F2 | Normalize transport string in view_state fallback | 1 line in view_state.py | Trivial |
| F3 | Update ADR-045/046/047 status labels | Docs only | Trivial |
| F4 | Fix AG-UI inactive fallback text in settings-view | 1 line in settings-view.ts | Trivial |
| F5 | Fix A2A inactive fallback text in settings-view | 1 line in settings-view.ts | Trivial |
| F6 | Remove or update hardcoded fallback counts | 2 lines in view_state.py | Trivial |
| F7 | Source agent card version from package metadata | ~5 lines in protocols.py | Small |
| F8 | Add MCP tools for forager trigger + domain override | ~80 lines in mcp_server.py | Medium |
| F9 | Add MCP/Queen tool for knowledge promotion | ~40 lines | Small |

**Recommended packet scope:** F1–F7 (trivial/small fixes, pure coherence).
F8–F9 are capability additions and should be evaluated separately.

---

## Audit Completeness

| Track | Status |
|-------|--------|
| A: Canonical Capability Truth | Complete — inventory produced |
| B: Protocol Status / Capability Drift | Complete — F1–F7 identified |
| C: Control-Plane Asymmetry | Complete — intentional vs accidental separated |
| D: Reachability / Power | Complete — F8–F10 identified |
