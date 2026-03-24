# Targeted OpenClaw Research: Three Operational Depth-Dives

You already produced two strong research passes on the OpenClaw codebase.
This third pass asks for depth on three specific areas where FormicOS
could learn something genuinely new -- not architecture, not features,
but operational patterns born from scale.

Calibrate against FormicOS post-Wave 50 repo truth. Do not recommend
things FormicOS already has in stronger form. Focus on patterns that
are hard to discover without running a 325K-line codebase at scale.

---

## Area 1: Tool-Call Loop Context Management

FormicOS runs a tool-call loop in engine/runner.py (up to 25 iterations
for Coders). Each iteration appends assistant + tool-result messages.
No mid-loop compaction. At 80K context window with TOOL_OUTPUT_CAP=2000
chars, this is mostly okay but could pressure context on long loops.

We already found the head+tail truncation fix. Now go deeper:

Questions:
- How does OpenClaw manage context growth WITHIN a multi-turn tool loop?
- Does it compact/summarize/drop older tool results mid-loop?
- Does it have a "preemptive context guard" that triggers emergency
  compaction before hitting the provider's limit?
- The first research mentioned tool-result-context-guard.ts with a 90%
  overflow ratio trigger. How exactly does that work? What does it
  replace old tool results with? How does it decide which results to
  keep vs drop?
- What is their experience with the cost of mid-loop compaction vs
  the cost of context overflow errors?

FormicOS context: We identified mid-round observation masking as a
"Should" in the Wave 49 plan. OpenClaw's battle-tested approach to
this exact problem would inform whether and how to implement it.

---

## Area 2: MCP Tool Integration Patterns at Scale

FormicOS uses FastMCP for its tool surface and is wiring MCP for
the Researcher's mediated Forager access (request_forage via
ServiceRouter.register_handler). OpenClaw has extensive MCP
integration as a major framework.

Questions:
- How does OpenClaw handle MCP tool discovery and registration?
- How does it manage the "too many tools confuses the model" problem?
  (Our research found this is a real issue. Does OpenClaw have a
  dynamic tool loading/unloading strategy?)
- How does it handle MCP server failures mid-conversation?
- Does it have patterns for MCP tool result caching or deduplication?
- How does it handle MCP tool timeouts without breaking the agent loop?
- Any patterns for MCP tool permission scoping (some tools available
  to some agents but not others)?

FormicOS context: We have per-caste tool policies in tool_dispatch.py
(CasteToolPolicy with allowed_categories and denied_tools). Comparing
with OpenClaw's approach at scale could validate or improve our design.

---

## Area 3: What Breaks at Scale (Failure Taxonomy)

FormicOS is a single-operator desktop tool. OpenClaw runs at massive
scale with thousands of concurrent users. The failure modes at scale
are different from the failure modes in development.

Questions:
- What are the top 5 failure modes OpenClaw has encountered in
  production that are NOT obvious from reading the code?
- How does context window exhaustion actually manifest in practice?
  (Gradual degradation? Sudden hallucination? Provider rejection?)
- What patterns do they use to detect when an agent is "stuck" vs
  "thinking hard"? (FormicOS has stall detection in its governance
  engine -- how does OpenClaw's approach compare?)
- How do they handle the "agent edits a file, tests fail, agent
  re-edits, tests fail again, infinite loop" pattern? Is there a
  max-retry or diminishing-returns detector?
- What's their experience with model-specific failure modes?
  (e.g., Claude vs GPT vs Gemini behaving differently on the same
  tool-call pattern)
- How do they handle partial failures in multi-step tool sequences?
  (Tool 1 succeeds, tool 2 fails -- does the agent retry tool 2,
  undo tool 1, or something else?)

FormicOS context: Our governance engine handles stall detection and
auto-escalation. Our research found Devin has 15% success on real
tasks and agents commonly enter infinite edit-test loops. OpenClaw's
operational experience with these failure modes at massive scale
would be the most valuable thing this research could produce.

---

## Output Format

For each area:
1. What OpenClaw actually does (with source file references)
2. What they learned the hard way (failure modes that drove the design)
3. What FormicOS should consider adopting (if anything)
4. What FormicOS already handles better (for confidence calibration)

Keep it concrete. Code references over generalizations. Failure
stories over feature descriptions. Operational wisdom over
architecture opinions.
