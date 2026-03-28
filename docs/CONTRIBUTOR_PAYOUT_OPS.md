# Contributor Payout Operations

Internal operations guide for administering the FormicOS Contributor
Revenue Share program. This document covers tax compliance, payment
mechanics, timing, and edge cases.

This is an operational reference, not a legal instrument. The binding
terms are in [CLA.md](CLA.md) (contributor rights and pool mechanics)
and [LICENSE](LICENSE) (pool size and activation threshold).


## Quarterly Cycle

| Step | Timing | Action |
|------|--------|--------|
| Quarter close | End of Q (Mar 31, Jun 30, Sep 30, Dec 31) | Revenue reconciliation begins |
| Revenue check | Q+5 business days | Determine if $5,000 activation threshold met |
| Attribution run | Q+10 business days | Run git blame, compute weights, generate report |
| Report publication | Q+15 business days | Publish attribution report to contributors |
| Dispute window | Q+15 to Q+30 business days | Contributors review and raise issues |
| Payout execution | Q+35 business days | Execute payments via Stripe Connect |

If the $5,000 quarterly threshold is not met, skip all steps after
the revenue check. No attribution report is required for inactive
quarters.


## Attribution Computation

### Running the formula

```bash
# Generate attribution report for current HEAD
python scripts/attribution.py \
    --repo . \
    --branch main \
    --revenue <quarterly_pool_amount> \
    --maintainer-floor 0.50 \
    --min-payout 25.00 \
    --ignore-revs .git-blame-ignore-revs \
    --output reports/attribution-YYYY-QN.json
```

The script (to be implemented as an addon or standalone tool):

1. Runs `git blame -w --line-porcelain` on all tracked files in
   `src/`, `frontend/src/`, `config/`, and `addons/`
2. Excludes files in `.git-blame-ignore-revs` (mass-formatting commits)
3. Excludes whitespace-only lines
4. Aggregates surviving lines per author email
5. Applies the maintainer floor (50% guaranteed to Intradyne)
6. Distributes the remaining 50% proportionally by surviving lines
7. Filters out contributors below the $25 minimum payout threshold
8. Outputs a JSON report with per-contributor breakdown

### Report format

```json
{
    "quarter": "2026-Q2",
    "pool_total_usd": 1250.00,
    "maintainer_allocation_usd": 625.00,
    "contributor_pool_usd": 625.00,
    "formula_version": "v1-git-blame",
    "commit_sha": "abc123...",
    "contributors": [
        {
            "email": "contributor@example.com",
            "name": "Jane Contributor",
            "surviving_lines": 2400,
            "percentage": 38.7,
            "gross_amount_usd": 241.88,
            "below_threshold": false,
            "accrued_balance_usd": 0.00
        }
    ],
    "below_threshold_accruals": [
        {
            "email": "small@example.com",
            "accrued_total_usd": 12.50,
            "note": "Accumulated until $25 threshold met"
        }
    ]
}
```

### Maintainer floor mechanics

The maintainer floor guarantees Intradyne receives the greater of:
- 50% of the activated quarterly pool, or
- whatever Intradyne would receive under the attribution formula alone

In practice, while Intradyne is the majority contributor (likely 90%+
of surviving lines), the floor is redundant -- the formula already
gives Intradyne the largest share. The floor matters when external
contributors collectively exceed 50% of surviving lines.


## Tax Compliance

### US contributors (W-9)

- Collect IRS Form W-9 before the first payout
- Store securely (encrypted at rest, access-controlled)
- Issue IRS Form 1099-NEC by January 31 for any contributor who
  received $600 or more in the prior calendar year
- The $600 threshold is per calendar year, not per quarter
- File 1099-NEC electronically via IRS FIRE system or through
  Stripe Connect (which handles 1099 generation automatically for
  connected accounts)
- Retain W-9 forms for 4 years after the last tax year they apply to

### Non-US contributors (W-8BEN / W-8BEN-E)

- Collect IRS Form W-8BEN (individuals) or W-8BEN-E (entities)
  before the first payout
- W-8 forms are valid for 3 calendar years from the year of signing
  (e.g., a form signed in 2026 expires December 31, 2029)
- Track expiration dates and request renewal 60 days before expiry
- Default withholding for foreign payees: 30% on US-source income
- Reduced rates available under tax treaties (contributor must claim
  treaty benefits on the W-8BEN, Part III)
- Common treaty rates: UK 0%, Canada 0%, Germany 0%, India 15%,
  Australia 0%, Japan 0% (for independent personal services)
- Verify treaty eligibility -- the contributor must be a tax resident
  of the treaty country and the payment must qualify under the treaty
  article (typically "Independent Personal Services" or "Business
  Profits")
- Withhold and remit to IRS using Form 1042 (annual) and 1042-S
  (per-recipient) by March 15 of the following year

### Stripe Connect handles most of this

If using Stripe Connect with Express or Standard accounts:
- Stripe collects W-9/W-8BEN during onboarding
- Stripe generates and files 1099s for US recipients
- Stripe handles KYC/AML verification
- You still need to handle 1042/1042-S for non-US withholding
  unless using Stripe's tax form automation (check current
  capabilities)


## Payment Rails

### Primary: Stripe Connect

Recommended for all payouts. Setup:

1. Create a Stripe Connect platform account
2. For each contributor, create a Connected Account (Express type)
3. Contributor completes Stripe's onboarding (KYC, bank details, tax
   forms) -- you never touch their bank details directly
4. Execute payouts via the Transfers API:

```python
import stripe

stripe.Transfer.create(
    amount=24188,  # cents
    currency="usd",
    destination="acct_contributor123",
    description="FormicOS Q2 2026 revenue share",
    metadata={
        "quarter": "2026-Q2",
        "formula_version": "v1-git-blame",
        "surviving_lines": "2400",
    },
)
```

Costs: $0.25 + 0.25% per payout + $2/month per active connected
account. For 10 contributors at $100 average payout: ~$22.50/quarter
in Stripe fees.

### Fallback: Manual wire / ACH

For contributors who cannot or will not use Stripe Connect:
- Collect bank details directly (encrypted storage required)
- Execute via business bank account ACH or wire
- Manual 1099 issuance required
- Track separately from Stripe-managed payouts

### Crypto (opt-in only)

For contributors who prefer USDC on a supported chain:
- Contributor provides a wallet address
- Transfer USDC via the chain of their choice
- Transaction hash serves as payment receipt
- You still owe 1099 reporting for US persons regardless of
  payment method
- Note: crypto payouts do NOT exempt you from tax withholding
  obligations for non-US persons


## Edge Cases

### Contributor becomes unreachable

Per CLA.md Section 7.7:

1. Attempt contact via the email on file
2. If no response after 30 days, try any alternative contact method
   (GitHub profile, LinkedIn, etc.)
3. Document all contact attempts with dates and methods
4. After 12 months of good-faith attempts, return the unpaid accrued
   amount to the general Contributor Revenue Pool
5. If the contributor reappears after reversion, they do not have a
   claim to the reverted amount (it was distributed in a subsequent
   quarter) -- but they resume accruing for future quarters

### Contributor withdraws from program

Per CLA.md Section 8:

1. Contributor provides written notice (email is sufficient)
2. Stop accruing new amounts from the next billing period
3. Pay any remaining balance, even if below $25, within 90 days
4. The contributor's license grants (Section 3, 4) remain in effect
5. Their code continues to be used under the CLA terms -- they just
   stop receiving future revenue share

### Contributor changes email / identity

- Git blame attribution is by author email
- If a contributor changes their email, their old commits still
  attribute to the old email
- Maintain a canonical mapping: `{old_email: canonical_email}`
- The attribution script should support an email alias file
- Contributors are responsible for notifying Intradyne of email
  changes

### Employer changes

- If a contributor was covered by a Corporate CLA and changes
  employers, they need either:
  (a) a new Corporate CLA from their new employer, or
  (b) to sign the individual CLA with their own employer
      authorization
- Past contributions remain licensed under the previous Corporate CLA
- Future contributions need fresh authorization

### Dispute resolution

- Attribution disputes: contributor believes the git blame count is
  wrong. Resolution: re-run attribution script with the contributor
  present (screen share or provide the raw data). The formula is
  deterministic -- same inputs always produce same outputs.
- Amount disputes: contributor believes the pool amount is wrong.
  Resolution: provide the quarterly revenue report showing Tier 2/3
  income. Revenue numbers are auditable via Usage Attestations.
- Formula disputes: contributor believes surviving-lines is unfair.
  Resolution: the formula can be changed via ADR + 30 days notice
  (per CLA Section 7.8). Disagreement about the formula is a
  governance question, not an operational one.

### Multiple contributors with same email

- Rare but possible (shared team email, generic address)
- Require unique personal emails for revenue share eligibility
- The attribution script should flag duplicate emails

### Zero-payout quarters

- If the $5,000 activation threshold is not met, publish a brief
  note: "Q2 2026: revenue below activation threshold. No pool
  distribution this quarter."
- No attribution report required
- Sub-threshold revenue does NOT accumulate toward future quarters
  (per LICENSE)


## Recordkeeping

Retain for at least 4 years (IRS requirement for 1099 records):
- All attribution reports (JSON + human-readable)
- All W-9 and W-8BEN forms (encrypted)
- All Stripe Connect transfer records
- All contact attempt logs for unreachable contributors
- All CLA acceptance records (individual + corporate)
- Quarterly revenue reconciliation showing Tier 2/3 income

Store attribution reports in `reports/` in the repo (public) or in
a private admin repo (if revenue numbers are confidential). The
formula inputs (git blame data) are inherently public since the repo
is public.


## Checklist: First Payout

- [ ] Stripe Connect platform account created
- [ ] Attribution script implemented and tested
- [ ] `.git-blame-ignore-revs` file maintained with formatting commits
- [ ] All eligible contributors have signed individual CLA
- [ ] All eligible contributors have completed Stripe Connect onboarding
- [ ] W-9 / W-8BEN collected for all eligible contributors
- [ ] Email alias mapping file created (if needed)
- [ ] Quarterly revenue reconciliation process documented
- [ ] Attribution report template reviewed by at least one contributor
- [ ] Test payout executed with a small amount to verify the pipeline
