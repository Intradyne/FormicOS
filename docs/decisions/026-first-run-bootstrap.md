# ADR-026: First-Run Bootstrap Behavior

**Status:** Accepted
**Date:** 2026-03-14
**Context:** Wave 15. Making the first launch experience work without operator configuration.

---

## Decision

Extend the existing first-run detection in `surface/app.py` to auto-load templates and send a welcome Queen message. Do NOT add a new event type.

## Context

The current first-run code (post-Wave 14) creates a default workspace and thread when `projections.last_seq == 0`. This gives the operator a blank shell with no guidance.

A new operator needs:
1. Templates visible in the browser without manual loading
2. A prompt telling them what to do
3. A path from "I opened the app" to "I spawned my first colony" in under 60 seconds

## Implementation

The lifespan function in `surface/app.py` adds two steps after creating the default workspace/thread:

1. **Template visibility check:** Call `load_templates()` from `template_manager.py` and log the count. Templates from `config/templates/*.yaml` are already loaded directly from disk by the existing surface layer, so first-run only needs to verify they are readable and visible.

2. **Welcome Queen message:** Emit a `QueenMessage` event with `role="queen"` containing a 3-step getting-started guide. This uses the existing event type -- no new events.

## Why not a new `FirstRunCompleted` event?

First-run detection is a surface-layer concern. It triggers once, it's local to the bootstrap sequence, and nothing else in the system reacts to it. Adding it to the event union would be contract bloat with no consumer.

The signal is `projections.last_seq == 0`. That's sufficient, permanent, and free.

## Why not a `.first_run_complete` flag file?

The `last_seq == 0` check is idempotent. If the operator deletes the database and restarts, they get the welcome experience again -- which is correct behavior. A flag file would persist across database resets and produce confusing state.

## Alternatives considered

**Onboarding overlay / modal:** More complex, requires frontend-specific first-run detection, and adds a component that's only used once. The Queen message achieves the same goal with zero new UI code.

**Template pre-seeding in Docker image:** Would work but couples templates to the image build. Loading from `config/templates/` at runtime is more operator-friendly -- they can edit templates before first launch.
