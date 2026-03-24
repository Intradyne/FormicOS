# Research Prompt: Multi-Agent Role Specialization, Tool Assignment, and Reviewer/Researcher Best Practices

## Context

FormicOS is a multi-agent colony framework with a caste system:
- Queen (coordinator), Coder (implementation), Reviewer (quality gate),
  Researcher (knowledge gathering), Forager (web knowledge acquisition service),
  Archivist (knowledge compression).

Current state: the Coder is well-equipped (workspace tools, code execution,
patch_file, git tools). The Reviewer and Researcher are under-tooled relative
to their stated roles. The Reviewer cannot read workspace files or run tests.
The Researcher cannot access the web or read project files.

We already know from our existing research base:
- MetaGPT found executable feedback outperforms LLM-only review
- ChatDev found removing role definitions caused the largest perf drop
- The Wharton study showed generic personas don't help; structured behavioral
  constraints do
- SWE-agent's ACI framework shows tool design matters more than agent identity
- The actor-critic pattern with structured APPROVED/NEEDS_CHANGES verdicts
  works well
- The "Swiss Cheese" critic model says prioritize orthogonal reviewers
- Aider's architect/editor split outperforms single-agent approaches

## What we need to learn (search for these specific gaps)

### Q1: Reviewer agent tool access in production coding systems

How do production multi-agent coding systems equip their reviewer/verifier
agents? Specifically:

- Does the reviewer in Cursor/Windsurf/Devin/Amazon Q have read access to
  the full workspace, or just the diff/output?
- Do any systems give the reviewer independent test execution capability?
- What's the empirical evidence for read-only reviewers vs reviewers who can
  also run tests?
- How does the "challenge-response" pattern from Vijayaraghavan et al. work
  in practice -- do critics need to see the full artifact or just a summary?

Search queries:
- "multi-agent code review tool access 2025 2026"
- "AI code reviewer workspace access empirical"
- "SWE-agent verifier tools ablation"
- "Devin reviewer agent architecture"
- "CodeR reviewer agent tools"

### Q2: Should a dedicated researcher agent exist separately from foraging?

In systems with both knowledge retrieval and web search:

- Do production systems have a separate "researcher" agent, or do they give
  research tools to all agents?
- What's the evidence for dedicated research roles vs tool-enriched general
  agents?
- How do systems like Manus, OpenHands, or AIDE handle the "gather
  information before coding" phase?
- Is there evidence that a dedicated research phase (before coding begins)
  outperforms interleaved research-during-coding?

Search queries:
- "multi-agent researcher role vs shared tools 2025 2026"
- "AIDE research agent architecture"
- "OpenHands information gathering phase coding"
- "Manus research before implementation agent"
- "dedicated research agent vs enriched coder 2026"

### Q3: Optimal tool assignment per role in multi-agent coding

What's the best practice for tool distribution across specialized agents?

- Should all agents have read access to the workspace, or should some be
  deliberately blind to encourage different perspectives?
- What tools should a reviewer have vs NOT have?
  (The "read-only reviewer" pattern vs "reviewer who can run tests")
- Is there evidence that restricting tools improves agent focus, or does it
  just create capability gaps?
- How do CAMEL, CrewAI, AutoGen handle tool assignment per role?

Search queries:
- "multi-agent tool assignment best practices 2025 2026"
- "agent tool restriction focus vs capability"
- "CrewAI agent tool configuration"
- "AutoGen agent tool access patterns"
- "code review agent read-only vs full access"

### Q4: Reviewer sycophancy mitigation in production

The biggest risk when giving a reviewer more tools: it uses them to confirm
the coder's work rather than critique it.

- What techniques prevent reviewer agents from rubber-stamping?
- How does the "adversarial" instruction pattern perform in practice?
- What structured output formats force genuine critique?
- Is temperature/model choice for reviewers different from coders?
- Does giving the reviewer independent test execution actually reduce
  sycophancy (because test results are objective)?

Search queries:
- "AI code reviewer sycophancy mitigation 2025 2026"
- "adversarial reviewer prompt engineering"
- "LLM reviewer rubber stamp prevention"
- "independent test execution reviewer agent"
- "structured code review output format agent"

### Q5: The Forager/Researcher overlap question

When a system has both a background knowledge acquisition service (like our
Forager) and an in-colony research agent:

- Do they duplicate effort or serve genuinely different needs?
- What's the right division of responsibility? (Background/proactive vs
  in-task/synchronous?)
- Should the researcher be able to trigger the forager, or should they be
  independent paths?
- Is there evidence from any system that merged these roles successfully?

Search queries:
- "background knowledge acquisition vs synchronous research agent"
- "RAG agent vs web search agent architecture 2025 2026"
- "proactive knowledge foraging multi-agent"
- "knowledge acquisition service vs research agent overlap"

### Q6: Fast path / solo mode patterns

For systems that support both multi-agent and single-agent modes:

- How do they decide when to use which?
- Is the decision made by the orchestrator or by a classifier?
- What's the empirical overhead of multi-agent coordination on simple tasks?
- Does anyone measure the "break-even point" where multi-agent starts
  outperforming single-agent?

Search queries:
- "multi-agent vs single agent task routing 2025 2026"
- "agent orchestration overhead simple tasks"
- "when to use multi-agent vs single agent coding"
- "SWE-bench single agent vs multi-agent comparison"
- "fast path single agent mode multi-agent framework"

## Output format

For each question:
1. What the current evidence says (with sources and dates)
2. What's settled vs still debated
3. Concrete recommendation for FormicOS
4. What we should NOT do based on negative evidence

Prioritize 2025-2026 sources. Prefer empirical results over opinion.
Flag any finding that contradicts our existing research base.

## What NOT to research

- General multi-agent architecture (we have extensive coverage)
- Stigmergy theory (well-covered)
- Prompt engineering basics (well-covered)
- Benchmark methodology (separate concern)
- LLM selection / model routing (well-covered)
- Tool design patterns (well-covered via SWE-agent/Aider research)
