# Wave 15 Plan: Dispatch Document

**Status:** Dispatch-ready
**Theme:** "Out of the Box"
**Streams:** A (first-run + defaults) / B (shell + UX polish) / C (smoke + validation)
**Contract stance:** Frozen. No changes to `core/events.py`, `core/types.py`, or `core/ports.py`.
**Estimated effort:** 8-10 calendar days with 3 coders in parallel

---

## Wave boundary

Wave 15 is the hardening and productization wave that follows Wave 14's contract/mechanics work.

Wave 15 owns:
- first-run operator experience (startup to first successful colony)
- default config/template/recipe audit and correction
- frontend shell polish to match v3 visual spec
- end-to-end smoke tests with real API keys
- operator documentation (README, RUNBOOK)
- branding update (2.0.0-alpha to v3)

Wave 15 does not:
- open any contracts (event union stays at 35, ports frozen)
- add new colony mechanics
- swap inference backends
- rewrite the frontend framework
- add multi-user, auth, or community features

---

## Success criteria

After Wave 15, this sequence works without surprises:

1. `git clone` + `cp .env.example .env` + add Anthropic/Gemini keys
2. `docker compose up -d` -- all containers healthy in ~2 minutes
3. Open `http://localhost:8080` -- see v3 shell, default workspace, Queen chat ready
4. Type a task in Colony Creator or Queen chat -- colony spawns with suggested team + tiers
5. Watch colony chat show round milestones, code execution results, governance warnings
6. Colony completes -- cost visible -- skills extracted -- "Save as Template" available
7. Spawn a second colony using saved template -- it retrieves skills from the first run

That is the 10-minute success path. Everything in Wave 15 exists to make it work.

---

## Pre-requisites

None gating. Wave 14 is complete (CI green, BDD green, Docker smoke green, all containers healthy, frontend bundle loads, WebSocket upgrade succeeds).

The Qdrant v1.16.2 upgrade should have landed as a Wave 14 pre-req. If it hasn't been applied yet, Stream C applies it as its first task.

---

## Frontend gap analysis (v3 prototype vs live shell)

The live Lit frontend already has most v3 mechanics. The gap is polish, not architecture.

### Already shipped (no work needed)

| Feature | Component |
|---|---|
| Colony Creator with tiers + suggest-team | `colony-creator.ts` -- 4-step flow, tier pills |
| Per-colony chat with sender styling | `colony-chat.ts` -- ChatSender types, event_kind colors |
| Service colony banner + indicators | `colony-detail.ts` -- service banner, serviceType check |
| Template browser | `template-browser.ts` |
| CasteSlot / SubcasteTier types | `types.ts` |
| Queen chat | `queen-chat.ts` wired into queen-overview |
| Knowledge view (skills + KG) | `knowledge-view.ts` |

### Needs polish (Wave 15 Stream B)

| Gap | Current state | Target |
|---|---|---|
| Nav tab count | 6 tabs (Models + Castes separate) | 5 tabs: merge into "Fleet" per v3 spec |
| Sidebar behavior | Hover-based (mouseenter/mouseleave) | Click-to-toggle (v3 spec, less janky) |
| Branding | `2.0.0-alpha` in topbar | `v3` or `3.0.0-alpha` |
| Empty states | Blank panels when no colonies exist | Queen overview shows template suggestions, "spawn first colony" prompt |
| Cost ticker colors | Shows cost number only | Color-coded by budget regime (green >= 70%, yellow 30-70%, orange 10-30%, red < 10%) |
| Code execution cards | No dedicated component | Inline cards in colony detail for CodeExecuted events |
| Loading/disconnected UI | Minimal | Visible reconnection state, connection indicator |
| First-run experience | Default workspace + thread created, otherwise blank | Guided prompt in Queen chat, pre-loaded templates visible |

### Not in Wave 15 (deferred)

| Feature | Reason |
|---|---|
| Full React rewrite | Lit shell works. Polish it, don't replace it. |
| Queen-composed dashboards | Needs proven component library. Wave 16+. |
| Drag-and-drop sidebar reordering | Nice-to-have, not blocking usability. |
| Mobile responsive layout | Desktop-first product. Later. |

---

## Stream A: First-Run and Defaults

**Owner:** 1 coder. Can start immediately.

Focus: make the product demonstrate itself on first launch.

### A.1 First-run bootstrapping enhancement

Current state: `surface/app.py` lifespan creates default workspace + thread on first run.

Add:
- Validate that default templates in `config/templates/` are readable on first run and log the count (template listing already reads directly from disk).
- Insert a welcome `QueenMessage` into the default thread: "Welcome to FormicOS. Try spawning a colony -- click + or type a task below. I'll suggest a team."

Files: `src/formicos/surface/app.py` (lifespan function only).

### A.2 Default template audit

Read every file in `config/templates/*.yaml`. Verify:

| Template | Must include | Must exercise |
|---|---|---|
| `full-stack` | Archivist (for KG visibility) | code_execute, memory tools |
| `minimal` | Coder only | Fast demo path (2-3 rounds) |
| `research-heavy` | Researcher + Archivist | web_search (if available), memory_search |
| `code-review` | Coder + Reviewer | code_execute, memory tools |
| `rapid-prototype` | Coder (heavy tier) | code_execute |
| `documentation` | Archivist | memory tools |
| `debugging` | Coder + Reviewer | code_execute |

Fix any template that:
- lacks governance block (max_rounds, budget_usd)
- uses stale `caste_names` format instead of `castes: list[CasteSlot]`
- has unreasonable defaults (budget too low to complete, max_rounds too high)

Ensure at least one template exercises Archivist so KG events actually emit during demo use.

Files: `config/templates/*.yaml`

### A.3 Default caste recipes audit

Read `config/caste_recipes.yaml`. Verify:

- Every caste has `max_iterations` and `max_execution_time_s` (Wave 14 safety layer)
- Every caste has a sensible `tools` list that matches Wave 14's `CasteToolPolicy` defaults
- Coder has `code_execute` in tools list
- Researcher has `web_search` in tools list (if egress gateway shipped)
- Archivist has `memory_write` + `memory_search`
- Manager has `delegate` if service colonies are wired
- Temperature and max_tokens are reasonable per caste

Fix any recipe that would cause a new operator's first colony to fail silently.

Files: `config/caste_recipes.yaml`

### A.4 .env.example and README

Create or update `.env.example`:
```
ANTHROPIC_API_KEY=sk-ant-...
GEMINI_API_KEY=AI...
# Optional: override LLM model file
# LLM_MODEL_FILE=Qwen3-30B-A3B-Instruct-2507-Q4_K_M.gguf
```

Update `README.md` quickstart section with the 7-step success path from the success criteria above. Remove any stale Wave 10-era instructions.

Files: `.env.example`, `README.md`

### A.5 RUNBOOK

Create `docs/RUNBOOK.md` -- the operator's "I just pulled this repo" document:

- Hardware requirements (RTX 5090 32GB, or any NVIDIA GPU with 24GB+ for smaller models)
- Model download commands (Qwen3-30B-A3B GGUF, Qwen3-Embedding-0.6B GGUF)
- Docker compose startup
- API key setup
- First colony walkthrough
- Troubleshooting: container not healthy, WebSocket won't connect, Qdrant BM25 degraded, no embedding results
- Where to look: logs, data directory, skill bank, KG

Files: `docs/RUNBOOK.md` (new)

### Stream A deliverables

- [ ] First-run welcome message in Queen chat
- [ ] Templates visible and validated on first run
- [ ] All 7 templates audited and corrected
- [ ] Caste recipes audited and corrected
- [ ] `.env.example` present and accurate
- [ ] `README.md` quickstart updated
- [ ] `docs/RUNBOOK.md` written

**Estimated effort:** 2-3 days.

---

## Stream B: Shell and UX Polish

**Owner:** 1 coder. Can start immediately.

Focus: close the gap between the live Lit shell and the v3 visual spec.

### B.1 Nav consolidation: Models + Castes -> Fleet

Merge the existing `model-registry.ts` and `castes-view.ts` into a single "Fleet" tab. Implementation:

- Create `fleet-view.ts` that renders both as sub-sections (models above, castes below, or tabbed within)
- Update `formicos-app.ts` NAV array: remove `models` and `castes` entries, add `fleet`
- Update the ViewId type and renderView switch

The v3 prototype uses 5 tabs: Queen, Knowledge, Templates, Fleet, Settings. Match that.

Files: `frontend/src/components/fleet-view.ts` (new), `frontend/src/components/formicos-app.ts`

### B.2 Sidebar: click-to-toggle

Replace the current hover behavior (mouseenter/mouseleave) with click-to-toggle:

- Add a toggle button (chevron or hamburger) at the top of the sidebar
- Remove mouseenter/mouseleave handlers
- Sidebar starts open on first load
- Click toggles between open (195px) and closed (46px)
- Closed state shows mini colony icons (already implemented)

Files: `frontend/src/components/formicos-app.ts`

### B.3 Branding update

- Change `2.0.0-alpha` to `v3` in the topbar logo area
- Update any other version strings in the frontend

Files: `frontend/src/components/formicos-app.ts`

### B.4 Empty states

When no colonies exist (first run or clean state):

**Queen Overview:** Show a card grid of 2-3 suggested templates with "Spawn" buttons, plus a text prompt: "Describe a task and I'll suggest a team." Currently shows blank panels.

**Thread View:** Show "No colonies yet. Spawn one from the Queen tab or click + below."

**Knowledge View:** Show "Knowledge grows as colonies run. Skills and graph entities appear here after your first completed colony."

Files: `frontend/src/components/queen-overview.ts`, `frontend/src/components/thread-view.ts`, `frontend/src/components/knowledge-view.ts`

### B.5 Cost ticker regime colors

In `colony-detail.ts`, color the cost display by budget regime:

```
>= 70% remaining: green  (var(--v-success))
30-70% remaining: yellow (var(--v-warn))
10-30% remaining: orange (var(--v-accent))
< 10% remaining:  red    (var(--v-danger))
```

This is the visual complement to the budget injection from ADR-022 -- the operator sees the same signal the agents see.

Files: `frontend/src/components/colony-detail.ts`

### B.6 Code execution cards

Add inline rendering in colony detail for `CodeExecuted` events:

- Green card for exit_code 0 with stdout preview
- Red card for non-zero exit with stderr preview
- Yellow card for AST-blocked with violation message
- Expandable to show full output

This data is already in the colony snapshot from Wave 14 events. The rendering just needs to exist.

Files: `frontend/src/components/colony-detail.ts` (or new `code-result-card.ts`)

### B.7 Connection state indicator

Add a small dot/badge in the topbar showing WebSocket connection state:

- Green dot: connected
- Yellow dot + "Reconnecting...": disconnected, retrying
- Red dot + "Disconnected": failed after retries

The store already tracks `connection` state. Just surface it.

Files: `frontend/src/components/formicos-app.ts`

### B.8 Bug fixes from first operator testing

These were found during real usage and block the success path:

1. **Add thread button:** Currently non-functional. Wire it to create a new thread via `runtime.create_thread()`. Style the button orange (accent color).
2. **Base font size:** Increase body font from ~12px to 14px. Mono font to 12px. The app feels "small" across the board.
3. **Model registry misclassification:** Gemini models appear under "LOCAL MODELS", llama-cpp appears under "CLOUD ENDPOINTS". Fix the provider-prefix filter in `model-registry.ts` so models are classified by their actual provider prefix, not by endpoint reachability.
4. **Anthropic shows "connected" without API key:** The status check defaults to connected when it can't verify. Should show `no_key` status (value already exists in `ModelRecord`). Add a visual "Add Key" link when status is `no_key`.
5. **Colony rename:** Add a rename button/action in colony detail that emits a WS command. The `ColonyNamed` event already exists -- wire it for operator-initiated renames, not just Queen-assigned names.
6. **Nav tab overflow:** If 5 tabs still overflow on narrow screens after the Fleet merge, add `flex-wrap: wrap` to `.nav-tabs` or reduce tab padding.

Files: `frontend/src/components/model-registry.ts`, `frontend/src/components/formicos-app.ts`, `frontend/src/components/colony-detail.ts`, `frontend/src/styles/shared.ts`

### B.9 Frontend build verification

After all changes:
```bash
cd frontend && npm run build
```

Verify `frontend/dist/` is updated. The served app must match the source. If the build pipeline has any staleness risk, document it in the RUNBOOK.

### Stream B deliverables

- [ ] 5-tab nav (Fleet replaces Models + Castes)
- [ ] Click-to-toggle sidebar
- [ ] `v3` branding
- [ ] Empty states for Queen, Thread, Knowledge views
- [ ] Budget regime colors on cost ticker
- [ ] Code execution result cards
- [ ] Connection state indicator
- [ ] Add thread button working + orange styled
- [ ] Base font size increased
- [ ] Model registry classifies providers correctly
- [ ] Anthropic no_key state visible with "Add Key" link
- [ ] Colony rename via existing ColonyNamed event
- [ ] Nav tabs don't overflow
- [ ] Frontend build passes

**Estimated effort:** 4-5 days.

---

## Stream C: Smoke and Validation

**Owner:** 1 coder. Can start immediately, but most value comes after A and B stabilize.

Focus: prove the 10-minute success path works end-to-end with real infrastructure.

### C.1 Qdrant upgrade verification

If the v1.16.2 upgrade hasn't been applied yet, apply it now:
```yaml
# docker-compose.yml
qdrant:
  image: qdrant/qdrant:v1.16.2  # was v1.14.0
```

Then verify:
- [ ] Qdrant health endpoint responds
- [ ] Existing `skill_bank_v2` collection intact
- [ ] Re-upsert test points with sparse vectors
- [ ] Hybrid search returns results from both dense AND sparse branches
- [ ] No client/server version warning in logs

### C.2 End-to-end colony smoke (real API keys)

Spawn a colony with the `full-stack` template. Requires real Anthropic and/or Gemini API keys.

Verify:
- [ ] Colony spawns with CasteSlot payload (not caste_names)
- [ ] Tier routing works: light -> local, standard -> smart routing, heavy -> cloud
- [ ] Colony chat shows round milestones, phase transitions
- [ ] At least one agent uses memory_search / memory_write
- [ ] Colony completes with cost > $0 and skills_extracted > 0
- [ ] Archivist generates KG entities (check knowledge view)
- [ ] Budget regime text appears in agent prompts (check structured logs)
- [ ] Iteration caps are respected (no runaway tool loops)

### C.3 Sandbox smoke

If gVisor sandbox shipped in Wave 14:
- [ ] Agent calls code_execute with valid Python
- [ ] AST pre-parser blocks `import subprocess`
- [ ] Output sanitizer strips ANSI escapes
- [ ] CodeExecuted event emitted
- [ ] ColonyChatMessage one-liner appears in colony chat
- [ ] Container pool recycles

If sandbox is not yet deployed (gVisor not available on host):
- Document the gap in RUNBOOK
- Ensure code_execute fails gracefully with a clear error, not a crash

### C.4 Service colony smoke

- [ ] Complete a colony
- [ ] Activate it as service via `activate_service` MCP tool or UI button
- [ ] Colony status becomes "service" in fleet view
- [ ] Spawn a second colony
- [ ] Second colony queries the service colony via `query_service`
- [ ] Response appears in both colonies' chat feeds

### C.5 Provider fallback smoke

- [ ] Start with valid Anthropic key, invalid Gemini key
- [ ] Verify Gemini adapter enters cooldown after failures
- [ ] Verify fallback to Anthropic / local works
- [ ] Verify structured logs show `fallback_triggered=true`

### C.6 Fix discovered issues

Stream C's primary output is a list of issues found during smoke testing, plus fixes for any that are blocking the 10-minute success path. Non-blocking issues get filed as Wave 16 items.

### C.7 Update PROGRESS.md

Update `docs/waves/PROGRESS.md` with Wave 15 completion status.

### Stream C deliverables

- [ ] Qdrant BM25 verified with real data
- [ ] End-to-end colony smoke passed
- [ ] Sandbox smoke passed (or gap documented)
- [ ] Service colony smoke passed
- [ ] Provider fallback verified
- [ ] All blocking issues fixed
- [ ] PROGRESS.md updated

**Estimated effort:** 2-3 days (plus fix time for discovered issues).

---

## Shared-workspace merge discipline

Overlap is minimal in Wave 15. Each stream owns distinct files.

| File | Stream | Notes |
|---|---|---|
| `src/formicos/surface/app.py` | A only | First-run lifespan changes |
| `config/templates/*.yaml` | A only | Template audit |
| `config/caste_recipes.yaml` | A only | Recipe audit |
| `README.md` | A only | Quickstart |
| `docs/RUNBOOK.md` | A + C | A writes initial, C adds smoke findings |
| `frontend/src/components/formicos-app.ts` | B only | Nav, sidebar, branding, connection indicator |
| `frontend/src/components/colony-detail.ts` | B only | Cost colors, code cards |
| `frontend/src/components/queen-overview.ts` | B only | Empty states |
| `frontend/src/components/fleet-view.ts` | B only | New component |
| `docker-compose.yml` | C only | Qdrant version (if not already done) |

**Only overlap:** `docs/RUNBOOK.md` -- Stream A writes the initial version, Stream C appends troubleshooting findings. Sequential, not concurrent.

---

## Frozen files

| File | Reason |
|---|---|
| `src/formicos/core/events.py` | Event union stays at 35 |
| `src/formicos/core/types.py` | No new types |
| `src/formicos/core/ports.py` | No port changes |
| `docs/contracts/events.py` | Mirror frozen |
| `docs/contracts/ports.py` | Mirror frozen |
| `docs/contracts/types.ts` | Mirror frozen |
| `src/formicos/engine/runner.py` | Wave 14 runner is stable |
| `src/formicos/engine/context.py` | Budget injection is stable |
| `src/formicos/surface/runtime.py` | LLMRouter and spawn flow are stable |
| `src/formicos/adapters/vector_qdrant.py` | Hybrid search code is stable |

---

## What's NOT in Wave 15

| Feature | Why deferred |
|---|---|
| New events or types | Contracts are frozen. 35 events is enough. |
| Experimentation engine | Needs baseline from real production runs. Wave 16. |
| Skill synthesis / meta-skills | Needs 200+ skills. Wave 16+. |
| Research colony expansion | Needs web egress proven. Wave 16. |
| SGLang swap | Decision was made in Wave 14. Not revisited. |
| Full React rewrite | Lit shell works. Polish, don't replace. |
| Community template sharing | < 20 templates. Premature. |
| Mobile responsive | Desktop-first product. |
| Multi-user / auth | Single-operator product for now. |
| Queen-composed dashboards | Needs proven component library. Wave 16+. |

---

## Exit gate

- [ ] 10-minute success path verified end-to-end with real API keys
- [ ] All 7 templates load, spawn colonies with correct CasteSlot payloads
- [ ] Caste recipes have iteration caps, tool lists, and budget defaults
- [ ] Frontend builds clean, served bundle matches source
- [ ] Shell shows 5-tab nav, click sidebar, v3 branding, empty states
- [ ] Colony chat shows round milestones, code results, governance warnings
- [ ] Cost ticker colored by budget regime
- [ ] Service colony activates and responds to queries
- [ ] Qdrant BM25 hybrid search verified
- [ ] Provider fallback works when one cloud provider is unavailable
- [ ] README quickstart is accurate
- [ ] RUNBOOK exists and covers first-run through troubleshooting
- [ ] PROGRESS.md updated
