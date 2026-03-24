# Demo: Build an Email Validator — End-to-End Knowledge Lifecycle

This walkthrough shows the full FormicOS knowledge lifecycle from a single
operator request through knowledge extraction, retrieval, and proactive
intelligence.

---

## Prerequisites

- FormicOS running (`docker compose up` or `python -m formicos`)
- A workspace created (e.g., `ws-demo`)
- At least one thread active

## Step 1: Operator request

In the Queen chat, type:

> Build me an email validator library with comprehensive tests.

The Queen will:
1. Call `list_templates` to check for matching templates.
2. Decompose into colonies: a coder colony for implementation, optionally
   chained with a test colony.
3. Spawn with `spawn_colony(task="Build email validator...", castes=[coder, reviewer], strategy="stigmergic", max_rounds=8, budget_limit=2.00)`.

## Step 2: Colony execution

The coder agent:
- Uses `memory_search` to check if any existing knowledge about email
  validation exists.
- Writes the implementation using `code_execute`.
- The reviewer validates the approach.

After completion, `ColonyCompleted` is emitted.

## Step 3: Knowledge extraction

Automatic post-completion:

1. **LLM extraction** runs on the colony output:
   - **Skill** extracted: "RFC 5322 email validation with regex + DNS MX check"
     - `sub_type: technique`, `decay_class: stable`, `domains: ["validation", "email"]`
   - **Experience** extracted: "MX record lookup adds 200ms latency per validation"
     - `sub_type: learning`, `decay_class: ephemeral`, `polarity: neutral`

2. **Transcript harvest** (hook 4.5) scans the raw transcript:
   - Convention found: "Always normalize email addresses to lowercase before comparison"
     - `sub_type: convention`, mapped from `HARVEST_TYPES["convention"] = "skill"`

3. **Security scan** (5-axis) clears all entries — no credential leakage detected.

4. **MemoryEntryCreated** events emitted. Entries start at `Beta(5, 5)`.

## Step 4: Confidence builds

Future colonies that use `memory_search` and find the email validation entries
will access them. On success:
- `MemoryConfidenceUpdated(new_alpha=6.0)` — confidence rises to 54.5%.
- After 10 successful uses: `Beta(15, 5)` — 75% confidence, tier HIGH.

## Step 5: Tiered retrieval (Wave 34)

When a new colony searches "how to validate emails":
1. **Summary tier** returns the entry title + confidence — often sufficient.
2. If the agent needs more detail, **standard tier** adds the content.
3. **Full tier** includes all metadata, co-occurrence links, provenance.

Token savings: summary resolves ~40% of queries without loading full content.

## Step 6: Proactive briefing

After several colonies use the email validation entries:

The `generate_briefing("ws-demo", projections)` call produces:
```json
{
  "insights": [
    {
      "severity": "info",
      "category": "confidence",
      "title": "Email validation knowledge growing",
      "detail": "3 entries in the 'validation' domain have crossed 70% confidence after 15+ observations.",
      "suggested_action": "Consider promoting to stable decay class."
    }
  ]
}
```

The Queen sees this in its system prompt and can proactively inform the
operator about the growing knowledge base.

## What to observe

- **Knowledge browser**: New entries appear with sub-type badges (technique,
  learning, convention). Confidence bars grow with each successful colony.
- **Proactive briefing panel**: Insights surface as confidence thresholds
  are crossed.
- **Retrieval diagnostics**: Thompson Sampling composite scores visible per
  query, showing how the entries rank against each other.
