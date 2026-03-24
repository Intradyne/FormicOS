"""Deterministic maintenance service handlers (Wave 29).

Each handler is a plain async function registered on ServiceRouter.
Receives query_text and a context dict. Returns response text.
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from formicos.surface.runtime import Runtime

log = structlog.get_logger()


def make_dedup_handler(runtime: Runtime):  # noqa: ANN201
    """Factory: returns an async callable for dedup consolidation."""

    async def _handle_dedup(query_text: str, ctx: dict[str, Any]) -> str:
        projections = runtime.projections
        memory_store = getattr(runtime, "memory_store", None)
        if memory_store is None:
            return "Error: memory store not available"

        verified = [
            e for e in projections.memory_entries.values()
            if e.get("status") == "verified"
        ]
        verified.sort(key=lambda e: e.get("created_at", ""))

        merged_count = 0
        flagged: list[dict[str, Any]] = []

        for i, entry_a in enumerate(verified):
            for entry_b in verified[i + 1:]:
                try:
                    sim = await _compute_similarity(
                        memory_store, entry_a, entry_b,
                    )
                except Exception:  # noqa: BLE001
                    continue

                if sim >= 0.98:
                    # Auto-merge: merge the lower-confidence entry into higher
                    survivor, absorbed = (
                        (entry_a, entry_b)
                        if entry_a.get("confidence", 0) >= entry_b.get("confidence", 0)
                        else (entry_b, entry_a)
                    )
                    from formicos.core.events import MemoryEntryMerged  # noqa: PLC0415

                    target_content = survivor.get("content", "")
                    source_content = absorbed.get("content", "")
                    if len(source_content) > len(target_content) * 1.2:
                        m_content = source_content
                        strategy: str = "keep_longer"
                    else:
                        m_content = target_content
                        strategy = "keep_target"

                    target_domains = survivor.get("domains", [])
                    source_domains = absorbed.get("domains", [])
                    m_domains = sorted(set(target_domains) | set(source_domains))
                    existing_merged_from: list[str] = survivor.get("merged_from", [])
                    m_from = existing_merged_from + [absorbed.get("id", "")]

                    await runtime.emit_and_broadcast(MemoryEntryMerged(
                        seq=0,
                        timestamp=datetime.now(UTC),
                        address=survivor.get("workspace_id", ""),
                        target_id=survivor.get("id", ""),
                        source_id=absorbed.get("id", ""),
                        merged_content=m_content,
                        merged_domains=m_domains,
                        merged_from=m_from,
                        content_strategy=strategy,  # type: ignore[arg-type]
                        similarity=sim,
                        merge_source="dedup",
                        workspace_id=survivor.get("workspace_id", ""),
                    ))
                    merged_count += 1
                elif sim >= 0.82:
                    flagged.append({
                        "entry_a": entry_a.get("id"),
                        "entry_b": entry_b.get("id"),
                        "similarity": round(sim, 3),
                    })

        # Wave 30 B9: LLM-confirmed dedup for [0.82, 0.98) band
        llm_router = getattr(runtime, "llm_router", None)
        llm_confirmed = 0
        llm_dismissed = 0

        if flagged and llm_router is not None:
            # Build dismissed-pair set from last_status_reason
            dismissed_pairs: set[tuple[str, str]] = set()
            for entry in projections.memory_entries.values():
                reason = entry.get("last_status_reason", "")
                if reason.startswith("dedup:dismissed"):
                    # Extract paired ID from reason string
                    for fp in flagged:
                        eid = entry.get("id", "")
                        if eid == fp["entry_a"] or eid == fp["entry_b"]:
                            dismissed_pairs.add((fp["entry_a"], fp["entry_b"]))

            from formicos.core.events import MemoryEntryStatusChanged  # noqa: PLC0415

            for pair in flagged:
                pair_key = (pair["entry_a"], pair["entry_b"])
                if pair_key in dismissed_pairs:
                    continue

                ea = projections.memory_entries.get(pair["entry_a"])
                eb = projections.memory_entries.get(pair["entry_b"])
                if ea is None or eb is None:
                    continue

                prompt = (
                    "Do these two knowledge entries describe the same thing? "
                    "Answer YES or NO only.\n\n"
                    f"Entry A: {ea.get('title', '')} — "
                    f"{ea.get('summary', '') or ea.get('content', '')[:200]}\n\n"
                    f"Entry B: {eb.get('title', '')} — "
                    f"{eb.get('summary', '') or eb.get('content', '')[:200]}"
                )

                try:
                    llm_result = await asyncio.wait_for(
                        llm_router.complete(
                            model="gemini/gemini-2.5-flash",
                            messages=[{"role": "user", "content": prompt}],
                            temperature=0.0,
                            max_tokens=10,
                        ),
                        timeout=15.0,
                    )
                    answer = llm_result.content.strip().upper()
                except Exception:  # noqa: BLE001
                    log.debug(
                        "dedup.llm_timeout",
                        entry_a=pair["entry_a"],
                        entry_b=pair["entry_b"],
                    )
                    continue

                if answer.startswith("YES"):
                    # Confirm merge: merge lower-confidence into higher
                    survivor, absorbed = (
                        (ea, eb)
                        if ea.get("confidence", 0) >= eb.get("confidence", 0)
                        else (eb, ea)
                    )
                    from formicos.core.events import MemoryEntryMerged  # noqa: PLC0415

                    target_content = survivor.get("content", "")
                    source_content = absorbed.get("content", "")
                    m_content = llm_result.content.strip() or (
                        source_content
                        if len(source_content) > len(target_content) * 1.2
                        else target_content
                    )
                    target_domains = survivor.get("domains", [])
                    source_domains = absorbed.get("domains", [])
                    m_domains = sorted(
                        set(target_domains) | set(source_domains),
                    )
                    existing_from: list[str] = survivor.get(
                        "merged_from", [],
                    )
                    m_from = existing_from + [absorbed.get("id", "")]

                    await runtime.emit_and_broadcast(MemoryEntryMerged(
                        seq=0,
                        timestamp=datetime.now(UTC),
                        address=survivor.get("workspace_id", ""),
                        target_id=survivor.get("id", ""),
                        source_id=absorbed.get("id", ""),
                        merged_content=m_content,
                        merged_domains=m_domains,
                        merged_from=m_from,
                        content_strategy="llm_selected",
                        similarity=pair["similarity"],
                        merge_source="dedup",
                        workspace_id=survivor.get("workspace_id", ""),
                    ))
                    llm_confirmed += 1
                else:
                    # Dismiss: emit status-unchanged event as durable marker
                    for entry_dict in (ea, eb):
                        other_id = (
                            pair["entry_b"]
                            if entry_dict.get("id") == pair["entry_a"]
                            else pair["entry_a"]
                        )
                        cur_status = entry_dict.get("status", "verified")
                        await runtime.emit_and_broadcast(
                            MemoryEntryStatusChanged(
                                seq=0,
                                timestamp=datetime.now(UTC),
                                address=entry_dict.get("workspace_id", ""),
                                entry_id=entry_dict.get("id", ""),
                                old_status=cur_status,
                                new_status=cur_status,
                                reason=f"dedup:dismissed (pair with {other_id})",
                                workspace_id=entry_dict.get(
                                    "workspace_id", "",
                                ),
                            ),
                        )
                    llm_dismissed += 1

        report = {
            "merged": merged_count,
            "llm_confirmed": llm_confirmed,
            "llm_dismissed": llm_dismissed,
            "flagged_for_review": len(flagged),
            "flagged_pairs": flagged,
        }
        return (
            f"Dedup complete: {merged_count} auto-merged, "
            f"{llm_confirmed} LLM-confirmed, "
            f"{llm_dismissed} LLM-dismissed, "
            f"{len(flagged)} flagged total.\n"
            f"{json.dumps(report, indent=2)}"
        )

    return _handle_dedup


def make_stale_handler(runtime: Runtime):  # noqa: ANN201
    """Factory: returns an async callable for stale sweep."""

    async def _handle_stale(query_text: str, ctx: dict[str, Any]) -> str:
        projections = runtime.projections
        now = datetime.now(UTC)
        stale_days = 90

        # Build set of recently-accessed entry IDs from KnowledgeAccessRecorded
        accessed_ids: set[str] = set()
        for colony in projections.colonies.values():
            for trace in getattr(colony, "knowledge_accesses", []):
                for item in trace.get("items", []):
                    accessed_ids.add(item.get("id", ""))

        stale_count = 0

        for entry_id, entry in list(projections.memory_entries.items()):
            if entry.get("status") in ("rejected", "stale"):
                continue
            try:
                created = datetime.fromisoformat(entry.get("created_at", ""))
            except (ValueError, TypeError):
                continue
            age = now - created

            # Wave 33 A3: prediction error as additional staleness signal
            prediction_errors = entry.get("prediction_error_count", 0)
            access_count = sum(
                1 for colony in projections.colonies.values()
                for trace in getattr(colony, "knowledge_accesses", [])
                for item in trace.get("items", [])
                if item.get("id") == entry_id
            )
            is_stale_by_age = entry_id not in accessed_ids and age > timedelta(days=stale_days)
            is_stale_by_prediction = prediction_errors >= 5 and access_count < 3

            if is_stale_by_age or is_stale_by_prediction:
                reason_detail = (
                    f"prediction_error: {prediction_errors} errors, {access_count} accesses"
                    if is_stale_by_prediction and not is_stale_by_age
                    else f"stale_sweep: not accessed in {age.days} days"
                )
                from formicos.core.events import MemoryEntryStatusChanged  # noqa: PLC0415

                await runtime.emit_and_broadcast(MemoryEntryStatusChanged(
                    seq=0,
                    timestamp=now,
                    address=entry.get("workspace_id", ""),
                    entry_id=entry_id,
                    old_status=entry.get("status", "verified"),
                    new_status="stale",
                    reason=reason_detail,
                    workspace_id=entry.get("workspace_id", ""),
                ))
                stale_count += 1

        # NOTE: Confidence decay (gradual penalty for aging entries) is
        # deferred to Wave 30 where Bayesian confidence (Beta distribution)
        # replaces the current scalar field.  Decaying confidence here
        # would mutate projection state without an event (hard constraint #7).

        return f"Stale sweep: {stale_count} entries transitioned to stale"

    return _handle_stale


# Wave 33 A5: co-occurrence weight decay
_COOCCURRENCE_GAMMA_PER_DAY: float = 0.995  # half-life ~138 days
_COOCCURRENCE_PRUNE_THRESHOLD: float = 0.1


def make_cooccurrence_decay_handler(runtime: Runtime):  # noqa: ANN201
    """Factory: returns an async callable for co-occurrence weight decay."""

    async def _handle_cooccurrence_decay(query_text: str, ctx: dict[str, Any]) -> str:
        now = datetime.now(UTC)
        pruned = 0
        decayed = 0
        to_prune: list[tuple[str, str]] = []
        for key, entry in runtime.projections.cooccurrence_weights.items():
            if not entry.last_reinforced:
                to_prune.append(key)
                continue
            try:
                last = datetime.fromisoformat(entry.last_reinforced)
            except (ValueError, TypeError):
                to_prune.append(key)
                continue
            elapsed_days = max(
                (now - last).total_seconds() / 86400.0, 0.0,
            )
            gamma_eff = _COOCCURRENCE_GAMMA_PER_DAY ** elapsed_days
            entry.weight *= gamma_eff
            entry.last_reinforced = now.isoformat()
            decayed += 1
            if entry.weight < _COOCCURRENCE_PRUNE_THRESHOLD:
                to_prune.append(key)
        for key in to_prune:
            runtime.projections.cooccurrence_weights.pop(key, None)
            pruned += 1

        # Wave 34.5: identify distillation candidates after pruning
        candidates = _find_distillation_candidates(runtime)
        runtime.projections.distillation_candidates = candidates

        return (
            f"Co-occurrence decay: {decayed} pairs decayed, {pruned} pruned, "
            f"{len(candidates)} distillation candidates"
        )

    return _handle_cooccurrence_decay


def _find_distillation_candidates(runtime: Runtime) -> list[list[str]]:
    """Find co-occurrence clusters dense enough for knowledge distillation.

    A cluster is a connected component with edge weight > 2.0.
    Candidate when: >= 5 entries and average weight > 3.0.
    """
    weights = runtime.projections.cooccurrence_weights
    adj: dict[str, set[str]] = {}
    edge_weights: dict[tuple[str, str], float] = {}

    for (a, b), entry in weights.items():
        w = entry.weight
        if w <= 2.0:
            continue
        adj.setdefault(a, set()).add(b)
        adj.setdefault(b, set()).add(a)
        edge_weights[(min(a, b), max(a, b))] = w

    # BFS connected components
    visited: set[str] = set()
    candidates: list[list[str]] = []
    for node in adj:
        if node in visited:
            continue
        cluster: set[str] = set()
        queue = [node]
        while queue:
            current = queue.pop()
            if current in visited:
                continue
            visited.add(current)
            cluster.add(current)
            queue.extend(adj.get(current, set()) - visited)
        if len(cluster) < 5:
            continue
        # Average weight of edges within cluster
        cluster_edges = [
            w for (a, b), w in edge_weights.items()
            if a in cluster and b in cluster
        ]
        if cluster_edges and sum(cluster_edges) / len(cluster_edges) > 3.0:
            candidates.append(sorted(cluster))
    return candidates


async def _compute_similarity(
    memory_store: Any,  # noqa: ANN401
    entry_a: dict[str, Any],
    entry_b: dict[str, Any],
) -> float:
    """Compute cosine similarity between two entries via vector search.

    memory_store.search() returns Qdrant hit.score which is cosine
    *similarity* (higher = more similar), NOT distance.  Use directly.
    """
    content_a = entry_a.get("content_preview", "") or entry_a.get("summary", "")
    if not content_a:
        return 0.0
    results = await memory_store.search(
        query=content_a, top_k=10,
        workspace_id=entry_a.get("workspace_id", ""),
    )
    for hit in results:
        if hit.get("id") == entry_b.get("id"):
            return float(hit.get("score", 0.0))
    return 0.0


def make_contradiction_handler(runtime: Runtime):  # noqa: ANN201
    """Factory: returns an async callable for contradiction detection (Wave 30 S14).

    Wave 41 A3: delegates detection to the shared seam in
    conflict_resolution.detect_contradictions instead of carrying
    its own inline Jaccard + polarity logic.
    """

    async def _handle_contradiction(query_text: str, ctx: dict[str, Any]) -> str:
        from formicos.surface.conflict_resolution import (  # noqa: PLC0415
            PairRelation,
            detect_contradictions,
        )

        projections = runtime.projections

        # Build entry dict keyed by id for the shared detector
        entry_dict: dict[str, dict[str, Any]] = {
            e.get("id", ""): e
            for e in projections.memory_entries.values()
            if e.get("id")
            and e.get("status") == "verified"
            and e.get("polarity", "neutral") not in ("", "neutral")
            and e.get("domains")
        }

        all_pairs = detect_contradictions(entry_dict)

        contradictions: list[dict[str, Any]] = []
        for pair in all_pairs:
            if pair.relation != PairRelation.contradiction:
                continue
            ea = entry_dict.get(pair.entry_a_id, {})
            eb = entry_dict.get(pair.entry_b_id, {})
            domains_a = set(ea.get("domains", []))
            domains_b = set(eb.get("domains", []))
            contradictions.append({
                "entry_a": pair.entry_a_id,
                "entry_b": pair.entry_b_id,
                "relation": pair.relation.value,
                "shared_domains": sorted(domains_a & domains_b),
                "jaccard": round(pair.domain_overlap, 3),
                "polarity_a": ea.get("polarity", ""),
                "polarity_b": eb.get("polarity", ""),
                "confidence_a": ea.get("confidence", 0.5),
                "confidence_b": eb.get("confidence", 0.5),
            })

        report = {
            "contradictions_found": len(contradictions),
            "pairs": contradictions,
        }
        return (
            f"Contradiction scan: {len(contradictions)} pair(s) flagged.\n"
            f"{json.dumps(report, indent=2)}"
        )

    return _handle_contradiction


def make_confidence_reset_handler(runtime: Runtime):  # noqa: ANN201
    """Factory: confidence reset for stuck entries.

    Resets entries with 50+ observations beyond the prior and a posterior
    mean between 0.35 and 0.65 back to the prior Beta(5.0, 5.0).
    Manual-only — not included in the scheduled maintenance loop.
    """

    async def _handle_confidence_reset(query_text: str, ctx: dict[str, Any]) -> str:
        from formicos.core.events import MemoryConfidenceUpdated  # noqa: PLC0415

        projections = runtime.projections
        threshold = 50  # total observations above prior
        reset_count = 0

        for entry_id, entry in list(projections.memory_entries.items()):
            alpha = float(entry.get("conf_alpha", 5.0))
            beta_val = float(entry.get("conf_beta", 5.0))
            total_obs = (alpha + beta_val) - 10.0  # subtract prior (5.0 + 5.0)
            mean = alpha / (alpha + beta_val) if (alpha + beta_val) > 0 else 0.5

            if total_obs >= threshold and 0.35 <= mean <= 0.65:
                ws_id = entry.get("workspace_id", "")
                th_id = entry.get("thread_id", "")
                await runtime.emit_and_broadcast(
                    MemoryConfidenceUpdated(
                        seq=0,
                        timestamp=datetime.now(UTC),
                        address=f"{ws_id}/{th_id}" if ws_id else "system",
                        entry_id=entry_id,
                        colony_id="",
                        colony_succeeded=True,
                        old_alpha=alpha,
                        old_beta=beta_val,
                        new_alpha=5.0,
                        new_beta=5.0,
                        new_confidence=0.5,
                        workspace_id=ws_id,
                        thread_id=th_id,
                        reason="manual_reset",
                    ),
                )
                reset_count += 1

        return f"Reset {reset_count} entries to prior (5.0/5.0)"

    return _handle_confidence_reset


def make_credential_sweep_handler(runtime: Runtime):  # noqa: ANN201
    """Factory: retroactive credential sweep using detect-secrets (Wave 33 B3).

    Re-scans existing memory entries with the current detect-secrets plugin
    set. Entries with embedded credentials are rejected. A version counter
    ensures entries are only re-scanned when the plugin set changes.
    """

    async def _handle_credential_sweep(query_text: str, ctx: dict[str, Any]) -> str:
        from formicos.surface.credential_scan import scan_mixed_content  # noqa: PLC0415

        current_version = 1  # Bump when adding new plugins
        swept = 0
        flagged = 0

        for entry_id, entry in list(runtime.projections.memory_entries.items()):
            if entry.get("status") == "rejected":
                continue
            scanned_version = entry.get("credential_scan_version", 0)
            if scanned_version >= current_version:
                continue

            content = entry.get("content", "") or entry.get("summary", "")
            title = entry.get("title", "")
            text = f"{title}\n{content}" if title else content

            findings = scan_mixed_content(text)
            entry["credential_scan_version"] = current_version
            swept += 1

            if findings:
                from formicos.core.events import MemoryEntryStatusChanged  # noqa: PLC0415

                await runtime.emit_and_broadcast(
                    MemoryEntryStatusChanged(
                        seq=0,
                        timestamp=datetime.now(UTC),
                        address=entry.get("workspace_id", ""),
                        entry_id=entry_id,
                        old_status=entry.get("status", "candidate"),
                        new_status="rejected",
                        reason=f"credential_sweep:v{current_version}:{findings[0]['type']}",
                        workspace_id=entry.get("workspace_id", ""),
                    ),
                )
                flagged += 1

        return f"Credential sweep: {swept} entries scanned, {flagged} flagged and rejected"

    return _handle_credential_sweep


def make_curation_handler(runtime: Runtime):  # noqa: ANN201
    """Factory: periodic knowledge curation (Wave 59).

    Selects popular-but-unexamined entries (access >= 5, confidence < 0.65)
    and asks the archivist to refine them.
    """

    async def _handle_curation(query_text: str, ctx: dict[str, Any]) -> str:
        workspace_id = ctx.get("workspace_id", "")
        if not workspace_id:
            return "no workspace_id in context"

        # Select candidates: popular-but-unexamined
        candidates: list[dict[str, Any]] = []
        usage = getattr(runtime.projections, "knowledge_entry_usage", {})
        for eid, entry in runtime.projections.memory_entries.items():
            if entry.get("status") != "verified":
                continue
            if entry.get("workspace_id", "") != workspace_id:
                continue
            entry_usage = usage.get(eid, {})
            access_count = int(entry_usage.get("count", 0))
            if access_count < 5:
                continue
            alpha = float(entry.get("conf_alpha", 5.0))
            beta_val = float(entry.get("conf_beta", 5.0))
            denom = alpha + beta_val
            if denom <= 0:
                continue
            confidence = alpha / denom
            if confidence >= 0.65:
                continue
            candidates.append({
                **entry,
                "access_count": access_count,
                "confidence": confidence,
            })
            if len(candidates) >= 10:
                break

        if not candidates:
            return "no curation candidates"

        # Build prompt
        lines = [
            "You are reviewing knowledge entries that are frequently accessed "
            "but may need improvement.\n\nENTRIES TO REVIEW:",
        ]
        for c in candidates:
            cid = c.get("id", "?")
            ctitle = c.get("title", "untitled")
            cconf = float(c.get("confidence", 0.5))
            caccess = int(c.get("access_count", 0))
            ccontent = str(c.get("content", ""))
            cdomains = ", ".join(c.get("domains", []))
            lines.append(
                f'- [{cid}] "{ctitle}" (conf: {cconf:.2f}, accessed: {caccess}x)\n'
                f"  Content: {ccontent}\n"
                f"  Domains: {cdomains}"
            )
        lines.append(
            "\nFor each entry, decide:\n"
            "- REFINE: Improve the content to be more precise, actionable, or correct.\n"
            '  Provide "entry_id" + "new_content" (+ optional "new_title")\n'
            "- NOOP: Entry is already adequate. No change needed.\n\n"
            'Return JSON: {"actions": [...]}\n\n'
            "Be conservative. Only refine when you can make the entry genuinely better.\n"
            "Do not add speculative information. Do not generalize away specific details."
        )
        prompt = "\n".join(lines)

        # Use resolve_model for proper fallback chain.
        # Do NOT copy the dedup handler's hardcoded "gemini/gemini-2.5-flash".
        model = runtime.resolve_model("archivist", workspace_id)
        try:
            response = await runtime.llm_router.complete(
                model=model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You review knowledge entries for quality improvement. "
                            "Return valid JSON only."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.0,
                max_tokens=2048,
            )
        except Exception:  # noqa: BLE001
            log.warning("curation_maintenance.llm_failed", workspace_id=workspace_id)
            return "archivist call failed"

        # Parse response
        try:
            parsed = json.loads(response.content)
        except json.JSONDecodeError:
            try:
                import json_repair  # noqa: PLC0415

                parsed = json_repair.loads(response.content)
            except Exception:  # noqa: BLE001
                log.warning("curation_maintenance.parse_failed", workspace_id=workspace_id)
                return "response parse failed"

        # Dispatch REFINE actions only
        from formicos.core.events import MemoryEntryRefined  # noqa: PLC0415

        refined_count = 0
        for action in parsed.get("actions", []):
            action_type = action.get("type", "").upper()
            if action_type != "REFINE":
                if action_type not in ("NOOP", ""):
                    log.warning(
                        "curation_maintenance.unexpected_action",
                        action_type=action_type,
                    )
                continue

            rid = action.get("entry_id", "")
            existing = runtime.projections.memory_entries.get(rid)
            if existing is None:
                log.warning("curation_maintenance.missing_entry", entry_id=rid)
                continue
            new_content = action.get("new_content", "").strip()
            if len(new_content) < 20:
                continue
            old_content = existing.get("content", "")
            if new_content == old_content:
                continue

            address = f"{workspace_id}/_maintenance/{rid}"
            await runtime.emit_and_broadcast(MemoryEntryRefined(
                seq=0,
                timestamp=datetime.now(UTC),
                address=address,
                entry_id=rid,
                workspace_id=workspace_id,
                old_content=old_content,
                new_content=new_content,
                new_title=action.get("new_title", ""),
                refinement_source="maintenance",
                source_colony_id="",
            ))
            refined_count += 1

        return (
            f"curation complete: {refined_count} entries refined, "
            f"{len(candidates)} reviewed"
        )

    return _handle_curation


__all__ = [
    "make_cooccurrence_decay_handler",
    "make_confidence_reset_handler",
    "make_contradiction_handler",
    "make_credential_sweep_handler",
    "make_curation_handler",
    "make_dedup_handler",
    "make_stale_handler",
]
