# ADR-029: Colony File I/O as REST + Filesystem

**Status:** Accepted
**Date:** 2026-03-15
**Context:** Wave 16. Operator needs to upload context documents and download colony outputs.

---

## Decision

Colony file upload and export use REST endpoints and filesystem storage. No new events.

## Rationale

Files are context material consumed by agents during execution. They are not domain events that need replay or coordination.

**Upload:** POST multipart to `/api/v1/colonies/{id}/files`. Stored in `{data_dir}/workspaces/{ws}/colonies/{id}/uploads/`. Content injected into running colony via `colony_manager.inject_message()`.

**Export:** GET `/api/v1/colonies/{id}/export?items=outputs,chat,skills`. Assembles selected items into a zip streamed to the browser.

## Why not events?

An event-based approach (`FileUploaded`, `FileDownloaded`) would:
- Bloat the event log with large text payloads
- Add replay overhead (re-reading files on startup)
- Mix content delivery with domain coordination

Files are ephemeral context. They inform agents but don't change the colony's state machine. The event log tracks what the colony *did* (rounds, turns, completions). File I/O tracks what the operator *provided* — a surface-layer concern.

## Constraints

- Text files only for alpha (.txt, .md, .py, .json, .yaml, .csv)
- 10MB per file, 50MB per colony
- Upload content truncated to 8000 chars for context injection
- Binary files (PDF, images) deferred to Wave 17
