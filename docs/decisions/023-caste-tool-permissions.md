# ADR-023: Caste-Based Tool Permission Enforcement

**Status:** Accepted  
**Date:** 2026-03-14  
**Stream:** B

## Decision

Enforce deny-by-default tool permissions per caste via a `CasteToolPolicy` model checked before every tool dispatch in `engine/runner.py`.

## Context

Without explicit permission checks, any agent can attempt any MCP tool call. That is unacceptable once Wave 14 adds code execution, service routing, and richer colony mechanics.

## Rules

- each tool belongs to a `ToolCategory`
- each caste declares allowed categories
- unknown tools are denied
- unknown castes are denied
- explicit deny lists override category allow lists
- per-iteration tool-call limits are part of the same policy surface

## Consequences

- every new MCP tool requires a category mapping
- policies are hardcoded in Wave 14 for simplicity
- denials should surface clearly to both the agent and the operator

## Rejected alternatives

**Prompt-only permissions**  
Rejected. LLMs do not reliably enforce access control on their own.

**Full external RBAC stack**  
Rejected. Overkill for the current local-first single-operator architecture.

## Implementation note

See `docs/waves/wave_14/algorithms.md`, Section 4.
