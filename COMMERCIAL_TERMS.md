# FormicOS Commercial Terms

Version 1.0

These Commercial Terms govern the payment, reporting, and dispute
resolution mechanics for Tier 2 (Metered Commercial License) and
Tier 3 (Enterprise Agreement) licensees of FormicOS. The fee
computation formula is specified in the FormicOS License Agreement
(LICENSE). These Terms govern how that fee is reported, invoiced,
and paid.

These Terms become binding upon Licensee's first Usage Attestation
submission. By submitting an attestation, Licensee accepts these
Terms in their entirety.

IMPORTANT: Have these Terms reviewed by qualified legal counsel
before submitting your first attestation.


## 1. AGREEMENT STRUCTURE

The FormicOS commercial licensing relationship consists of four
instruments:

  (a) The FormicOS License Agreement (LICENSE), which specifies the
      AGPLv3 base license, Tier 1 free-use permissions, Tier 2
      pricing formula, and Contributor Revenue Share.

  (b) These Commercial Terms, which govern payment mechanics and
      dispute resolution.

  (c) The FormicOS Usage Metering Specification (METERING.md),
      which is the normative technical specification for computing
      Total Tokens and producing Usage Attestations.

  (d) The FormicOS Contributor License Agreement (CLA.md), which
      governs the relationship between Contributors and the
      copyright holder regarding revenue sharing.

In the event of conflict: the License Agreement controls on fee
computation and metering scope. These Commercial Terms control on
payment mechanics, invoicing, and dispute resolution.


## 2. REPORTING AND PAYMENT

### 2.1 Billing Period

Each calendar month is a Billing Period.

### 2.2 Attestation Submission

Within fifteen (15) days after the end of each Billing Period,
Licensee shall submit a Usage Attestation as specified in
METERING.md to the billing endpoint provided by Licensor.

### 2.3 Invoice and Payment

Licensor will issue an invoice within five (5) business days of
receiving a valid Usage Attestation. Payment is due within thirty
(30) days of invoice date.

### 2.4 Payment Methods

Licensor accepts payment via:
- ACH bank transfer (US accounts)
- Wire transfer (international accounts)
- Credit card via Stripe

Transaction fees for credit card payments are borne by Licensee.
ACH and wire transfers have no additional fees.

### 2.5 Currency

All fees are denominated in United States Dollars (USD). Licensees
paying in other currencies bear the exchange rate risk. The
applicable rate is the mid-market rate on the invoice date.

### 2.6 Late Payment

Payments more than thirty (30) days past due accrue interest at the
lesser of 1.5% per month or the maximum rate permitted by law.

Payments more than ninety (90) days past due constitute a material
breach. Licensor may terminate the Commercial License upon thirty
(30) days written notice if the breach is not cured.

### 2.7 Taxes

Fees are exclusive of all taxes. Licensee is responsible for all
applicable sales, use, VAT, GST, and withholding taxes. If
Licensee is required to withhold taxes, the payment to Licensor
must be grossed up so that Licensor receives the full invoiced
amount.


## 3. AUDIT

### 3.1 Audit Rights

Licensor may conduct one (1) audit per calendar year upon thirty
(30) days written notice. The audit is limited to:

  (a) Aggregate token counts per Billing Period (Total Tokens as
      defined in the License Agreement)
  (b) Event store sequence continuity (first/last event sequence
      numbers per period, chain hash verification)
  (c) Number of TokensConsumed events per period

The audit does NOT include access to prompts, model outputs, agent
conversation content, workspace files, or any other content
processed by FormicOS.

### 3.2 Audit Process

Licensee provides the requested aggregate data within fifteen (15)
business days of the audit notice. Licensor may engage an
independent third-party auditor bound by confidentiality
obligations.

### 3.3 Audit Findings

If the audit reveals underreporting of Total Tokens by more than
ten percent (10%) for any Billing Period:

  (a) Licensee pays the underpayment amount plus the lesser of
      $5,000 or the reasonable cost of the audit.
  (b) Licensor may conduct one additional audit within the
      following twelve (12) months.

If the audit reveals no material discrepancy, Licensor bears the
cost of the audit.


## 4. TERM AND TERMINATION

### 4.1 Term

These Commercial Terms are effective upon Licensee's first
attestation submission and continue for successive one-year terms
unless terminated.

### 4.2 Termination by Licensee

Licensee may terminate at any time by providing thirty (30) days
written notice. Licensee must pay all fees accrued through the
termination date. Upon termination, Licensee must either:

  (a) comply fully with AGPLv3 Section 13, OR
  (b) cease use of FormicOS.

### 4.3 Termination by Licensor

Licensor may terminate for material breach (including persistent
late payment or attestation fraud) upon thirty (30) days written
notice if the breach is not cured within the notice period.

### 4.4 Effect of Termination

Sections 3 (Audit), 5 (Limitation of Liability), 6 (Dispute
Resolution), 7 (Force Majeure), and 8 (General) survive
termination.


## 5. LIMITATION OF LIABILITY

TO THE MAXIMUM EXTENT PERMITTED BY LAW, LICENSOR'S TOTAL LIABILITY
UNDER THESE TERMS SHALL NOT EXCEED THE FEES PAID BY LICENSEE IN
THE TWELVE (12) MONTHS PRECEDING THE CLAIM.

NEITHER PARTY SHALL BE LIABLE FOR INDIRECT, INCIDENTAL, SPECIAL,
CONSEQUENTIAL, OR PUNITIVE DAMAGES, REGARDLESS OF THE THEORY OF
LIABILITY.


## 6. DISPUTE RESOLUTION

### 6.1 Fee Computation Disputes

Disputes about fee computation are resolved by running the
canonical pricing function (specified in the License Agreement)
against the attested Total Tokens. The function is deterministic.
If both parties agree on the input (Total Tokens), the output (fee)
is not disputable.

If the parties disagree on Total Tokens, the dispute is resolved
via the audit process in Section 3.

### 6.2 Other Disputes

All other disputes are resolved by binding arbitration under the
rules of the American Arbitration Association, conducted in the
state of the Licensor's principal place of business. The
arbitrator's award is final and enforceable in any court of
competent jurisdiction.

### 6.3 Governing Law

These Terms are governed by the laws of the State of Colorado,
without regard to conflict-of-laws principles.


## 7. FORCE MAJEURE

Neither party is liable for failure or delay in performance caused
by events beyond its reasonable control, including but not limited
to: natural disasters, acts of government, pandemic, war, civil
unrest, power or internet outages, and third-party service provider
failures.

If the billing endpoint is unavailable due to a force majeure
event, the fifteen (15) day attestation submission deadline
(Section 2.2) is extended by the duration of the outage plus five
(5) business days. Licensee must submit the attestation promptly
after the force majeure event ends.

If a force majeure event prevents performance for more than ninety
(90) consecutive days, either party may terminate these Terms upon
written notice without penalty.


## 8. GENERAL

### 8.1 Entire Agreement

The License Agreement, these Commercial Terms, the Usage Metering
Specification, and any executed Enterprise Agreement constitute the
entire agreement between the parties regarding FormicOS commercial
licensing. The Contributor License Agreement governs a separate
relationship (contributor rights and revenue sharing) and is not
part of the licensee agreement.

### 8.2 Amendment

Licensor may update these Commercial Terms (excluding the pricing
formula) with sixty (60) days written notice. Updated Terms apply
to Billing Periods beginning after the notice period.

The pricing formula coefficient in the License Agreement may only
be changed with six (6) months written notice. Any other change to
the pricing formula (including changes to the functional form)
requires twelve (12) months written notice. In either case, the
change applies prospectively to Billing Periods beginning after the
notice period. Fees for prior Billing Periods are computed under
the formula in effect during that period.

### 8.3 Assignment

Licensee may not assign these Terms without Licensor's written
consent. Licensor may assign these Terms in connection with a
merger, acquisition, or sale of substantially all assets.

### 8.4 Severability

If any provision of these Terms is found unenforceable, the
remaining provisions continue in full force. The unenforceable
provision is reformed to the minimum extent necessary to make it
enforceable.

### 8.5 Waiver

Failure to enforce any provision is not a waiver of future
enforcement of that or any other provision.

### 8.6 Notices

All notices under these Terms must be in writing and delivered via
email to the addresses registered at license activation. A notice
is effective upon confirmed delivery.
