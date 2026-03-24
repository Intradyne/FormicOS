# Wave 19 Plan — The Queen Steers

**Wave:** 19 — "The Queen Steers"
**Theme:** Strategic steering, safe carry-forward of results, human-approved learning.
**Contract changes:** +1 event (`ColonyRedirected`). Union 36 → 37. `ColonySpawned` gains `input_sources` field. Colony projection gains `active_goal`, `redirect_history`. Ports frozen.
**Estimated LOC delta:** ~350 Python, ~80 TypeScript

---

## Wave 19 Is an Adaptive Execution Wave

Wave 18 gave the Queen eyes (inspect_colony, list_templates, list_skills) and hands (suggest_config_change). Wave 19 gives her judgment — the ability to steer a colony mid-run, chain colony results forward, approve config changes, and escalate compute when needed.

The product gap this closes: the Queen is currently fire-and-forget. She spawns a colony and has no mid-flight steering. If a colony goes down the wrong path, the only options are let it burn budget or kill it. After Wave 19, the Queen can redirect a struggling colony, feed one colony's output into the next, and apply learned config changes — all with full operator visibility and audit trails.

Wave 19 is NOT an autonomy wave. Every Queen action is either operator-visible in the thread, operator-approved before taking effect, or constrained by a configurable cap. The Queen steers; the operator decides how much steering is allowed.

---

## Tracks

Three parallel tracks. Track A is the main event.

### Track A — REDIRECT + Governance Trigger (ADR-032)

**Goal:** The Queen can reframe a colony's goal mid-run when she detects it's going off-track. One redirect per colony by default.

**A1. ColonyRedirected event.**
New event type in the closed union (36 → 37):

```python
class ColonyRedirected(BaseModel):
    model_config = FrozenConfig
    kind: Literal["ColonyRedirected"] = "ColonyRedirected"
    seq: int
    timestamp: datetime
    address: str
    colony_id: str
    redirect_index: int          # 0-based, supports future multi-redirect
    original_goal: str           # immutable original task
    new_goal: str                # what the colony works toward now
    reason: str                  # Queen's rationale
    trigger: str                 # "queen_inspection" | "governance_alert" | "operator_request"
    round_at_redirect: int       # which round the redirect occurred at
```

`redirect_index` makes skill extraction boundaries and UI rendering unambiguous. The original task is carried for audit — never overwritten.

Files touched:
- `src/formicos/core/events.py` — add `ColonyRedirected`, update union (36 → 37)
- `docs/contracts/events.py` — mirror
- `frontend/src/types.ts` — mirror

**A2. Colony projection: active_goal + redirect_history.**
The colony projection gains:
- `active_goal: str` — initialized to `task` at spawn, updated on redirect
- `redirect_history: list[dict]` — append-only log of `{new_goal, reason, trigger, round, redirect_index}`

Context assembly in `engine/context.py` reads `active_goal` instead of `task` for the goal tier. The original `task` remains on the projection unchanged.

Files touched:
- `src/formicos/surface/projections.py` — add `active_goal` and `redirect_history` fields to `ColonyProjection`, add `_on_colony_redirected` handler
- `src/formicos/engine/context.py` — read `active_goal` from colony state for goal assembly

**A3. Queen tool: redirect_colony.**
```python
{
    "name": "redirect_colony",
    "description": (
        "Redirect a running colony to a new goal. The colony keeps its team "
        "and topology but works toward the new goal from the next round. "
        "One redirect per colony by default."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "colony_id": {"type": "string"},
            "new_goal": {"type": "string", "description": "Clear reframed goal."},
            "reason": {"type": "string", "description": "Why this redirect is needed."},
        },
        "required": ["colony_id", "new_goal", "reason"],
    },
}
```

Handler:
1. Find colony in projections. Reject if not `running`.
2. Check redirect cap: `len(redirect_history) < max_redirects_per_colony` (default 1, configurable in governance config).
3. Emit `ColonyRedirected` event.
4. Reset convergence/stall detection window on the colony (colony_manager clears the stall detector's sliding window).
5. Do NOT reset pheromone weights — topology is team chemistry, not task-specific.

Files touched:
- `src/formicos/surface/queen_runtime.py` — add tool definition and handler
- `src/formicos/surface/colony_manager.py` — handle `ColonyRedirected`: update active_goal, reset stall window, log redirect boundary for skill extraction

**A4. Governance alert → Queen notification.**
When the governance engine detects early stall signals (repeated outputs within the stall detection window, before escalating to force-halt), it directly notifies the Queen rather than setting hidden projection state.

Implementation: `colony_manager.py` already runs the governance check after each round. When a governance warning is emitted (existing chat message path), additionally call `queen_agent.on_governance_alert(colony_id, workspace_id, thread_id, alert_type)`. This method:
1. Checks preconditions: colony was Queen-spawned, thread is recently active (30 min), no redirect already issued this colony.
2. Calls `inspect_colony` internally.
3. Decides: REDIRECT with a reframed goal, or note in chat ("Colony may be struggling, monitoring").
4. At most one Queen reaction per governance alert per colony.

This consumes the existing governance warning signal — no new event, no hidden mutable state. The Queen's reaction is visible in the thread as a chat message (either a redirect confirmation or a monitoring note).

Files touched:
- `src/formicos/surface/queen_runtime.py` — add `on_governance_alert()` method
- `src/formicos/surface/colony_manager.py` — call `on_governance_alert` when governance warning fires

**A5. Skill extraction boundary tagging.**
When skill crystallization runs at colony completion (existing path in `colony_manager.py`), skills extracted from rounds before the redirect are tagged with `pre_redirect: true` and the original goal. Skills from rounds after the redirect are tagged with the new goal. This prevents the skill bank from learning "approaches that needed correction" as positive patterns.

Implementation: the Archivist's extraction prompt receives the redirect boundary (round number). Skills carry `redirect_context: {pre_redirect: bool, goal_at_extraction: str}` in their Qdrant payload metadata.

Files touched:
- `src/formicos/surface/colony_manager.py` — pass redirect boundary to skill extraction

---

### Track B — Colony Chaining + Config Approval (ADR-033)

**Goal:** Colony outputs feed forward into new colonies. Config proposals graduate from text-only to approve → apply → persist.

**B1. input_sources on ColonySpawned.**
Add `input_sources: list[InputSource]` to `ColonySpawned` event. Wave 19 implements one source type:

```python
class InputSource(BaseModel):
    model_config = FrozenConfig
    type: Literal["colony"]       # future: "file", "url", "skill_set"
    colony_id: str                # source colony (must be completed)
    summary: str = ""             # resolved at spawn time, not stored as reference
```

Resolution at spawn time: when `spawn_colony` receives `input_sources`, the runtime reads the completed source colony's compressed output (last round's Archivist summary if available, otherwise the truncated final round outputs — max 2000 tokens). The resolved summary is stored on the `InputSource.summary` field and injected as seed context in the new colony's first round via `engine/context.py`.

If the source colony is not completed, the spawn is rejected with a clear error: "Source colony {id} is not completed. Chain only from finished colonies."

The Queen's `spawn_colony` tool gains an optional `input_from` parameter (single colony_id for v1). The tool handler wraps it into `input_sources: [InputSource(type="colony", colony_id=...)]`.

Files touched:
- `src/formicos/core/events.py` — add `input_sources` field to `ColonySpawned` (optional, default empty list)
- `src/formicos/core/types.py` — add `InputSource` model
- `src/formicos/surface/queen_runtime.py` — add `input_from` parameter to `spawn_colony` tool
- `src/formicos/surface/runtime.py` — resolve input sources at spawn time
- `src/formicos/engine/context.py` — inject resolved input source summaries in the seed context tier
- `frontend/src/types.ts` — mirror `InputSource` type

**B2. Config approval completion.**
Wave 18's `suggest_config_change` emits a text-only proposal in chat. Wave 19 closes the loop.

When the Queen proposes a config change, she also stores a **pending proposal** record in memory:

```python
@dataclass
class PendingConfigProposal:
    proposal_id: str              # short hash of param_path + proposed_value
    thread_id: str
    param_path: str
    proposed_value: str
    current_value: str
    reason: str
    proposed_at: datetime
    ttl_minutes: int = 30         # expires after 30 min
```

Pending proposals are thread-scoped (one active proposal per thread) with a TTL. When the operator says "approve" or "yes", the Queen calls `approve_config_change`:

1. Find the pending proposal for this thread. If expired or none, reply "No pending proposal to approve."
2. Re-validate through both gates (config_validator + experimentable_params). State may have changed.
3. Apply the change via the existing `update_config` path in `runtime.py` / `config_endpoints.py`.
4. Persist to YAML via existing `save_castes()` or `save_model_registry()` path.
5. Emit `WorkspaceConfigChanged` event.
6. Clear the pending proposal.
7. Confirm in chat: "Applied: {param_path} changed from {old} to {new}."

The proposal_id (hash) prevents ambiguity — "approve" always applies to the most recent proposal in that thread. If the operator wants to reject, they say "no" or just move on (TTL expires).

Files touched:
- `src/formicos/surface/queen_runtime.py` — add `PendingConfigProposal` dataclass, pending proposal storage (dict keyed by thread_id), `approve_config_change` tool, TTL check in `suggest_config_change`

---

### Track C — Tier Escalation + Audit UX + Agent Card (Stretch)

**Goal:** The Queen can escalate a colony's compute tier. The operator sees redirect history and config audit trails. Agent Card is a stretch goal.

**C1. Tier escalation tool.**
`escalate_colony(colony_id, tier, reason)` sets a colony-scoped routing override. The compute router in `engine/runner.py` checks this override before consulting the caste×phase routing table.

```python
{
    "name": "escalate_colony",
    "description": (
        "Escalate a running colony to a higher compute tier for remaining rounds. "
        "Does not change the team — only routes to more capable models."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "colony_id": {"type": "string"},
            "tier": {
                "type": "string",
                "enum": ["standard", "heavy", "max"],
                "description": "Target tier: standard (local), heavy (cloud), max (Opus).",
            },
            "reason": {"type": "string"},
        },
        "required": ["colony_id", "tier", "reason"],
    },
}
```

The override is stored on the colony projection as `routing_override: {tier, reason, set_at_round}`. It's colony-scoped and transient — doesn't survive restart (colonies don't fully survive restart anyway). The telemetry bus already logs routing decisions with reason codes, so escalations are captured in `telemetry.jsonl` for audit.

The compute router in `runner.py` checks: if `colony.routing_override` exists, map the tier to a model (`standard` → local default, `heavy` → Sonnet, `max` → Opus) and use it instead of the caste×phase table for that colony.

Files touched:
- `src/formicos/surface/queen_runtime.py` — add tool definition and handler
- `src/formicos/surface/projections.py` — add `routing_override` field to ColonyProjection
- `src/formicos/engine/runner.py` — check routing_override before caste×phase table

**C2. Operator-facing audit UX.**
Colony detail view in the frontend gains:
- **Redirect history panel:** Shows original goal, each redirect (new_goal, reason, trigger, round), with visual boundary markers on the round timeline.
- **Config change log:** Shows approved config changes with before/after values, timestamps, and Queen reasoning.
- **Escalation indicator:** Badge on colony card when routing_override is active, with tier and reason tooltip.

Files touched:
- `src/formicos/surface/view_state.py` — include `active_goal`, `redirect_history`, `routing_override` in colony snapshot
- `frontend/src/types.ts` — add redirect_history, routing_override to Colony type
- `frontend/src/components/colony-detail.ts` (or equivalent) — render redirect history, escalation badge

**C3. Agent Card endpoint (stretch).**
Serve `/.well-known/agent.json` from `app.py`. Auto-generated from loaded templates:

```python
@app.route("/.well-known/agent.json")
async def agent_card(request):
    templates = load_templates()
    skills = [
        {
            "id": t.template_id,
            "name": t.name,
            "description": t.description,
            "tags": t.tags,
            "examples": [f"Run a {t.name.lower()} task"],
        }
        for t in templates
    ]
    card = {
        "name": "FormicOS",
        "description": "Stigmergic multi-agent colony framework",
        "url": f"http://{request.base_url.hostname}:{request.base_url.port}",
        "version": "0.19.0",
        "capabilities": {
            "streaming": False,
            "pushNotifications": False,
        },
        "defaultInputModes": ["text/plain"],
        "defaultOutputModes": ["text/plain"],
        "skills": skills,
    }
    return JSONResponse(card)
```

~50 LOC. No `a2a-sdk` dependency. Honestly advertises no streaming or push notification support. Other agents can discover FormicOS and see what it can do. Task handling comes later.

Files touched:
- `src/formicos/surface/app.py` — add `/.well-known/agent.json` route

---

## Execution Shape for 3 Parallel Coder Teams

| Team | Track | First Lands On | Dependencies |
|------|-------|-----------------|--------------|
| **Coder 1** | A (REDIRECT) | `events.py`, `projections.py`, `queen_runtime.py`, `colony_manager.py` | None — starts immediately |
| **Coder 2** | B (Chaining + Config) | `types.py`, `runtime.py`, `context.py`, `queen_runtime.py` | Rereads `queen_runtime.py` after Coder 1 lands A3 |
| **Coder 3** | C (Escalation + Audit UX) | `runner.py`, `view_state.py`, frontend | Rereads `projections.py` after Coder 1 lands A2 |

### Serialization Rules

- **Coder 1 lands A1-A2 first** on `events.py` and `projections.py` (new event + projection fields)
- **Coder 2 rereads** `queen_runtime.py` after Coder 1 lands A3 (tool surface), then adds `input_from` and `approve_config_change`
- **Coder 3 rereads** `projections.py` after Coder 1 lands A2, then adds `routing_override` field and snapshot wiring

### Overlap-Prone Files

| File | Teams | Resolution |
|------|-------|------------|
| `queen_runtime.py` | 1 + 2 | Coder 1 first (redirect_colony + on_governance_alert), Coder 2 rereads before adding input_from + approve_config_change |
| `projections.py` | 1 + 3 | Coder 1 first (active_goal + redirect_history + handler), Coder 3 rereads before adding routing_override |
| `events.py` | 1 + 2 | Coder 1 adds ColonyRedirected. Coder 2 adds input_sources to ColonySpawned. Non-overlapping changes but both modify the union — coordinate via sequential merge. |
| `colony_manager.py` | 1 only | No overlap (redirect handling + governance alert trigger) |
| `formicos.yaml` | — | No changes this wave |
| `docker-compose.yml` | — | No changes this wave |

---

## Acceptance Criteria

Wave 19 is complete when:

1. **REDIRECT works end-to-end.** Queen inspects struggling colony → calls redirect_colony → colony's next round uses new goal → original task preserved in audit → redirect_history visible in UI.
2. **One-redirect cap enforced.** Second redirect attempt returns clear rejection. Cap is configurable in governance config.
3. **Governance alert triggers Queen inspection.** Stall detection → Queen notified → Queen inspects → either redirects or notes in chat. Only for Queen-spawned colonies in active threads.
4. **Colony chaining works.** Spawn colony B with `input_from: colony_A_id` → colony B's first round context includes compressed summary from colony A → source attribution visible.
5. **Config approval completes the loop.** Queen proposes → pending proposal stored → operator says "approve" → re-validated → applied → persisted → confirmed in chat. Expired proposals handled gracefully.
6. **Tier escalation routes correctly.** Queen escalates colony → next round uses upgraded model → telemetry logs the routing override reason.
7. **Skill extraction respects redirect boundaries.** Pre-redirect skills tagged separately from post-redirect skills.
8. **Audit UX renders.** Colony detail shows redirect history, escalation badge, original vs. active goal.
9. **All CI gates green.** `ruff check src/ && pyright src/ && python scripts/lint_imports.py && pytest`

### Smoke Traces

1. **Redirect flow:** Spawn colony → wait for stall → Queen redirects → colony continues with new goal → completes → skills tagged with redirect boundary
2. **Governance-triggered redirect:** Spawn colony that will stall (e.g., ambiguous task on local model) → governance warns → Queen auto-inspects → Queen redirects with clearer goal
3. **Chain flow:** Spawn colony A (research task) → colony A completes → spawn colony B with `input_from: colony_A_id` → colony B's context includes A's output summary
4. **Config approval flow:** Ask Queen to adjust coder temperature → Queen proposes → operator says "approve" → change applied → persists across restart
5. **Config rejection flow:** Wait 30+ minutes → say "approve" → "No pending proposal" response
6. **Escalation flow:** Spawn colony on local model → Queen escalates to heavy → next round routes to Sonnet → telemetry shows override reason

---

## Not In Wave 19

| Item | Reason | When |
|------|--------|------|
| Mid-run team mutation (add/remove agents) | LOC-expensive, topology implications | Wave 20+ |
| Full A2A server (task lifecycle, message exchange) | Agent Card only is the right half-step | Wave 20+ |
| A2A client (consuming external agents) | No concrete use case yet | Post-alpha |
| Queen auto-redirect without operator visibility | v1 must surface all redirects in chat | Wave 20+ |
| Multi-redirect per colony | Default cap is 1; relax later when patterns are understood | Wave 20 |
| Experimentation engine (A/B testing) | Needs more operator trust with config proposals | Post-alpha |
| Self-evolution / autonomous skill improvement | System needs more data from config changes first | Post-alpha |
| MCP Streamable HTTP migration | Important but independent of this wave's theme | Wave 20 |
