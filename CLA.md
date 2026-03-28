# FormicOS Contributor License Agreement

Version 1.0

IMPORTANT: This is a legal instrument. Have it reviewed by qualified
legal counsel before relying on it.

This Contributor License Agreement ("Agreement") is between Intradyne, the
copyright holder and lead maintainer of FormicOS ("Intradyne"), and the
individual or Legal Entity accepting this Agreement ("Contributor").

By signing this Agreement electronically, submitting it through the project's
CLA workflow, or otherwise indicating assent in a contribution channel
designated by Intradyne, Contributor agrees to the following terms.


## 1. Purpose

FormicOS is built in the open because open development produces better
software. The project is distributed under the GNU Affero General Public
License version 3 with additional permissions and an alternative commercial
licensing path. This Agreement exists so that:

- the codebase stays available under the AGPLv3 for everyone to use, study,
  modify, and share -- free of charge for individuals, small businesses,
  nonprofits, and educators;
- Intradyne can also offer commercial licenses so that organizations
  choosing proprietary deployment help fund continued development;
- contributors who improve FormicOS share in the commercial revenue their
  work generates, creating a sustainable cycle where building the commons
  is also building a livelihood.

This Agreement is a license grant. It is not a copyright assignment. Except
for the rights expressly granted below, Contributor retains ownership of
Contributor's Contributions.


## 2. Definitions

"Contribution" means any code, documentation, configuration, test, build
artifact recipe, design text, or other copyrightable material intentionally
submitted by Contributor for inclusion in FormicOS and accepted into the
repository.

"FormicOS" means the software in this repository and its official
documentation.

"Commercial Terms" means the file `COMMERCIAL_TERMS.md` in the repository, as
updated from time to time under its stated amendment process.

"License" means the repository `LICENSE` file, including the AGPLv3 base
license, Section 7 additional permissions, and the commercial-license
framework.

"Contributor Revenue Pool" has the meaning given in the License.

"Eligible Contributor" means a Contributor who:

- has at least one merged Contribution subject to this Agreement;
- has provided any payout, tax, or identity information reasonably requested
  under Section 7;
- is not subject to payment restrictions under applicable law.

"Legal Entity" means the union of the acting entity and all other entities
that control, are controlled by, or are under common control with that
entity. "Control" means (a) the power to direct the management of such
entity, or (b) ownership of fifty percent (50%) or more of the outstanding
shares, voting interests, or beneficial ownership of such entity.


## 3. Copyright License and Commercial Relicensing Grant

Contributor grants Intradyne and its successors, affiliates, contractors, and
sublicensees a perpetual, worldwide, non-exclusive, irrevocable,
royalty-free, fully paid-up license to:

- use, reproduce, display, perform, and distribute the Contribution;
- modify, adapt, translate, and create derivative works of the Contribution;
- sublicense the Contribution under the License, a commercial license, or any
  successor licensing program for FormicOS;
- enforce the copyrights in the Contribution as part of the FormicOS codebase.

This grant includes the right to offer the Contribution under proprietary,
commercial, trial, evaluation, hosted, or negotiated enterprise terms without
seeking additional permission from Contributor.

Contributor understands that Intradyne may stop distributing FormicOS, may
change business models prospectively, and is not obligated to use every
Contribution in any particular release.


## 4. Patent License

Contributor grants Intradyne and recipients of the official FormicOS
distribution a perpetual, worldwide, non-exclusive, no-charge, royalty-free,
irrevocable patent license to make, have made, use, offer to sell, sell,
import, and otherwise transfer the Contribution and the portions of FormicOS
that necessarily practice Contributor's Contribution, but only for patent
claims owned or controlled by Contributor that are necessarily infringed by
the Contribution as submitted or as incorporated into FormicOS.

If Contributor institutes patent litigation against Intradyne or any official
FormicOS distributor alleging that a Contribution or FormicOS itself infringes
Contributor's patent rights, then the patent license granted by Contributor
under this Agreement terminates as of the date the litigation is filed.


## 5. Contributor Representations

Contributor represents and warrants that:

- Contributor is legally entitled to grant the rights in this Agreement.
- Each Contribution is an original work of authorship of Contributor, or
  Contributor has disclosed the source and license status of any third-party
  material included in the Contribution.
- Contributor is not knowingly submitting material that violates another
  party's copyright, trade secret, patent, or contractual rights.
- Contributor will identify any known legal restrictions, third-party notices,
  or patent concerns associated with a Contribution when submitting it.

If Contributor's employer or another Legal Entity has rights in a proposed
Contribution, Contributor represents that Contributor has authority to submit
the Contribution on that party's behalf, that the party has waived or
licensed the relevant rights for this purpose, or that the party has executed
another written agreement acceptable to Intradyne covering those rights.


## 6. Submission Conditions

Contributor may submit Contributions personally or on behalf of a Legal
Entity. If Contributor's employer has executed a Corporate Contributor
License Agreement (CORPORATE_CLA.md), Contributor does not need to
separately demonstrate employer authorization under Section 5.
Otherwise, Intradyne may require additional written confirmation for
entity-sponsored contributions, including confirmation of signatory
authority.

Intradyne may reject Contributions, require provenance clarification, or pause
review until ownership or licensing questions are resolved.

Unless otherwise agreed in writing, Contributions are provided on an "AS IS"
basis, without warranties or conditions of any kind.

Contributions submitted by autonomous agents (via A2A or other automated
channels) must identify a sponsoring principal -- a human or Legal Entity
who has signed this Agreement or a Corporate CLA. Agents are not legal
principals in their own right and cannot independently accept this Agreement.
See docs/A2A_ECONOMICS.md for the machine-readable contract and receipt
schemas that govern agent-submitted contributions.


## 7. Contributor Revenue Share Program

### 7.1 Program Basis

This Section governs the contributor revenue-share commitment referenced in the
License. If the License and this Agreement conflict on pool size, pricing
inputs, or activation threshold, the License controls. This Agreement controls
on contributor eligibility, allocation mechanics, payout administration, and
program operations.

### 7.2 Pool Size and Activation Threshold

Twenty percent (20%) of Tier 2 and Tier 3 revenue is allocated to the
Contributor Revenue Pool, subject to the quarterly activation threshold stated
in the License. If the threshold is not met for a calendar quarter, no pool
distribution is owed for that quarter.

### 7.3 Maintainer Floor

For each quarter in which the Contributor Revenue Pool activates, Intradyne is
entitled to a maintainer allocation equal to the greater of:

- fifty percent (50%) of the activated quarterly Contributor Revenue Pool; or
- the amount Intradyne would receive under the same attribution formula
  applied to all other Eligible Contributors.

The remainder of the activated quarterly Contributor Revenue Pool is
distributed among Eligible Contributors other than Intradyne in proportion to
their contribution weight.

### 7.4 Attribution Formula

Unless and until revised under Section 7.8, contribution weight is determined
from surviving lines of code attributed by `git blame` on the current release
branch, excluding whitespace-only changes, pure mass-formatting changes, and
other mechanically excluded changes documented by Intradyne in the published
attribution report.

As of Version 1.0 of this Agreement, execution-frequency weighting described in
`METERING.md` is not active.

### 7.5 Attribution Report and Timing

If a quarterly pool distribution is owed, Intradyne will publish an
attribution report showing the material computation inputs used for the
distribution, including the activated pool amount, the maintainer allocation,
the attribution formula version, and each recipient's resulting share.

Pool distributions are made quarterly after quarter-end close and any required
revenue reconciliation.

### 7.6 Eligibility, KYC, and Tax Forms

As a condition of receiving payouts, Eligible Contributors must provide:

- legal name;
- current email address;
- country of residence;
- payment instructions reasonably requested by Intradyne;
- a valid IRS Form W-9 for U.S. persons, or applicable IRS Form W-8 for
  non-U.S. persons, if required by law.

Intradyne may withhold payments to comply with tax, sanctions, anti-money
laundering, or similar legal obligations.

### 7.7 Minimum Payout and Unreachable Contributors

Quarterly amounts below USD $25.00 are accrued for the Eligible Contributor
until the threshold is met, unless payment is otherwise required by law.

If Intradyne cannot complete payment to an Eligible Contributor after twelve
(12) months of good-faith attempts using the contact information then on file,
Intradyne may return the unpaid accrued amount to the general Contributor
Revenue Pool for future distributions.

### 7.8 Program Changes

Intradyne may update payout operations, reporting mechanics, and reasonable
administrative requirements prospectively.

Any change to the attribution algorithm itself, including activation of
execution-frequency weighting or changes to the maintainer-floor rule,
requires:

- an Architecture Decision Record or equivalent public design note; and
- at least thirty (30) days advance notice before the change applies to a new
  billing period or quarter.

### 7.9 No Guaranteed Revenue

Contributor acknowledges that the contributor revenue-share program depends on
actual Tier 2 and Tier 3 revenue. Intradyne does not guarantee that any
revenue threshold will be met, that any particular quarter will activate the
pool, or that Contributor will receive any minimum amount.


## 8. Optional Withdrawal From Future Pool Participation

Contributor may elect to stop participating in future contributor-pool
distributions by giving written notice to Intradyne. Such notice does not
revoke or narrow any license or patent rights already granted under this
Agreement.

After the effective date of withdrawal, Contributor will not accrue new
revenue-share amounts for future billing periods or quarters unless
Intradyne agrees otherwise in writing.

Previously accrued unpaid balances remain payable subject to this Agreement
and applicable law. If a Contributor's accrued balance is below the USD
$25.00 minimum payout threshold at the time of withdrawal, Intradyne will
pay the remaining balance within ninety (90) days of the withdrawal
effective date regardless of the threshold.


## 9. Term, Survival, and Irrevocability

This Agreement remains in effect for all Contributions submitted and accepted
before termination of Contributor's future participation.

The rights granted in Sections 3 and 4 are irrevocable for accepted
Contributions, except as expressly provided in Section 4 for patent
litigation.

Sections 3, 4, 5, 7, 8, 9, and 10 survive any cessation of future
contributions.


## 10. General

This Agreement does not create an employment, partnership, joint venture, or
fiduciary relationship between Contributor and Intradyne.

Intradyne may assign this Agreement in connection with a merger, acquisition,
internal reorganization, or sale of substantially all assets relating to
FormicOS. Contributor may not assign this Agreement without Intradyne's
written consent.

If any provision of this Agreement is held unenforceable, the remaining
provisions remain in effect and the invalid provision will be reformed to the
minimum extent necessary to make it enforceable.

This Agreement is governed by the laws of the State of Colorado, without
regard to conflict-of-laws rules.

This Agreement, together with the License and any written program terms
incorporated by reference, is the entire agreement between Contributor and
Intradyne regarding accepted Contributions unless the parties sign a separate
written superseding agreement.


## 11. Signature

Contributor may accept this Agreement by:

- signing it through the repository's CLA workflow;
- signing and delivering a copy to Intradyne; or
- electronically affirming assent through another contribution channel
  designated by Intradyne.

Contributor should not submit Contributions until this Agreement has been
accepted.
