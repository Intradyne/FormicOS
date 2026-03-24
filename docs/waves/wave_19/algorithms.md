# Wave 19 Algorithms — Implementation Reference

**Wave:** 19 — "The Queen Steers"
**Purpose:** Technical implementation guide for all three tracks.

---

## §1. REDIRECT Mechanics (Track A)

### Data Model

The colony projection gains two fields alongside the existing `task`:

```python
# In projections.py ColonyProjection:
task: str                          # immutable, set at spawn
active_goal: str                   # mutable, initialized to task
redirect_history: list[dict] = []  # append-only audit log
```

On `ColonySpawned`: `active_goal = task`, `redirect_history = []`.

On `ColonyRedirected`: 
```python
colony.active_goal = event.new_goal
colony.redirect_history.append({
    "redirect_index": event.redirect_index,
    "new_goal": event.new_goal,
    "reason": event.reason,
    "trigger": event.trigger,
    "round": event.round_at_redirect,
    "timestamp": event.timestamp.isoformat(),
})
```

### Context Assembly Change

In `engine/context.py` `assemble_context()`, the goal tier currently reads the colony's `task`. Change to:

```python
# Before:
goal_text = colony_state.get("task", "")

# After:
goal_text = colony_state.get("active_goal") or colony_state.get("task", "")
```

This is the only engine-layer change. The active_goal flows through the existing context assembly pipeline without modification.

### Redirect Cap Enforcement

In `queen_runtime.py`, the redirect handler checks:

```python
async def _handle_redirect_colony(self, inputs, workspace_id, thread_id):
    colony_id = inputs.get("colony_id", "")
    colony = self._find_colony(colony_id)
    
    if colony is None:
        return ("Colony not found.", None)
    if colony.status != "running":
        return (f"Colony {colony_id} is {colony.status}, not running. Cannot redirect.", None)
    
    max_redirects = self._runtime.settings.governance.max_redirects_per_colony  # default 1
    if len(colony.redirect_history) >= max_redirects:
        return (
            f"Colony {colony_id} has already been redirected {len(colony.redirect_history)} time(s). "
            f"Maximum redirects per colony: {max_redirects}.",
            None,
        )
    
    # Emit event
    await self._runtime.emit_and_broadcast(ColonyRedirected(
        seq=0, timestamp=_now(),
        address=f"{workspace_id}/{thread_id}/{colony_id}",
        colony_id=colony_id,
        redirect_index=len(colony.redirect_history),
        original_goal=colony.task,
        new_goal=inputs["new_goal"],
        reason=inputs["reason"],
        trigger="queen_inspection",
        round_at_redirect=colony.round_number,
    ))
    
    return (
        f"Colony {colony_id} redirected at round {colony.round_number}.\n"
        f"New goal: {inputs['new_goal']}\n"
        f"Reason: {inputs['reason']}",
        {"tool": "redirect_colony", "colony_id": colony_id, "redirect_index": len(colony.redirect_history)},
    )
```

### Convergence/Stall Reset

In `colony_manager.py`, when processing `ColonyRedirected`:

```python
def _on_colony_redirected(self, event: ColonyRedirected) -> None:
    colony = self._colonies.get(event.colony_id)
    if colony is None:
        return
    
    # Reset stall detection window — new goal means old similarity comparisons are invalid
    colony.stall_window.clear()
    
    # Reset convergence progress — colony is starting fresh on a new goal
    colony.convergence = 0.0
    
    # Do NOT reset pheromone weights — topology is team chemistry, not task-specific
    
    # Mark redirect boundary for skill extraction
    colony.redirect_boundaries.append(event.round_at_redirect)
    
    log.info(
        "colony.redirected",
        colony_id=event.colony_id,
        redirect_index=event.redirect_index,
        round=event.round_at_redirect,
        new_goal=event.new_goal[:100],
    )
```

### Governance Alert → Queen Notification

The governance check in `colony_manager.py` already detects stalls and emits warnings. Add a direct Queen notification alongside the existing warning:

```python
# In colony_manager._check_governance() after detecting stall:
if stall_detected and self._queen_agent is not None:
    asyncio.create_task(
        self._queen_agent.on_governance_alert(
            colony_id=colony.id,
            workspace_id=workspace_id,
            thread_id=thread_id,
            alert_type="stall_detected",
        )
    )
```

In `queen_runtime.py`:

```python
async def on_governance_alert(
    self,
    colony_id: str,
    workspace_id: str,
    thread_id: str,
    alert_type: str,
) -> None:
    """React to a governance alert for a Queen-spawned colony.
    
    Preconditions (all must be true):
    1. Colony was spawned by Queen in this thread
    2. Thread has recent operator activity (30 min)
    3. Colony has not already been redirected (redirect cap)
    
    If preconditions pass, Queen inspects the colony and decides:
    - REDIRECT with a reframed goal, OR
    - Note in chat ("monitoring, colony may be struggling")
    
    At most one reaction per governance alert per colony.
    """
    # Check preconditions
    thread = self._runtime.projections.get_thread(workspace_id, thread_id)
    if thread is None:
        return
    
    # Recency check
    recent_cutoff = _now() - timedelta(minutes=30)
    has_recent = any(
        m.role == "operator" and m.timestamp >= recent_cutoff.isoformat()
        for m in thread.queen_messages
    )
    if not has_recent:
        return
    
    # Redirect cap check
    colony = self._find_colony(colony_id)
    if colony is None or colony.status != "running":
        return
    max_redirects = self._runtime.settings.governance.max_redirects_per_colony
    if len(getattr(colony, "redirect_history", [])) >= max_redirects:
        return
    
    # Queen decides: build a prompt with colony state and ask for a redirect decision
    colony_summary = self._format_colony_for_inspection(colony)
    
    decision_prompt = (
        f"A colony is showing signs of stalling (alert: {alert_type}).\n\n"
        f"{colony_summary}\n\n"
        f"Should I redirect this colony with a clearer goal? "
        f"If yes, call redirect_colony with a reframed goal. "
        f"If the colony seems to be making progress despite the alert, "
        f"just note that you're monitoring it."
    )
    
    # Use the existing respond() path with a synthetic operator message
    # This keeps the decision visible in the thread
    await self._emit_queen_message(
        workspace_id, thread_id,
        f"⚠ Governance alert on colony **{getattr(colony, 'display_name', colony_id)}**: {alert_type}. Inspecting...",
    )
    
    # Let the Queen's normal LLM loop decide (she has redirect_colony in her tools)
    # The response will be visible in the thread
```

The key design choice: the Queen's reaction goes through her normal LLM loop with the full tool set. She might redirect, or she might just note "the colony seems to be working through it." The operator sees everything in the thread.

### Skill Extraction Boundary Tagging

In `colony_manager.py`, when running skill extraction at colony completion:

```python
redirect_boundaries = getattr(colony, "redirect_boundaries", [])

if redirect_boundaries:
    # Extract skills separately for each phase
    for i, boundary in enumerate(redirect_boundaries):
        # Pre-redirect skills
        pre_rounds = [r for r in colony.round_records if r.round_number < boundary]
        if pre_rounds:
            pre_skills = await self._extract_skills(
                colony, pre_rounds,
                metadata_extra={
                    "pre_redirect": True,
                    "goal_at_extraction": colony.task if i == 0 else colony.redirect_history[i-1]["new_goal"],
                    "redirect_boundary": boundary,
                },
            )
    
    # Post-redirect skills (from last boundary onward)
    post_rounds = [r for r in colony.round_records if r.round_number >= redirect_boundaries[-1]]
    if post_rounds:
        post_skills = await self._extract_skills(
            colony, post_rounds,
            metadata_extra={
                "pre_redirect": False,
                "goal_at_extraction": colony.active_goal,
                "redirect_boundary": redirect_boundaries[-1],
            },
        )
else:
    # No redirects — normal extraction
    await self._extract_skills(colony, colony.round_records)
```

---

## §2. Colony Chaining (Track B)

### InputSource Model

```python
# In core/types.py:
class InputSource(BaseModel):
    """Source of seed context for a chained colony."""
    model_config = ConfigDict(frozen=True)
    
    type: Literal["colony"]     # future: "file", "url", "skill_set"
    colony_id: str
    summary: str = ""           # resolved at spawn time
```

### ColonySpawned Extension

`ColonySpawned` gains an optional field:

```python
class ColonySpawned(BaseModel):
    # ... existing fields ...
    input_sources: list[InputSource] = Field(default_factory=list)
```

This is a backward-compatible change — existing events without `input_sources` deserialize to `[]`.

### Resolution at Spawn Time

In `runtime.py` `spawn_colony()`, before emitting `ColonySpawned`:

```python
resolved_sources: list[InputSource] = []
for src in input_sources:
    if src.type == "colony":
        source_colony = self._find_colony_in_projections(src.colony_id)
        if source_colony is None:
            raise ValueError(f"Source colony '{src.colony_id}' not found.")
        if source_colony.status != "completed":
            raise ValueError(
                f"Source colony '{src.colony_id}' is {source_colony.status}. "
                f"Chain only from completed colonies."
            )
        # Prefer Archivist summary if available, else truncated final round
        summary = self._get_colony_compressed_output(source_colony, max_tokens=2000)
        resolved_sources.append(InputSource(
            type="colony",
            colony_id=src.colony_id,
            summary=summary,
        ))
```

The summary is resolved once at spawn time and stored on the event. No lazy references — the event is self-contained and replay-safe.

### Context Injection

In `engine/context.py`, add a new tier for input sources, between `goal` and `routed_outputs`:

```python
# After goal assembly:
if colony_state.get("input_sources"):
    for src in colony_state["input_sources"]:
        if src.get("summary"):
            messages.append({
                "role": "user",
                "content": f"[Context from prior colony {src['colony_id']}]:\n{src['summary']}",
            })
```

This naturally shares the `routed_outputs` budget in the tier system. Input sources are treated as high-priority routed context.

### Queen Tool Extension

The existing `spawn_colony` tool gains `input_from`:

```python
# Add to spawn_colony parameters:
"input_from": {
    "type": "string",
    "description": "Colony ID to chain from. The completed colony's output becomes seed context.",
},
```

Handler wraps it:
```python
input_from = inputs.get("input_from")
input_sources = []
if input_from:
    input_sources = [InputSource(type="colony", colony_id=input_from)]
```

---

## §3. Config Approval Completion (Track B)

### Pending Proposal Record

```python
@dataclass
class PendingConfigProposal:
    proposal_id: str          # sha256(param_path + proposed_value)[:8]
    thread_id: str
    param_path: str
    proposed_value: str
    current_value: str
    reason: str
    proposed_at: datetime
    ttl_minutes: int = 30
    
    @property
    def is_expired(self) -> bool:
        return _now() > self.proposed_at + timedelta(minutes=self.ttl_minutes)
```

Storage: `dict[str, PendingConfigProposal]` keyed by `thread_id` on `QueenAgent`. One pending proposal per thread. New proposal in a thread replaces the old one.

### suggest_config_change Update

When both gates pass, before returning the diff text:

```python
import hashlib

proposal_id = hashlib.sha256(f"{param_path}:{proposed_value}".encode()).hexdigest()[:8]
self._pending_proposals[thread_id] = PendingConfigProposal(
    proposal_id=proposal_id,
    thread_id=thread_id,
    param_path=param_path,
    proposed_value=proposed_value,
    current_value=str(current_value),
    reason=reason,
    proposed_at=_now(),
)

return (
    f"**Config change proposal** (#{proposal_id}):\n"
    f"  Parameter: `{param_path}`\n"
    f"  Current value: {current_value}\n"
    f"  Proposed value: {proposed_value}\n"
    f"  Reason: {reason}\n\n"
    f"Say 'approve' to apply this change.",
    {"tool": "suggest_config_change", "proposal_id": proposal_id, "status": "proposed"},
)
```

### approve_config_change Tool

```python
{
    "name": "approve_config_change",
    "description": "Apply a previously proposed config change. Only works if a proposal is pending in this thread.",
    "parameters": {
        "type": "object",
        "properties": {},
        "required": [],
    },
}
```

Handler:

```python
async def _handle_approve_config_change(self, inputs, workspace_id, thread_id):
    proposal = self._pending_proposals.get(thread_id)
    
    if proposal is None:
        return ("No pending config proposal in this thread.", None)
    
    if proposal.is_expired:
        del self._pending_proposals[thread_id]
        return (
            f"Proposal #{proposal.proposal_id} expired "
            f"({proposal.ttl_minutes} minute TTL). Please propose again.",
            None,
        )
    
    # Gate 1: re-validate structural safety
    from formicos.surface.config_validator import validate_config_update
    payload = {proposal.param_path: proposal.proposed_value}
    result = validate_config_update(payload)
    if not result.valid:
        del self._pending_proposals[thread_id]
        return (f"Proposal #{proposal.proposal_id} failed re-validation: {result.errors[0]}", None)
    
    # Gate 2: re-validate Queen scope
    if not self._is_experimentable(proposal.param_path):
        del self._pending_proposals[thread_id]
        return (f"Proposal #{proposal.proposal_id} is no longer in experimentable scope.", None)
    
    # Apply via existing config mutation path
    try:
        await self._runtime.apply_config_change(
            proposal.param_path,
            proposal.proposed_value,
            workspace_id,
        )
    except Exception as exc:
        del self._pending_proposals[thread_id]
        return (f"Failed to apply: {exc}", None)
    
    del self._pending_proposals[thread_id]
    
    return (
        f"✓ Applied proposal #{proposal.proposal_id}:\n"
        f"  `{proposal.param_path}`: {proposal.current_value} → {proposal.proposed_value}",
        {"tool": "approve_config_change", "proposal_id": proposal.proposal_id, "applied": True},
    )
```

The `apply_config_change` method on Runtime needs to be implemented. It should:
1. Parse the dot-path to find the target (caste recipe field vs. governance config vs. routing config)
2. Apply in-memory
3. Persist to YAML (reuse existing `save_castes()` / config persistence)
4. Emit `WorkspaceConfigChanged`

---

## §4. Tier Escalation (Track C)

### Routing Override

Colony projection gains:

```python
routing_override: dict | None = None
# When set: {"tier": "heavy", "reason": "...", "set_at_round": 5}
```

### Compute Router Check

In `engine/runner.py`, the routing decision point (existing caste×phase table lookup):

```python
# Before caste×phase lookup:
override = colony_state.get("routing_override")
if override:
    tier = override["tier"]
    model = self._tier_to_model(tier)  # standard→local, heavy→Sonnet, max→Opus
    log.info("compute_router.override", colony_id=colony_id, tier=tier, model=model)
    return model

# Existing caste×phase lookup follows...
```

The `_tier_to_model` mapping reads from config:

```python
def _tier_to_model(self, tier: str) -> str:
    tier_map = {
        "standard": self._settings.models.defaults.coder,  # local default
        "heavy": "anthropic/claude-sonnet-4.6",
        "max": "anthropic/claude-opus-4.6",
    }
    return tier_map.get(tier, tier_map["standard"])
```

### Telemetry Capture

The existing telemetry bus captures routing decisions. Escalation adds a reason code:

```python
bus.emit_nowait("routing_decision", {
    "colony_id": colony_id,
    "agent_id": agent_id,
    "model": model,
    "reason": f"tier_escalation:{tier}",
    "original_route": original_model,  # what the caste×phase table would have chosen
})
```

This provides the audit trail without a new event type.

---

## §5. Agent Card (Track C, Stretch)

### Endpoint

In `app.py`, add a route:

```python
from starlette.responses import JSONResponse

async def agent_card(request):
    """A2A Agent Card — discoverable metadata at /.well-known/agent.json."""
    from formicos.surface.template_manager import load_templates
    
    templates = load_templates()
    skills = [
        {
            "id": t.template_id,
            "name": t.name,
            "description": t.description,
            "tags": t.tags,
            "examples": [f"Run a {t.name.lower()} colony"],
        }
        for t in templates
    ]
    
    card = {
        "name": "FormicOS",
        "description": "Stigmergic multi-agent colony framework. Accepts tasks, spawns agent colonies, returns results.",
        "url": str(request.base_url).rstrip("/"),
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

# In create_app():
app.add_route("/.well-known/agent.json", agent_card, methods=["GET"])
```

No dependencies. No A2A SDK. Just a JSON endpoint that makes FormicOS discoverable.

---

## §6. Governance Config Addition

Add to `formicos.yaml` governance section:

```yaml
governance:
  # ... existing fields ...
  max_redirects_per_colony: 1   # Queen can redirect at most N times per colony
```

And to `core/settings.py` `GovernanceSettings`:

```python
max_redirects_per_colony: int = 1
```

---

## §7. Files Changed Summary

### Track A (Coder 1)
| File | Action |
|------|--------|
| `src/formicos/core/events.py` | Add `ColonyRedirected` event. Update union 36 → 37. |
| `docs/contracts/events.py` | Mirror `ColonyRedirected`. |
| `frontend/src/types.ts` | Mirror `ColonyRedirected` + `redirect_history` + `active_goal` on Colony type. |
| `src/formicos/surface/projections.py` | Add `active_goal`, `redirect_history`, `redirect_boundaries` to ColonyProjection. Add `_on_colony_redirected` handler. |
| `src/formicos/engine/context.py` | Read `active_goal` instead of `task` for goal tier. |
| `src/formicos/surface/queen_runtime.py` | Add `redirect_colony` tool + handler. Add `on_governance_alert()`. |
| `src/formicos/surface/colony_manager.py` | Handle redirect (reset stall window, mark boundary). Call `on_governance_alert` on stall detection. Tag skills at redirect boundaries. |
| `config/formicos.yaml` | Add `max_redirects_per_colony: 1` to governance. |
| `src/formicos/core/settings.py` | Add `max_redirects_per_colony` to GovernanceSettings. |

### Track B (Coder 2)
| File | Action |
|------|--------|
| `src/formicos/core/types.py` | Add `InputSource` model. |
| `src/formicos/core/events.py` | Add `input_sources` field to `ColonySpawned`. **(Coordinate merge with Coder 1)** |
| `src/formicos/surface/runtime.py` | Resolve input sources at spawn time. Add `apply_config_change()` method. |
| `src/formicos/engine/context.py` | Inject resolved input source summaries in seed context. **(Coordinate merge with Coder 1)** |
| `src/formicos/surface/queen_runtime.py` | Add `input_from` to spawn_colony tool. Add `PendingConfigProposal`, pending storage, `approve_config_change` tool. Update `suggest_config_change` to store pending. **(Read after Coder 1)** |
| `frontend/src/types.ts` | Mirror `InputSource`. **(Coordinate with Coder 1)** |

### Track C (Coder 3)
| File | Action |
|------|--------|
| `src/formicos/surface/queen_runtime.py` | Add `escalate_colony` tool. **(Read after Coders 1+2)** |
| `src/formicos/surface/projections.py` | Add `routing_override` to ColonyProjection. **(Read after Coder 1)** |
| `src/formicos/engine/runner.py` | Check routing_override before caste×phase table. Add `_tier_to_model()`. |
| `src/formicos/surface/view_state.py` | Include `active_goal`, `redirect_history`, `routing_override` in colony snapshot. |
| `frontend/src/types.ts` | Add `routing_override` to Colony type. **(Coordinate with Coders 1+2)** |
| `frontend/src/components/` | Render redirect history panel, escalation badge, config audit. |
| `src/formicos/surface/app.py` | Add `/.well-known/agent.json` route. **(Stretch)** |
