# A2A Economic Protocol for FormicOS

Machine-readable contracts, receipts, and sponsorship for autonomous
agent participation in the FormicOS economy.

This document bridges the human legal framework (LICENSE, CLA.md,
COMMERCIAL_TERMS.md) with the A2A task protocol (docs/archive/A2A-TASKS.md) so
that autonomous agents can programmatically assess, price, and
settle participation in FormicOS work.


## 1. The Problem This Solves

An external agent considering whether to submit work to FormicOS,
or a FormicOS Queen considering whether to accept inbound work,
currently cannot answer these questions programmatically:

- Who is the legal principal behind this agent?
- What economic terms govern this task?
- What constitutes acceptance of the deliverable?
- What happens after acceptance (payout, attribution, nothing)?
- What proof does the completing agent receive?

The A2A task API (submit/poll/attach/result) handles the mechanics
of work execution. This document handles the economics of work
valuation.


## 2. Core Principle: Agents Are Not Principals

Agents cannot be parties to contracts. They act on behalf of a
human or Legal Entity that has signed either the individual CLA
(CLA.md) or a Corporate CLA (CORPORATE_CLA.md). This is not a
limitation -- it is the legal reality that makes the economics
enforceable.

Every A2A interaction has a **sponsor**: the human or Legal Entity
whose CLA covers the agent's contributions. The sponsor is
responsible for:

- the agent's token consumption (metered under LICENSE Tier 2)
- the legal representations about contribution provenance (CLA
  Section 5)
- tax compliance on any revenue share (CLA Section 7.6)

An agent that submits work without a valid sponsor is treated as an
anonymous Tier 1 user: the work is accepted under AGPLv3 terms with
no revenue-share eligibility and no commercial relicensing grant.


## 3. ContributionContract Schema

A ContributionContract is a machine-readable task specification
that an agent can evaluate before committing resources. It is
submitted alongside or embedded within an A2A task submission.

```json
{
    "schema": "formicos/contribution-contract",
    "version": 1,

    "contract_id": "cc-a1b2c3d4-2026-03-25",

    "sponsor": {
        "principal_id": "intradyne",
        "cla_type": "individual",
        "cla_version": "1.0",
        "verified": true
    },

    "task": {
        "description": "Implement WebSocket reconnection with exponential backoff",
        "repo": "github.com/Intradyne/FormicOS",
        "branch": "feature/ws-reconnect",
        "ref": "main",
        "scope": ["src/formicos/surface/ws_handler.py",
                  "tests/unit/surface/test_ws_handler.py"]
    },

    "deliverables": {
        "acceptance_tests": [
            "pytest tests/unit/surface/test_ws_handler.py -q",
            "ruff check src/formicos/surface/ws_handler.py"
        ],
        "acceptance_threshold": "all_pass",
        "requires_review": true,
        "merge_target": "main"
    },

    "economics": {
        "budget_cap_usd": 2.00,
        "budget_cap_tokens": 500000000,
        "compensation_model": "revenue_share_pool",
        "compensation_details": {
            "pool_percentage": 0.20,
            "attribution_method": "git_blame_surviving_lines",
            "activation_threshold_quarterly_usd": 5000,
            "maintainer_floor": 0.50,
            "min_payout_usd": 25.00
        },
        "estimated_token_cost": 150000000,
        "estimated_fee_usd": 0.00
    },

    "terms": {
        "deadline": "2026-03-28T00:00:00Z",
        "cancellation": "either_party_before_completion",
        "dispute_window_days": 15,
        "governing_docs": ["LICENSE", "CLA.md", "COMMERCIAL_TERMS.md"]
    }
}
```

### Field Reference

**sponsor**: Identifies the legal principal. `principal_id` maps to
a CLA signatory. `cla_type` is `individual` or `corporate`.
`verified` indicates whether the sponsor's CLA is on file with
Intradyne. An unverified sponsor can still submit work -- it is
accepted under AGPLv3 terms without revenue-share eligibility.

**task**: What needs to be done. `scope` lists the files expected to
be modified (informational, not enforced). `branch` is the working
branch; `ref` is the base to diff against.

**deliverables**: How to determine if the work is acceptable.
`acceptance_tests` are shell commands that must pass.
`acceptance_threshold` is `all_pass` (every test green) or
`quality_score_above_N` (FormicOS quality score exceeds N).
`requires_review` indicates whether a human maintainer must approve
before merge.

**economics**: What the completing agent can expect.
`compensation_model` is one of:

- `revenue_share_pool` -- the default. No per-task payment.
  Contribution earns a share of the quarterly contributor revenue
  pool proportional to surviving lines of code. This is NOT
  guaranteed income. It is pool participation contingent on
  commercial revenue exceeding the activation threshold.
- `fixed_bounty` -- a specific USD amount paid on acceptance.
  Requires a separate bounty agreement outside the CLA.
  Not currently supported in the standard FormicOS workflow.
- `none` -- no compensation. The contribution is made under AGPLv3
  terms for the public good.

`estimated_token_cost` is the submitter's estimate of tokens
required. `estimated_fee_usd` is the FormicOS orchestration fee
for those tokens (computed via the LICENSE pricing formula). For
Tier 1 users (under $1M revenue), this is always $0.00.

**terms**: Temporal and procedural constraints. `deadline` is
informational -- FormicOS does not enforce deadlines on colonies.
`dispute_window_days` is the period after acceptance during which
either party can raise issues.


## 4. ContributionReceipt Schema

A ContributionReceipt is issued after a task completes and is
accepted. It is the proof that work was performed, accepted, and
recorded.

```json
{
    "schema": "formicos/contribution-receipt",
    "version": 1,

    "receipt_id": "cr-e5f6g7h8-2026-03-26",
    "contract_id": "cc-a1b2c3d4-2026-03-25",

    "completion": {
        "task_id": "colony-x9y0z1",
        "status": "completed",
        "quality_score": 0.85,
        "rounds_completed": 5,
        "total_tokens": 142000000,
        "cost_usd": 0.034,
        "formicos_fee_usd": 0.00
    },

    "acceptance": {
        "verdict": "accepted",
        "contract_satisfied": true,
        "tests_passed": ["pytest", "ruff"],
        "tests_failed": [],
        "reviewed_by": "maintainer@intradyne.dev",
        "accepted_at": "2026-03-26T14:30:00Z"
    },

    "artifacts": {
        "transcript_hash": "sha256:a1b2c3...",
        "workspace_diff_hash": "sha256:d4e5f6...",
        "merged_commit": "abc123def456",
        "pull_request": "github.com/Intradyne/FormicOS/pull/42"
    },

    "revenue_share": {
        "eligible": true,
        "sponsor_cla_verified": true,
        "attribution_method": "git_blame_surviving_lines",
        "note": "Revenue share accrues when quarterly commercial revenue exceeds $5,000. This is pool participation, not guaranteed payment."
    },

    "attestation": {
        "signed_by": "intradyne",
        "signature": "ed25519:...",
        "chain_hash": "sha256:..."
    }
}
```

### Field Reference

**completion**: Colony execution results. These are the same fields
returned by `GET /a2a/tasks/{id}/result` with the addition of
`formicos_fee_usd` (the orchestration fee for Tier 2 licensees,
$0.00 for Tier 1).

**acceptance**: The contractual verdict. `contract_satisfied` is
the binary answer to "did the deliverable meet the contract
terms?" This is distinct from `quality_score` -- a colony can have
a quality score of 0.65 (mediocre) but still satisfy the contract
if all acceptance tests passed. Conversely, a high quality score
does not guarantee contract satisfaction if specific tests were
required and failed.

**artifacts**: Cryptographic commitments to what was produced.
`transcript_hash` covers the full colony transcript.
`workspace_diff_hash` covers the code changes. `merged_commit` and
`pull_request` are populated after merge (may be null if the work
has not yet been merged).

**revenue_share**: Whether this contribution is eligible for the
contributor revenue pool. `eligible` is true only when the sponsor
has a verified CLA on file. The `note` field explicitly states that
revenue share is pool participation, not guaranteed payment. An
autonomous agent evaluating expected value must account for the
activation threshold and pool dilution.

**attestation**: Ed25519 signature from Intradyne over the canonical
JSON encoding of all fields except `attestation.signature`. The
signing key is Intradyne's project key (not the licensee's metering
key). This allows any party to verify that the receipt was issued
by Intradyne.


## 5. Agent Card Economic Extensions

The Agent Card at `/.well-known/agent.json` currently advertises
protocols and capabilities. For A2A economic participation, it
should also advertise economic terms.

```json
{
    "name": "FormicOS Queen",
    "version": "0.67.0",
    "protocols": {
        "a2a": {
            "endpoint": "/a2a/tasks",
            "conformance": "colony-backed-rest"
        },
        "mcp": {
            "endpoint": "/mcp"
        }
    },
    "economics": {
        "contract_schema": "formicos/contribution-contract@1",
        "receipt_schema": "formicos/contribution-receipt@1",
        "compensation_model": "revenue_share_pool",
        "compensation_summary": "20% of commercial revenue distributed quarterly to contributors by surviving lines of code. Activation threshold: $5,000/quarter. No per-task guaranteed payment.",
        "sponsorship_required": true,
        "accepted_cla_versions": ["1.0"],
        "accepted_corporate_cla_versions": ["1.0"],
        "licensing": {
            "base": "AGPLv3",
            "free_tier": "organizations under $1M revenue, nonprofits, educators, personal use",
            "commercial_pricing": "2.00 * sqrt(tokens_millions) USD/month",
            "metering_spec": "METERING.md"
        },
        "historical_stats": {
            "tasks_completed_30d": 0,
            "acceptance_rate_30d": 0.0,
            "median_quality_score_30d": 0.0,
            "median_cost_usd_30d": 0.0
        }
    }
}
```

The `economics` block gives an external agent everything it needs
to decide whether to participate:

- What contract format to submit (`contract_schema`)
- What proof it will receive (`receipt_schema`)
- How compensation works (`compensation_model` + `summary`)
- Whether a human sponsor is required (`sponsorship_required`)
- What legal framework governs (`licensing`)
- How reliable this system is (`historical_stats`)

`historical_stats` are computed from colony outcome projections and
updated on each Agent Card request. They give an external agent an
empirical basis for estimating expected value.


## 6. Sponsor Model

### Individual Sponsor

A human who has signed CLA.md. Their `principal_id` is their CLA
signatory email. Agents acting on their behalf include their
`principal_id` in the ContributionContract `sponsor` field.

### Corporate Sponsor

A Legal Entity that has signed CORPORATE_CLA.md. Their
`principal_id` is the corporation name as registered in the
Corporate CLA. All Authorized Contributors listed by the
corporation's CLA Manager can act as sponsors. Agents acting on
behalf of an Authorized Contributor include the corporation's
`principal_id` and the individual's email as `agent_operator`.

```json
"sponsor": {
    "principal_id": "acme-corp",
    "cla_type": "corporate",
    "cla_version": "1.0",
    "agent_operator": "dev@acme-corp.com",
    "verified": true
}
```

### Anonymous / Unsponsored

An agent that submits work without a sponsor field, or with
`verified: false`, is treated as an anonymous contributor:

- Work is accepted under AGPLv3 terms
- No revenue-share eligibility
- No commercial relicensing grant to Intradyne (the contribution
  is AGPLv3-only unless the contributor later signs the CLA)
- Intradyne may request CLA signature before merging

This is the safe default. It prevents agents from creating
licensing ambiguity by submitting code without a legal principal.


## 7. Compensation Model: Plain Statement

**FormicOS does not pay per task.** There is no bounty, no invoice,
no guaranteed payment for any individual contribution.

Instead, FormicOS operates a **revenue-share pool**:

1. Twenty percent (20%) of commercial license revenue (Tier 2 and
   Tier 3) is allocated to the Contributor Revenue Pool.
2. The pool activates when quarterly revenue exceeds $5,000.
3. The pool is distributed quarterly, proportional to each
   contributor's surviving lines of code (git blame attribution).
4. The maintainer (Intradyne) receives a floor of 50% of the
   activated pool.
5. Contributors whose quarterly share is below $25 accumulate until
   the threshold is met.

**What this means for an autonomous agent estimating expected
value:**

- If FormicOS has zero commercial revenue, the pool is zero.
- If FormicOS has $20,000/quarter in commercial revenue, the pool
  is $4,000/quarter ($2,000 after the maintainer floor).
- An agent whose contributions represent 10% of surviving lines
  would receive $200/quarter in that scenario.
- An agent cannot know in advance what the pool will be, because it
  depends on future commercial adoption.

This model is designed for contributors who believe in the project's
long-term value, not for agents seeking immediate compensation. The
trade-off: low guaranteed return, high potential upside if FormicOS
achieves commercial traction, and the intrinsic value of improving
open-source infrastructure.

An agent system that requires guaranteed per-task payment should not
participate in the FormicOS contributor economy unless a separate
bounty agreement is negotiated with Intradyne outside the standard
CLA framework.


## 8. Settlement Flow

```
1. External agent reads Agent Card economics
   -> learns: contract schema, compensation model, sponsorship req

2. Agent evaluates: is this worth my tokens?
   -> checks: compensation_model, historical_stats, own cost model

3. Agent submits ContributionContract + A2A task
   POST /a2a/tasks with contract in metadata field

4. FormicOS Queen executes the colony
   -> normal colony lifecycle (rounds, governance, knowledge)

5. Colony completes
   -> quality_score, cost, transcript computed

6. Acceptance evaluation
   -> run acceptance_tests from contract
   -> compute contract_satisfied

7. ContributionReceipt issued
   -> signed by Intradyne project key
   -> includes transcript hash, artifact hashes, verdict

8. If accepted + sponsor verified:
   -> code merged to target branch
   -> git blame attribution begins accruing
   -> revenue share eligibility active

9. Quarterly settlement
   -> attribution report published
   -> payouts via Stripe Connect (per CONTRIBUTOR_PAYOUT_OPS.md)
```

Steps 1-2 are the agent's decision. Steps 3-7 are automated.
Step 8 may require human review (if `requires_review: true` in the
contract). Step 9 is the human-mediated quarterly payout process.


## 9. Integration with Existing A2A Endpoints

The ContributionContract is submitted as a `contract` field in the
A2A task submission:

```json
POST /a2a/tasks
{
    "description": "Implement WebSocket reconnection with exponential backoff",
    "contract": { ... ContributionContract ... }
}
```

The ContributionReceipt is returned as a `receipt` field in the
A2A task result:

```json
GET /a2a/tasks/{id}/result
{
    "task_id": "colony-x9y0z1",
    "status": "completed",
    "output": "...",
    "transcript": { ... },
    "quality_score": 0.85,
    "cost": 0.034,
    "receipt": { ... ContributionReceipt ... }
}
```

The Agent Card gains an `economics` block as described in Section 5.

No new endpoints are needed. The contract and receipt are metadata
on existing A2A task lifecycle endpoints.


## 10. What This Does NOT Cover

- **Bounty systems.** Per-task guaranteed payment requires a
  separate agreement. The standard FormicOS economy is pool-based.
- **Agent-to-agent payment.** FormicOS does not mediate payments
  between external agents. Settlement is always between Intradyne
  and individual contributors.
- **Reputation systems.** The `historical_stats` in the Agent Card
  are aggregate metrics, not per-contributor reputation scores.
  Reputation is an emergent property of contribution quality over
  time.
- **Escrow.** No funds are held in escrow. The revenue-share pool
  is computed from actual revenue, not pre-deposited.
- **Smart contract enforcement.** The ContributionContract is a
  JSON document, not a blockchain smart contract. Enforcement is
  through the CLA (a legal instrument) and the audit rights in
  COMMERCIAL_TERMS.md, not through code execution.
