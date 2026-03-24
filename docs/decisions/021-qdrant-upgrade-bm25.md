# ADR-021: Qdrant Image Upgrade for Server-Side BM25

**Status:** Accepted  
**Date:** 2026-03-14  
**Context:** Wave 14 pre-requisite

## Decision

Upgrade the Qdrant Docker image to a version that supports the server-side BM25 sparse path already coded in Wave 13. The current planning baseline assumes `qdrant/qdrant:v1.16.2`.

## Context

Wave 13 wrote the sparse branch using server-side BM25 conversion through the Qdrant client. In the live Wave 13 stack, that path degrades because the running server/image does not provide the required support. As a result:
- dense retrieval still works
- the sparse branch does not contribute real results
- logs still show a client/server mismatch

## Consequences

- Wave 14 treats the Qdrant image upgrade as a real gate
- sparse vector backfill/re-upsert must happen after the upgrade
- hybrid verification in Wave 14 must prove both branches are live
- if official Qdrant requirements differ from the assumed version pin, update the pin and note it in the docs

## Rejected alternative

**Client-side BM25 fallback in Python**  
Rejected for now. It would add weight and operational complexity when the server-side path is the intended architecture.
