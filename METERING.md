# FormicOS Usage Metering System

Technical specification for the token metering and cryptographic
attestation system referenced by the FormicOS License Agreement.

This document is normative. The metering system described here is
the canonical method for computing Total Tokens and producing Usage
Attestations under Tier 2 and Tier 3 Commercial Licenses.


## What is metered

**Total Tokens** is the sum of all input tokens, output tokens, and
reasoning tokens processed through the FormicOS orchestration
runtime during a Billing Period (one calendar month).

Total Tokens = input_tokens + output_tokens + reasoning_tokens

This includes tokens processed by both local inference servers and
cloud API providers.

### Cache-read token accounting

Cache-read tokens are a SUBSET of input tokens. When a provider
serves a cached response, the tokens that hit the cache are still
input tokens -- they are simply served at a lower cost to the
licensee by the provider. For metering purposes, cache-read tokens
are already counted within input_tokens. They are NOT added
separately to Total Tokens.

The attestation schema includes a cache_read_tokens field for
informational transparency only. This field shows what portion of
input_tokens were served from cache. It does not affect the Total
Tokens computation or the fee.

Example: if a Billing Period has input_tokens=42M, output_tokens=
18M, reasoning_tokens=6M, and cache_read_tokens=12M, then Total
Tokens = 42M + 18M + 6M = 66M. The 12M cache-read tokens are
already inside the 42M input_tokens figure.

### What is NOT metered

- Tokens consumed by systems external to FormicOS
- Tokens used by the operator's own scripts or tools outside the
  FormicOS runtime
- Embedding tokens used for vector search (these are not LLM
  generation tokens)
- Tokens consumed during FormicOS development, testing, or CI runs
  where the metering system is not active


## Data source

FormicOS emits `TokensConsumed` events for every LLM call made
through the orchestration runtime. Each event contains:

    {
        "type": "TokensConsumed",
        "seq": 12345,
        "timestamp": "2026-03-25T14:30:00Z",
        "address": "workspace/thread/colony/round/turn",
        "input_tokens": 1500,
        "output_tokens": 800,
        "reasoning_tokens": 0,
        "cache_read_tokens": 500,
        "model": "qwen3-30b-a3b",
        "provider": "local",
        "cost_usd": 0.0,
        "agent_id": "coder_0"
    }

Note: cache_read_tokens in the event is informational. The
input_tokens field already includes any tokens served from cache.

These events are stored in the append-only event store (SQLite WAL
by default). The event store is the source of truth for all token
counts. Events are sequentially numbered and immutable once written.


## Attestation production

At the end of each Billing Period (or on demand), the metering
module produces a Usage Attestation -- a JSON document containing
aggregate token counts and a cryptographic signature.

### Attestation schema

    {
        "version": 1,
        "license_id": "lic-a1b2c3d4",
        "period_start": "2026-03-01T00:00:00Z",
        "period_end": "2026-03-31T23:59:59Z",
        "total_tokens": 66000000,
        "breakdown": {
            "input_tokens": 42000000,
            "output_tokens": 18000000,
            "reasoning_tokens": 6000000,
            "cache_read_tokens": 12000000
        },
        "by_provider": {
            "local": 54000000,
            "anthropic": 8000000,
            "openai": 4000000
        },
        "event_count": 8432,
        "first_event_seq": 100001,
        "last_event_seq": 108432,
        "chain_hash": "a1b2c3...64hex",
        "computed_fee_usd": 16.25,
        "signature": "ed25519...128hex"
    }

### Fields

- `version`: schema version (currently 1)
- `license_id`: unique identifier for this Commercial License
- `period_start`, `period_end`: Billing Period boundaries (UTC)
- `total_tokens`: input_tokens + output_tokens + reasoning_tokens
  across all events in the period. This is T (in raw tokens) used
  in the pricing formula. Note: this equals the sum of the three
  non-cache fields in breakdown. cache_read_tokens is informational
  and does not contribute to total_tokens.
- `breakdown`: per-category token counts for transparency.
  cache_read_tokens shows what portion of input_tokens came from
  cache. It is a subset, not an addition.
- `by_provider`: per-provider token counts for transparency. These
  are informational and do not affect the fee computation.
- `event_count`: number of TokensConsumed events in the period
- `first_event_seq`, `last_event_seq`: event sequence range,
  enabling audit continuity between periods
- `chain_hash`: SHA-256 hash of the concatenation of all event
  payloads in sequence order. Supports event-store integrity checks
  and audit reconciliation.
- `computed_fee_usd`: the fee computed by applying the pricing
  formula to total_tokens. Informational -- the formula in the
  LICENSE is canonical.
- `signature`: Ed25519 signature over the canonical JSON encoding
  of all fields except `signature` itself.


## Cryptographic integrity

### Key derivation

The Ed25519 signing key is derived from the license key at
activation:

    import hashlib
    from nacl.signing import SigningKey

    def derive_signing_key(license_key: str) -> SigningKey:
        seed = hashlib.sha256(
            f"formicos-metering-v1:{license_key}".encode()
        ).digest()
        return SigningKey(seed)

The corresponding verify key is registered with the copyright
holder at license activation. The licensee retains the signing key.
The copyright holder can verify attestation authenticity without
possessing the signing key.

### Signing process

    import json

    def sign_attestation(attestation: dict, key: SigningKey) -> str:
        # Canonical JSON: sorted keys, no whitespace
        payload = json.dumps(
            {k: v for k, v in attestation.items() if k != "signature"},
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return key.sign(payload).signature.hex()

### Chain hash computation

The chain hash provides a cryptographic consistency check for the
underlying event store. It is computed by hashing each
TokensConsumed event's payload in sequence order:

    import hashlib

    def compute_chain_hash(events: list[dict]) -> str:
        h = hashlib.sha256()
        for event in sorted(events, key=lambda e: e["seq"]):
            payload = json.dumps(
                event, sort_keys=True, separators=(",", ":")
            ).encode("utf-8")
            h.update(payload)
        return h.hexdigest()

If events are inserted, deleted, or modified after the hash is
computed, the chain hash will not match. The copyright holder can
request the raw events during an audit to verify the chain hash
independently.

This mechanism is audit-friendly, but it is not by itself an
external anti-fraud anchor because the licensee controls the local
event store and signing environment. Stronger tamper-evidence would
require an external receipt log, transparency service, or other
independent anchoring layer.


## CLI interface

The metering module provides a command-line interface:

    # View current period usage
    formicos billing status

    # Generate attestation for a completed period
    formicos billing attest --period 2026-03

    # Submit attestation to billing endpoint
    formicos billing submit --period 2026-03

    # View historical attestations
    formicos billing history

    # Dry run: compute fee without generating attestation
    formicos billing estimate

    # Validate the metering pipeline end-to-end
    formicos billing self-test

### Self-test

The `self-test` command validates the entire metering pipeline
without generating a real attestation or submitting anything. It:

  1. Queries the event store for TokensConsumed events in the
     current period
  2. Computes aggregate token counts
  3. Computes the chain hash over the event sequence
  4. Generates a test attestation (marked version: "test")
  5. Signs the test attestation with the derived key
  6. Verifies the signature
  7. Computes the fee using the canonical formula
  8. Reports any configuration issues (missing license key,
     unreachable billing endpoint, event store gaps)

This enables Tier 2 licensees to verify their metering works before
the first real billing period. A successful self-test output:

    FormicOS Billing Self-Test
    --------------------------
    Event store:      OK (8432 TokensConsumed events this period)
    Token counts:     OK (total: 66,000,000)
    Chain hash:       OK (a1b2c3...64hex)
    Key derivation:   OK (verify key: ed25519:...)
    Signature:        OK (round-trip verified)
    Computed fee:     $16.25
    Billing endpoint: OK (https://billing.formicos.dev reachable)
    --------------------------
    All checks passed. Ready for attestation.


## Offline operation

FormicOS is a local-first system. The metering module does not
require network connectivity during normal operation. Token counts
accumulate in the local event store. Attestations are generated
locally. Submission is a separate step that requires connectivity
to the billing endpoint.

If the billing endpoint is unreachable, the attestation is saved
locally and can be submitted later. The 15-day submission window
(per the License) provides buffer for connectivity issues.


## Transparency

The metering module's source code is part of the AGPLv3-licensed
FormicOS distribution. Any licensee can inspect, audit, and verify
the token-counting logic. The attestation schema, signing process,
and chain hash computation are fully specified in this document.

The copyright holder publishes the verification key and attestation
validation tool, allowing any party to verify that a given
attestation was produced with a registered verify key and has not
been modified after signing. This does not, by itself, prove that
the local event history was not rewritten before the attestation was
generated.


## AGPL interaction

The metering module is distributed as an integral component of
FormicOS under the AGPLv3. It is not a separate work.

Disabling, removing, or materially modifying the metering module
constitutes a modification of the software. If the modified version
is deployed over a network (triggering AGPLv3 Section 13), the
modifier must make the complete corresponding source code --
including the modifications to the metering module -- available to
all network users.

This does not prevent modification. It ensures that modifications
to the metering system are publicly visible and subject to the same
open-source obligations as any other FormicOS modification.


## Future: execution-weighted contribution attribution

A future version of the metering system may incorporate runtime
execution profiling to weight contributor revenue shares by code
execution frequency. This would use statistical sampling (e.g.,
py-spy at 100 Hz for 5-minute windows) to record which source
files are on the call stack during token processing, then correlate
with git blame authorship.

This capability is documented here for completeness. It is not
active in the current version. Activation will be announced via an
Architecture Decision Record and thirty (30) days notice to
Contributors per the License Agreement.
