# Demo: Federation — Two-Instance Knowledge Exchange

This walkthrough demonstrates federated knowledge exchange between two
FormicOS instances, including trust evolution and proactive intelligence.

---

## Prerequisites

- Two FormicOS instances running (Instance A and Instance B)
- Each with a workspace created
- Network connectivity between instances

## Step 1: Instance A builds knowledge

On Instance A, run a colony that builds testing expertise:

> Queen: "Write a comprehensive pytest fixture library for database testing."

After completion, Instance A has:
- **Skill**: "Pytest fixture composition for transactional DB testing"
  - `sub_type: technique`, `decay_class: stable`, `conf_alpha: 8, conf_beta: 5`
- **Skill**: "Factory pattern for test data generation"
  - `sub_type: pattern`, `decay_class: stable`, `conf_alpha: 6, conf_beta: 5`

## Step 2: Configure federation peer

On Instance A, add Instance B as a peer:

```python
federation_manager.add_peer(
    peer_id="inst-b",
    endpoint="https://instance-b.local:8080",
    replication_filter=ReplicationFilter(
        domain_allowlist=["testing", "pytest"],
        min_confidence=0.5,
    ),
)
```

## Step 3: Push replication

Instance A pushes knowledge to Instance B:

1. `fed_a.push_to_peer("inst-b")` sends CRDT events for matching entries.
2. Replication filter ensures only `testing`/`pytest` domain entries above
   50% confidence are sent.
3. Instance B receives and applies the events to its projection store.
4. Entries arrive with `hop_count=1` — trust-discounted by `trust * 0.9^1`.

## Step 4: Instance B uses federated knowledge

Instance B runs a colony:

> "Write integration tests for the payment service."

The colony's `memory_search` finds Instance A's testing entries:
- Thompson Sampling incorporates the trust-discounted confidence.
- The colony uses the "fixture composition" technique successfully.

## Step 5: Validation feedback

After the colony succeeds, Instance B sends validation feedback:

```python
await fed_b.send_validation_feedback("inst-a", "entry-001", success=True)
```

Instance A's peer trust for Instance B updates:
- `PeerTrust.alpha += 1` (success recorded)
- Trust score (10th percentile of Beta posterior) increases

## Step 6: Trust evolution

After 10 successful validations:
- `PeerTrust(alpha=11, beta=1).score ≈ 0.818` (high trust)
- Instance B's knowledge is retrieved with minimal discount

If failures occur:
- `PeerTrust.beta += 1` per failure
- Trust drops, federated entries rank lower in retrieval

## Step 7: Proactive intelligence fires

When trust drops significantly (e.g., after several failures):

```json
{
  "severity": "attention",
  "category": "federation",
  "title": "Declining peer reliability: inst-b",
  "detail": "Trust score for inst-b has dropped below 0.5 after 5 recent failures.",
  "suggested_action": "Review recent entries from inst-b and consider adjusting replication filters."
}
```

## Step 8: Conflict resolution

If Instance B sends an entry that contradicts Instance A's local knowledge:

1. **Pareto dominance**: If one entry dominates on evidence + recency, it wins.
2. **Adaptive threshold**: Composite score comparison with exploration bias.
3. **Competing hypotheses**: Both entries kept for operator resolution.

The Federation Dashboard shows:
- Peer trust scores with visual bars
- Sync status and pending events
- Recent conflicts with resolution method

## What to observe

- **Federation dashboard**: Peer table shows trust scores evolving after
  each validation feedback cycle.
- **Knowledge browser**: Federated entries have a source indicator showing
  the originating instance.
- **Proactive briefing**: Trust-related insights surface when thresholds
  are crossed.
