# FormicOS v0.9.0 — Perception & Scaling Engine

FormicOS v0.9.0 is the **Perception & Scaling Engine** release. It transforms FormicOS from a text-routing orchestrator into a memory-safe, financially-governed reasoning system capable of ingesting entire codebases and operating autonomously on consumer hardware.

Three architectural pillars define this release:

1. **Sovereign Memory** — A memory-mapped REPL sandbox (`SecuredTopologicalMemory`) that lets agents traverse 10M+ token repositories via byte-range clamping, eliminating OOM crashes under strict 8k context ceilings. Recursive sub-agent spawning via `formic_subcall` enables dynamic task decomposition without context window bloat.

2. **Topological Perception** — The Async Dockling integration replaces Euclidean text shredding with IBM's `HybridChunker`, preserving tables, lists, and structural hierarchies through the embedding pipeline. A CUDA semaphore contract ensures the ingestion queue never starves the RTX 5090's live LLM inference threads.

3. **Cryptographic Egress** — A zero-trust CFO caste holds the sole Ed25519 signing key. Worker agents are physically air-gapped from the network; all outbound traffic must pass through the `ProxyRouter`, which enforces three-stage cryptographic verification (signature, nonce freshness, budget check) before any paid API call leaves the container. Stripe ledger integration provides append-only financial audit.

---

## Specifications

| Document | Scope |
|----------|-------|
| [Sovereign Memory Specification](sovereign_memory_spec.md) | mmap sandbox, AST-validated REPL, DyTopo subcall routing, MCP server exposure |
| [Cryptographic Egress Specification](cryptographic_egress_spec.md) | CFO caste, Ed25519 signing, ProxyRouter air-gap, Stripe ledger proxy |
| [Perception Layer Specification](perception_layer_spec.md) | DocklingParser, HybridChunker topology preservation, async ingestion queue, CUDA semaphore |
