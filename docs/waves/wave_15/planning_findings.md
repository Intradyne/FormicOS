# Wave 15 Planning Findings

**Date:** 2026-03-14
**Purpose:** Document the gap analysis between Wave 14 delivery and real v3 operator experience, and the planning rationale for Wave 15.

---

## 1. The frontend gap is real but smaller than expected

Wave 14 delivered all the contract/mechanics work. The live Lit frontend absorbed it:

**Already working:**
- Colony Creator with 4-step flow, tier pills, suggest-team
- Per-colony chat with ChatSender types and event_kind color coding
- Service colony banner and serviceType detection
- Template browser
- CasteSlot / SubcasteTier types in frontend
- Queen chat wired into queen-overview
- Knowledge view (skills + KG)
- Topology graph
- Workspace config with per-caste model overrides

**Gap is polish, not architecture:**
- 6 nav tabs instead of 5 (Models and Castes not yet merged into Fleet)
- Sidebar uses hover instead of click-to-toggle
- Branding still says `2.0.0-alpha`
- No empty states -- first-time user sees blank panels
- Cost ticker doesn't use budget regime colors
- No inline code execution result cards
- No visible connection state indicator

This is a half-wave of frontend work, not a rewrite. The Lit framework is not the problem. The missing pieces are all additive.

---

## 2. First-run experience is the highest leverage gap

A new operator who runs `docker compose up` today and opens the app will see:

1. A dark shell with 6 tabs
2. An empty Queen overview with no guidance
3. No obvious path to "do something"
4. Templates exist in the backend but may not be visibly loaded
5. No welcome message or suggested first action

After Wave 15:

1. A v3-branded shell with 5 tabs
2. Queen overview with template suggestions and a "describe a task" prompt
3. Welcome message in Queen chat explaining the 3-step flow
4. Templates pre-loaded and visible in the browser
5. First colony spawnable within 60 seconds of opening the app

This is the single highest-leverage improvement.

---

## 3. Config defaults are the silent killer of first-run experience

Even with a polished UI, the first colony will fail silently if:

- A template uses stale `caste_names` format (spawn fails)
- A caste recipe is missing `max_iterations` (no safety cap)
- A caste recipe doesn't list `code_execute` in tools (coder can't run code)
- No template includes Archivist (KG stays empty, Knowledge view always blank)
- Budget default is $0.50 (colony runs out in 2 rounds)

Wave 15 audits every template and every caste recipe. This is not glamorous work, but it's the difference between "it works" and "it seems broken."

---

## 4. Contract stance: frozen

Wave 14 opened the contracts from 27 to 35 events and added 5 types. That's enough.

Wave 15 does not need new events. The 10-minute success path works entirely with existing mechanics:

- Colony spawning: `ColonySpawned` with CasteSlot
- Colony chat: `ColonyChatMessage`
- Code execution: `CodeExecuted`
- Service colonies: `ServiceQuerySent/Resolved`, `ColonyServiceActivated`
- KG: `KnowledgeEntityCreated/EdgeCreated/EntityMerged`

First-run bootstrapping uses `projections.last_seq == 0` as the signal. No `FirstRunCompleted` event needed -- that's a surface-layer concern.

The welcome message uses the existing `QueenMessage` event with `role="queen"`. No new event type.

---

## 5. The v3 prototype's role

The React prototype (`docs/prototype/formicos-v3.jsx`) served as a visual spec for Waves 12-14. After Wave 15, the live Lit frontend IS the product.

The prototype should get a header comment noting its historical role, but it should not be deleted -- it's still useful as a design reference for future UI work.

No React rewrite is planned or needed.

---

## 6. Stream shape rationale

**Why 3 parallel streams with no sequencing?**

Unlike Wave 14, where Stream A gated everything, Wave 15's three streams touch almost completely different files:

- Stream A: backend config files + `app.py` lifespan + docs
- Stream B: frontend components only
- Stream C: Docker/infrastructure + end-to-end testing

The only shared file is `docs/RUNBOOK.md` (A writes it, C appends findings). This is low-risk sequential overlap, not a merge conflict.

**Why not 2 streams?**

Smoke testing (Stream C) is qualitatively different from the other two streams. It requires real API keys, real Docker containers, real inference. Mixing it with frontend polish or config audit would slow both down. A dedicated smoke coder can work in parallel and fix issues as they're found.

---

## 7. Risk assessment

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Real API keys reveal new adapter bugs | Medium | Medium | Stream C smoke catches them early. Provider fallback ensures graceful degradation. |
| gVisor not available on host | Medium | Low | Sandbox smoke documents the gap. code_execute fails gracefully, colony still completes. |
| Template YAML format still has stale fields | High | High | Stream A audit is explicitly checking for this. |
| Frontend build produces stale dist/ | Low | Medium | Stream B runs `npm run build` as final step. RUNBOOK documents rebuild. |
| First colony takes > $5 budget | Low | Medium | Template audit sets sensible budget defaults. Budget regime injection warns agents. |

---

## 8. What Wave 16 looks like

Wave 15 makes the product usable. Wave 16 makes it smart:

- Experimentation engine (A/B test colony configurations)
- Skill synthesis (combine skills from multiple colonies)
- Research colony expansion (web egress, persistent research service)
- Dashboard composition (Queen builds custom views)
- Template recommendations from usage patterns

None of these belong in Wave 15. They all depend on having real usage data, which only exists after Wave 15 makes the product usable enough to generate it.
