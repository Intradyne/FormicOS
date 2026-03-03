# FormicOS v0.9.0: Cryptographic Egress Layer Specification

This document details the Zero-Trust, cryptographic egress architecture implemented in FormicOS v0.9.0. As FormicOS scales to an Agent-to-Agent economy, it is critical that worker agents operating inside isolated containers cannot autonomously spend funds by hitting external paid APIs (e.g., Anthropic, OpenAI, Stripe) without cryptographic authorization.

To solve this, v0.9.0 introduces the **Cryptographic Egress Layer**, a lock-and-key architecture where network calls are intercepted, cryptographically signed by a designated financial caste, and verified by an air-gapped proxy router.

---

## 1. The CFO Caste (Colony Financial Officer)
**Source:** `src/core/cfo.py`

The CFO (Colony Financial Officer) is a highly specialized orchestration caste. It is the **sole entity** within the colony trusted with the Ed25519 Private Signing Key.

### Responsibilities
- **Key Custody**: The CFO holds the `nacl.signing.SigningKey`. Worker or Coder agents do *not* have access to this key, meaning they cannot forge network requests.
- **Budget Evaluation**: The `CFOToolkit` maintains a stateful `$USD` budget (`budget_limit_usd`) and an append-only audit ledger. When evaluating an `ExpenseRequest` (e.g. hitting a Wikipedia API at `$0.01`), the CFO deducts from the remaining budget.
- **Cryptographic Signing (The "Key")**: If the expense is approved, the CFO calls `approve_and_sign()`. This serializes the request fields (amount, target API, justification, nonce, timestamp) into a canonical UTF-8 JSON byte string, producing a deterministic Ed25519 hex signature attached to the `ExpenseRequest`.
- **Stigmergy Interaction**: The CFO uses the `AsyncContextTree`. During Orchestrator Phase 4.5, it monitors `ctx("colony", "pending_expenses")`. If a Coder agent has requested a network call, the CFO wakes up, evaluates the request against the budget, and resolves the pending state.

---

## 2. The Proxy Router
**Source:** `src/core/network/egress_proxy.py`

The `ProxyRouter` is the air-gapped "Lock" in this architecture. All outbound traffic from the worker agents is structurally blocked except for traffic routed through this proxy.

### Physical Air-Gapping
The primary agent execution container must be physically air-gapped (via strict Docker networking) from the internet. The only way an agent can communicate with the outside world is by submitting an `ExpenseRequest` to the `ProxyRouter`, which acts as the sole egress node. Because the agent lacks the CFO's private key, it cannot directly curl outbound endpoints.

### The Three-Stage Verification Process
When the proxy receives an `ExpenseRequest`, it performs three strict verifications before utilizing `httpx` to forward the payload:

1. **Signature Verification**: The `ProxyRouter` holds the public `VerifyKey` inside its `KeyVault`. It rebuilds the canonical JSON byte string and uses libsodium/PyNaCl to verify the attached hex signature. If the agent tampered with *any* field (e.g., changing the `$0.01` amount to `$100.00`, or altering the `target_api`), the signature verification fails instantly and blocks the request.
2. **Nonce / Idempotency Verification**: To prevent malicious workers from capturing a validly signed request and replaying it endlessly (a Replay Attack), the proxy checks the `nonce` against an atomic, thread-safe `NonceLedger`. Once forwarded, the nonce is consumed and mapped to the current timestamp. Any duplicate nonces raise a `ProxyReplayError`.
3. **Allowlist Checking**: The proxy evaluates the `target_api` string against an explicit list of approved structural targets (e.g., restricting egress only to known model provider subnets or permitted search APIs) before forwarding the request to the upstream target.

---

## 3. The Gateway Test (Lock and Key Flow)
**Source:** `src/mcp/external_client.py`

The `ExternalNetworkGateway` represents the bridge between agnostic agent tool usage and the strict Zero-Trust egress routing.

### The complete "Lock and Key" Flow
1. **The Intercept**: A Coder agent calls `query("quantum computing")` to retrieve data. Instead of firing an HTTP request, the gateway intercepts this call and creates an *unsigned* `ExpenseRequest` with a new UUID `nonce`.
2. **The Wait State**: The gateway writes this unsigned request to the Stigmergy `AsyncContextTree` (`pending_expenses`) and deliberately suspends its thread by awaiting an `asyncio.Future[SigningKey | None]`.
3. **CFO Evaluation**: Asynchronous to the worker thread, the Orchestrator instantiates the CFO agent. The CFO reads the graph, approves the `$0.01` expense, and calls `authorize(nonce, signing_key)`.
4. **The Gateway Sign & Send**: The suspended `asyncio.Future` resolves, delivering the `SigningKey` temporarily to the gateway context. The gateway immediately calls `expense.sign(signing_key)`.
5. **Egress Forwarding**: The gateway dispatches the signed `ExpenseRequest` to the air-gapped `ProxyRouter.forward()`. The ProxyRouter verifies the signature, nonce, and allowlist, then natively forwards the HTTP request to the external world, eventually returning the JSON body back through the suspended agent tool call.
