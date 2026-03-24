"""Context assembly and token-budget management for colony rounds.

Implements algorithms.md §2 — tiered context assembly with per-source caps,
compaction, edge-preserving truncation, and confidence-weighted skill retrieval.
"""

from __future__ import annotations

import os
import re
import time as _time_mod
from datetime import datetime
from typing import Any

import structlog
from pydantic import BaseModel, ConfigDict

from formicos.core.ports import VectorPort
from formicos.core.types import (
    AgentConfig,
    ColonyContext,
    KnowledgeAccessItem,
    LLMMessage,
    VectorSearchHit,
)

log = structlog.get_logger()

# ---------------------------------------------------------------------------
# Ephemeral retrieval timing (Wave 13 F3 — operator diagnostics)
# ---------------------------------------------------------------------------
# Updated after each RetrievalPipeline.search() or direct vector search.
# Read by the diagnostics endpoint in surface/app.py.  Not persisted.

_last_retrieval_timing: dict[str, float] = {
    "graph_ms": 0.0,
    "vector_ms": 0.0,
    "total_ms": 0.0,
}


def get_last_retrieval_timing() -> dict[str, float]:
    """Return the most recent retrieval pipeline timing snapshot."""
    return dict(_last_retrieval_timing)


# Wave 55.5: minimum vector similarity for knowledge injection.
# Entries below this threshold are retrieved but not injected into context.
# Calibrated for Qwen3-Embedding-0.6B: irrelevant entries score 0.34-0.41,
# relevant entries score 0.50-0.70 (see retrieval_quality_audit.md).
_MIN_KNOWLEDGE_SIMILARITY: float = float(
    os.environ.get("FORMICOS_KNOWLEDGE_MIN_SIMILARITY", "0.50")
)

# Wave 58: Specificity gate -- skip knowledge injection for general tasks.
# When enabled, the gate checks for project-specific signals in the task
# description and strong semantic matches in the retrieved pool.
_SPECIFICITY_GATE_ENABLED: bool = (
    os.environ.get("FORMICOS_SPECIFICITY_GATE", "1") == "1"
)

_PROJECT_SIGNALS: frozenset[str] = frozenset({
    "our", "existing", "internal", "custom", "legacy", "current",
    "workspace", "codebase", "repo", "project", "module",
})

# Default skill collection name (Wave 13: skill_bank_v2 with hybrid search).
# Reads the actual name from the vector port's ``_default_collection`` attribute
# at call time so the config stays consistent end-to-end.
_DEFAULT_SKILL_COLLECTION = "skill_bank_v2"


def _skill_collection(vector_port: VectorPort | None) -> str:
    """Resolve the live skill collection name from the vector port."""
    return str(getattr(vector_port, "_default_collection", _DEFAULT_SKILL_COLLECTION))


# ---------------------------------------------------------------------------
# Tier budget configuration (ADR-008)
# ---------------------------------------------------------------------------


class TierBudgets(BaseModel):
    """Per-tier token caps for context assembly."""

    model_config = ConfigDict(frozen=True)

    goal: int = 500
    routed_outputs: int = 1500
    max_per_source: int = 500
    merge_summaries: int = 500
    prev_round_summary: int = 500
    skill_bank: int = 800
    compaction_threshold: int = 500


DEFAULT_TIER_BUDGETS = TierBudgets()


class ContextResult(BaseModel):
    """Return type for assemble_context — messages plus retrieval metadata."""

    model_config = ConfigDict(frozen=True)

    messages: list[LLMMessage]
    retrieved_skill_ids: list[str] = []
    knowledge_items_used: list[KnowledgeAccessItem] = []  # Wave 28


# ---------------------------------------------------------------------------
# Graph-augmented retrieval (algorithms.md §5, Wave 13 B-T3)
# ---------------------------------------------------------------------------


class RetrievalPipeline:
    """Orchestrates hybrid vector search + KG graph traversal.

    Injected from surface/app.py with both vector_port and kg_adapter.
    The KG adapter is duck-typed (no core port) — accepts any object with
    ``search_entities`` and ``get_neighbors`` async methods.
    """

    def __init__(
        self,
        vector_port: VectorPort,
        kg_adapter: Any,  # noqa: ANN401
    ) -> None:
        self._vectors = vector_port
        self._kg = kg_adapter

    async def search(
        self,
        workspace_id: str,
        query: str,
        top_k: int = 8,
    ) -> tuple[list[VectorSearchHit], list[dict[str, Any]]]:
        """Three-stage retrieval: entity extraction, parallel search, merge.

        Returns (vector_hits, kg_triples) so the caller can score and format.
        """
        t_total = _time_mod.perf_counter()

        # Stage 1 + 2a: Entity extraction from KG
        kg_triples: list[dict[str, Any]] = []
        t_graph = _time_mod.perf_counter()
        try:
            known_entities = await self._kg.search_entities(
                text=query, workspace_id=workspace_id,
            )
            # Stage 2b: 1-hop BFS for matched entities (limit to top 3)
            for entity in known_entities[:3]:
                neighbors = await self._kg.get_neighbors(
                    entity_id=entity["id"],
                    depth=1,
                    workspace_id=workspace_id,
                )
                kg_triples.extend(neighbors)
        except Exception:
            log.debug("kg_retrieval_failed", workspace_id=workspace_id)
        graph_ms = (_time_mod.perf_counter() - t_graph) * 1000

        # Stage 2a: Hybrid vector search (adapter-internal dense+BM25+RRF)
        t_vector = _time_mod.perf_counter()
        vector_hits = await self._vectors.search(
            collection=_skill_collection(self._vectors),
            query=query,
            top_k=top_k,
        )
        vector_ms = (_time_mod.perf_counter() - t_vector) * 1000

        total_ms = (_time_mod.perf_counter() - t_total) * 1000

        # Update ephemeral timing for operator diagnostics
        _last_retrieval_timing["graph_ms"] = round(graph_ms, 2)
        _last_retrieval_timing["vector_ms"] = round(vector_ms, 2)
        _last_retrieval_timing["total_ms"] = round(total_ms, 2)

        log.info(
            "retrieval_pipeline.timing",
            graph_ms=round(graph_ms, 2),
            vector_ms=round(vector_ms, 2),
            total_ms=round(total_ms, 2),
            vector_hits=len(vector_hits),
            kg_triples=len(kg_triples),
            workspace_id=workspace_id,
        )

        return vector_hits, kg_triples


# ---------------------------------------------------------------------------
# Freshness decay (algorithms.md §2.2)
# ---------------------------------------------------------------------------


def _compute_freshness(extracted_at: str) -> float:
    """Exponential decay with 90-day half-life. Returns value in [0, 1]."""
    if not extracted_at:
        return 1.0
    try:
        ext_dt = datetime.fromisoformat(extracted_at)
        age_days = (_time_mod.time() - ext_dt.timestamp()) / 86400.0
    except (ValueError, TypeError):
        return 1.0
    return 2.0 ** (-age_days / 90.0)


# ---------------------------------------------------------------------------
# Token estimation
# ---------------------------------------------------------------------------


def estimate_tokens(text: str) -> int:
    """Cheap token estimate: 1 token ≈ 4 characters."""
    return len(text) // 4


# ---------------------------------------------------------------------------
# Truncation helpers
# ---------------------------------------------------------------------------


def _truncate(text: str, budget_tokens: int) -> str:
    """Simple character-based truncation to fit a token budget."""
    if estimate_tokens(text) <= budget_tokens:
        return text
    return text[: budget_tokens * 4]


def _truncate_preserve_edges(text: str, budget_tokens: int) -> str:
    """Truncate keeping first and last portions (edges have highest info density)."""
    if estimate_tokens(text) <= budget_tokens:
        return text
    char_budget = budget_tokens * 4
    half = char_budget // 2
    return text[:half] + "\n[... truncated ...]\n" + text[-half:]


# ---------------------------------------------------------------------------
# Compaction (ADR-008, algorithms.md §2.3)
# ---------------------------------------------------------------------------


def _split_sentences(text: str) -> list[str]:
    """Simple sentence splitter. Not perfect, but fast and deterministic."""
    parts = re.split(r"(?<=[.!?])\s+|\n+", text.strip())
    return [p.strip() for p in parts if p.strip()]


def _compact_summary(text: str, goal: str, budget_tokens: int) -> str:
    """Compress text to budget by keeping goal-relevant sentences."""
    sentences = _split_sentences(text)
    if not sentences:
        return text[: budget_tokens * 4]

    goal_words = set(goal.lower().split())

    scored: list[tuple[int, float, str]] = []
    for i, sent in enumerate(sentences):
        sent_words = set(sent.lower().split())
        overlap = len(goal_words & sent_words)
        position_bonus = 0.5 if (i == 0 or i == len(sentences) - 1) else 0.0
        score = overlap + position_bonus
        scored.append((i, score, sent))

    scored.sort(key=lambda x: -x[1])
    selected: list[tuple[int, str]] = []
    used_tokens = 0
    for idx, _score, sent in scored:
        sent_tokens = estimate_tokens(sent)
        if used_tokens + sent_tokens > budget_tokens:
            continue
        selected.append((idx, sent))
        used_tokens += sent_tokens

    selected.sort(key=lambda x: x[0])
    return " ".join(s for _, s in selected)


# ---------------------------------------------------------------------------
# Legacy trim (kept for backward compat with callers using budget_tokens)
# ---------------------------------------------------------------------------


def trim_to_budget(
    messages: list[LLMMessage],
    budget_tokens: int,
) -> list[LLMMessage]:
    """Trim lowest-priority messages (from end) until within budget.

    Always keeps at least the first message (system prompt).
    """
    total = sum(estimate_tokens(m["content"]) for m in messages)
    if total <= budget_tokens:
        return messages
    result = list(messages)
    while total > budget_tokens and len(result) > 1:
        removed = result.pop()
        total -= estimate_tokens(removed["content"])
    return result


# ---------------------------------------------------------------------------
# Budget regime injection (ADR-022, algorithms.md §3)
# ---------------------------------------------------------------------------


class BudgetRegime:
    """Budget regime thresholds and advice for agent prompt injection."""

    HIGH = "HIGH"      # ≥70% remaining
    MEDIUM = "MEDIUM"  # 30–70% remaining
    LOW = "LOW"        # 10–30% remaining
    CRITICAL = "CRITICAL"  # <10% remaining

    _ADVICE = {
        "HIGH": "Explore freely when helpful.",
        "MEDIUM": "Stay focused on your strongest path.",
        "LOW": "Wrap up current work. Reduce exploration.",
        "CRITICAL": "Answer with what you have. No new exploration.",
    }

    @staticmethod
    def classify(remaining_pct: float) -> str:
        """Classify budget percentage into a regime."""
        if remaining_pct >= 70.0:
            return BudgetRegime.HIGH
        if remaining_pct >= 30.0:
            return BudgetRegime.MEDIUM
        if remaining_pct >= 10.0:
            return BudgetRegime.LOW
        return BudgetRegime.CRITICAL

    @staticmethod
    def advice(regime: str) -> str:
        return BudgetRegime._ADVICE.get(regime, "")


def build_budget_block(
    budget_limit: float,
    total_cost: float,
    iteration: int,
    max_iterations: int,
    round_number: int,
    max_rounds: int,
    stall_count: int = 0,  # Wave 54
    convergence_progress: float = 0.0,  # Wave 54
    local_tokens: int = 0,  # Wave 60
) -> str:
    """Build the budget status block injected before each LLM call (ADR-022).

    Returns a short text block with remaining budget %, iteration count,
    round progress, regime-specific advice, and convergence status (Wave 54).
    Wave 60: split display — API budget + local token count.
    """
    remaining = max(budget_limit - total_cost, 0.0)
    remaining_pct = (remaining / budget_limit * 100.0) if budget_limit > 0 else 0.0
    regime = BudgetRegime.classify(remaining_pct)
    advice = BudgetRegime.advice(regime)

    # Wave 60: split cost display — API budget + local tokens
    block = (
        f"[API Budget: ${remaining:.2f} remaining ({remaining_pct:.0f}%) — {regime}]\n"
    )
    if local_tokens > 0:
        if local_tokens >= 1_000_000:
            local_str = f"{local_tokens / 1_000_000:.1f}M"
        elif local_tokens >= 1_000:
            local_str = f"{local_tokens / 1_000:.0f}K"
        else:
            local_str = str(local_tokens)
        block += f"[Local: {local_str} tokens processed]\n"
    block += (
        f"[Iteration {iteration}/{max_iterations} · Round {round_number}/{max_rounds}]\n"
        f"{advice}"
    )

    # Wave 54: convergence status — behavioral nudge for stalling agents
    if round_number >= max_rounds - 1:
        block += "\nSTATUS: FINAL ROUND -- deliver your best output immediately."
    elif stall_count >= 3:
        block += "\nSTATUS: STALLED -- you must change approach. Write output now."
    elif stall_count >= 1:
        block += "\nSTATUS: SLOW -- focus on productive tool calls."
    else:
        block += "\nSTATUS: ON TRACK"

    return block


# ---------------------------------------------------------------------------
# Wave 58: Specificity gate
# ---------------------------------------------------------------------------


def _should_inject_knowledge(
    round_goal: str,
    knowledge_items: list[dict[str, Any]],
) -> bool:
    """Specificity gate: skip injection when knowledge won't help.

    Returns True (inject) when:
    1. Gate is disabled via env var, OR
    2. Any retrieved entry is a trajectory (always valuable), OR
    3. Task contains project-specific signals, OR
    4. Top retrieved entry has raw similarity >= 0.55 (strong match exists)

    Returns False (skip) when none of the above hold.
    """
    if not _SPECIFICITY_GATE_ENABLED:
        return True

    # Always inject when trajectory entries are available -- they are
    # action sequences, not redundant prose.
    for item in knowledge_items[:5]:
        if item.get("sub_type") == "trajectory":
            return True

    # Check for project-specific language in the task description.
    words = set(round_goal.lower().split())
    if words & _PROJECT_SIGNALS:
        return True

    # Check whether the pool contains a genuinely relevant entry.
    # 0.55 is above the per-entry threshold (0.50) to avoid redundancy.
    if knowledge_items:
        top_sim = max(
            float(item.get("similarity", item.get("score", 0.0)))
            for item in knowledge_items[:5]
        )
        if top_sim >= 0.55:
            return True

    log.debug(
        "context.specificity_gate_skip",
        round_goal=round_goal[:80],
        top_similarity=round(
            max(
                (float(i.get("similarity", i.get("score", 0.0))) for i in knowledge_items[:5]),
                default=0.0,
            ),
            3,
        ),
    )
    return False


# ---------------------------------------------------------------------------
# Main assembly (algorithms.md §2.2)
# ---------------------------------------------------------------------------


async def assemble_context(
    agent: AgentConfig,
    colony_context: ColonyContext,
    round_goal: str,
    routed_outputs: dict[str, str],
    merged_summaries: list[str],
    vector_port: VectorPort | None,
    budget_tokens: int = 4000,
    tier_budgets: TierBudgets | None = None,
    total_colonies: int = 0,
    ucb_exploration_weight: float = 0.1,
    kg_adapter: Any = None,  # noqa: ANN401
    input_sources: list[dict[str, Any]] | None = None,
    knowledge_items: list[dict[str, Any]] | None = None,  # Wave 28
    operational_playbook: str | None = None,  # Wave 54
) -> ContextResult:
    """Build message list with per-tier budget enforcement.

    Returns a ContextResult with messages and retrieved skill IDs.

    Assembly order (optimized for attention — important at edges):
      1. System prompt                 (position 1 — highest attention)
      2. Round goal                    (position 2 — task must be salient)
      2b. Input sources (ADR-033)      (high priority — chained colony context)
      3. Routed agent outputs          (middle — acceptable attention zone)
      4. Merge summaries               (middle)
      5. Previous round summary        (near end — decent recall)
      6. Skill bank results            (last — good recall, lowest trim priority)
    """
    budgets = tier_budgets or DEFAULT_TIER_BUDGETS
    messages: list[LLMMessage] = []
    retrieved_skill_ids: list[str] = []

    # 1. System prompt (always present, not budget-limited)
    messages.append({"role": "system", "content": agent.recipe.system_prompt})

    # 2. Round goal (capped)
    goal_text = _truncate(f"Round goal: {round_goal}", budgets.goal)
    messages.append({"role": "user", "content": goal_text})

    # 2.5. Operational playbook (Wave 54) — task-class procedural guidance
    if operational_playbook:
        playbook_text = _truncate(operational_playbook, 400)  # ~250 tokens
        messages.append({"role": "system", "content": playbook_text})

    # 2.6. Common-mistakes anti-patterns (Wave 56.5 A) — always on, caste-aware
    from formicos.engine.playbook_loader import load_common_mistakes  # noqa: PLC0415

    mistakes_block = load_common_mistakes(agent.caste)
    if mistakes_block:
        messages.append({"role": "system", "content": mistakes_block})

    # 2a. Structural context (Wave 47) — injected when available
    if colony_context.structural_context:
        struct_text = _truncate(
            f"[Workspace Structure]\n{colony_context.structural_context}",
            budgets.routed_outputs,
        )
        messages.append({"role": "user", "content": struct_text})

    # 2b. Input sources — chained colony context (ADR-033)
    if input_sources:
        for src in input_sources:
            summary = src.get("summary", "")
            if summary:
                source_id = src.get("colony_id", "unknown")
                src_text = _truncate(
                    f"[Context from prior colony {source_id}]:\n{summary}",
                    budgets.max_per_source,
                )
                messages.append({"role": "user", "content": src_text})
            # Wave 25: inject artifact metadata from chained colony
            artifacts: list[dict[str, Any]] = src.get("artifacts", [])
            if artifacts:
                source_id = src.get("colony_id", "unknown")
                lines = [f"[Artifacts from prior colony {source_id}]:"]
                for art in artifacts:
                    name = art.get("name", "unnamed")
                    atype = art.get("artifact_type", "generic")
                    preview = art.get("content", "")[:200]
                    lines.append(f"- {name} ({atype}): {preview}")
                art_text = _truncate("\n".join(lines), budgets.max_per_source)
                messages.append({"role": "user", "content": art_text})

    # Tier 2c: Unified system knowledge (Wave 28)
    skip_legacy_skills = False
    knowledge_access_items: list[KnowledgeAccessItem] = []

    # Wave 58.5: domain-boundary filter — keep entries whose primary_domain
    # matches the colony's task_class, or entries with no domain tag / generic.
    _task_class = colony_context.task_class
    if knowledge_items and _task_class and _task_class != "generic":
        knowledge_items = [
            item for item in knowledge_items
            if item.get("primary_domain", "") in ("", _task_class, "generic")
        ]

    if knowledge_items and _should_inject_knowledge(round_goal, knowledge_items):
        # Wave 59.5: auto-inject full content for top-1 entry, index-only
        # for remaining.  Addresses Phase 1 finding: 0 knowledge_detail
        # calls across 8 tasks — 30B models don't call optional tools.

        # Filter to entries above similarity threshold first.
        injected_items: list[dict[str, Any]] = []
        for item in knowledge_items[:8]:
            raw_similarity = float(
                item.get("similarity", item.get("score", 0.0)),
            )
            if raw_similarity < _MIN_KNOWLEDGE_SIMILARITY:
                log.debug(
                    "context.knowledge_below_threshold",
                    entry_id=item.get("id", ""),
                    title=str(item.get("title", ""))[:60],
                    similarity=round(raw_similarity, 3),
                    threshold=_MIN_KNOWLEDGE_SIMILARITY,
                )
                continue
            injected_items.append(item)

        lines: list[str] = ["[Available Knowledge]"]

        for idx, item in enumerate(injected_items):
            entry_id = item.get("id", "")
            title = item.get("title", "")
            conf = float(item.get("confidence", 0.5))
            sub_type = str(item.get("sub_type", "") or "")
            status = str(item.get("status", "")).upper()
            raw_similarity = float(
                item.get("similarity", item.get("score", 0.0)),
            )

            if idx == 0:
                # Top-1: full content injection (~200 tokens)
                top_content = str(item.get("content", ""))[:500]
                # Truncate at sentence boundary if possible
                last_period = top_content.rfind(". ")
                if last_period > 200:
                    top_content = top_content[:last_period + 1]
                if sub_type == "trajectory":
                    type_tag = "[TRAJECTORY] "
                else:
                    ctype = str(item.get("canonical_type", "skill")).upper()
                    type_tag = f"[{ctype}, {status}] "
                lines.append(
                    f'{type_tag}**{title}** (conf: {conf:.2f}, id: {entry_id})\n'
                    f'{top_content}'
                )
            elif sub_type == "trajectory":
                summary = str(
                    item.get("summary", item.get("content_preview", "")),
                )[:100]
                lines.append(
                    f'- [TRAJECTORY] "{title}" -- {summary} '
                    f"(conf: {conf:.2f}, id: {entry_id})"
                )
            else:
                ctype = str(item.get("canonical_type", "skill")).upper()
                label = f"{ctype}, {status}"
                summary = str(
                    item.get("summary", item.get("content_preview", "")),
                )[:80]
                lines.append(
                    f'- [{label}] "{title}" -- {summary} '
                    f"(conf: {conf:.2f}, id: {entry_id})"
                )

            knowledge_access_items.append(KnowledgeAccessItem(
                id=entry_id,
                source_system=item.get("source_system", ""),
                canonical_type=item.get("canonical_type", "skill"),
                title=title,
                confidence=conf,
                score=float(item.get("score", 0.0)),
                similarity=raw_similarity,
            ))

        if len(lines) > 1:
            knowledge_text = _truncate("\n".join(lines), budgets.skill_bank)
            messages.append({"role": "user", "content": knowledge_text})
            skip_legacy_skills = True

    # 3. Routed context with per-source cap
    routed_budget = budgets.routed_outputs
    routed_used = 0
    for source_id, output in routed_outputs.items():
        if routed_used >= routed_budget:
            break
        capped = _truncate_preserve_edges(output, budgets.max_per_source)
        msg_text = f"[{source_id}]: {capped}"
        msg_tokens = estimate_tokens(msg_text)
        if routed_used + msg_tokens > routed_budget:
            break
        messages.append({"role": "user", "content": msg_text})
        routed_used += msg_tokens

    # 4. Merge summaries (capped)
    merge_used = 0
    for summary in merged_summaries:
        if merge_used >= budgets.merge_summaries:
            break
        capped = _truncate(summary, budgets.merge_summaries - merge_used)
        messages.append({"role": "user", "content": capped})
        merge_used += estimate_tokens(capped)

    # 5. Previous round summary (compacted if over threshold)
    if colony_context.prev_round_summary:
        prev = colony_context.prev_round_summary
        if estimate_tokens(prev) > budgets.compaction_threshold:
            prev = _compact_summary(prev, round_goal, budgets.prev_round_summary)
        prev_text = _truncate(f"Previous round: {prev}", budgets.prev_round_summary)
        messages.append({"role": "user", "content": prev_text})

    # 6. Skill bank — confidence-weighted composite scoring (algorithms.md §2)
    #    With optional KG augmentation (Wave 13 B-T3, algorithms.md §5)
    #    Wave 28: skipped when unified knowledge is present.
    if vector_port is not None and not skip_legacy_skills:
        try:
            kg_triples: list[dict[str, Any]] = []
            t_retrieval = _time_mod.perf_counter()

            # Use RetrievalPipeline when KG adapter is available
            if kg_adapter is not None:
                pipeline = RetrievalPipeline(vector_port, kg_adapter)
                raw_skills, kg_triples = await pipeline.search(
                    workspace_id=colony_context.workspace_id,
                    query=round_goal,
                    top_k=8,
                )
            else:
                raw_skills = await vector_port.search(
                    collection=_skill_collection(vector_port),
                    query=round_goal,
                    top_k=8,
                )

            retrieval_ms = (_time_mod.perf_counter() - t_retrieval) * 1000

            # Update timing for non-pipeline path (no KG adapter)
            if kg_adapter is None:
                _last_retrieval_timing["graph_ms"] = 0.0
                _last_retrieval_timing["vector_ms"] = round(retrieval_ms, 2)
                _last_retrieval_timing["total_ms"] = round(retrieval_ms, 2)

            if raw_skills:
                # Wave 41 A2: unified exploration-confidence via shared helper
                from formicos.engine.scoring_math import exploration_score  # noqa: PLC0415

                scored: list[tuple[float, VectorSearchHit, float]] = []
                for hit in raw_skills:
                    # Normalize distance → similarity
                    semantic = 1.0 - min(hit.score, 1.0)
                    confidence = float(hit.metadata.get("confidence", 0.5))
                    freshness = _compute_freshness(
                        hit.metadata.get("extracted_at", ""),
                    )
                    alpha = float(hit.metadata.get("conf_alpha", 0))
                    beta_p = float(hit.metadata.get("conf_beta", 0))
                    exploration = exploration_score(
                        alpha if alpha > 0 else 5.0,
                        beta_p if beta_p > 0 else 5.0,
                        total_observations=total_colonies,
                        ucb_weight=ucb_exploration_weight,
                    )
                    composite = (
                        0.50 * semantic
                        + 0.25 * confidence
                        + 0.20 * freshness
                        + 0.05 * min(exploration, 1.0)
                    )
                    scored.append((composite, hit, confidence))

                scored.sort(key=lambda x: -x[0])
                top_skills = scored[:3]

                skill_parts: list[str] = []
                for _score, skill_hit, conf in top_skills:
                    skill_parts.append(
                        f"[conf:{conf:.1f}] {skill_hit.content[:300]}",
                    )
                    retrieved_skill_ids.append(skill_hit.id)

                skill_text = "Relevant skills:\n" + "\n".join(skill_parts)

                # Append KG relationship context if available
                if kg_triples:
                    kg_lines = [
                        f"  {t['subject']} {t['predicate']} {t['object']}"
                        for t in kg_triples
                    ]
                    skill_text += "\n\nRelated knowledge:\n" + "\n".join(
                        kg_lines,
                    )

                skill_text = _truncate(skill_text, budgets.skill_bank)
                messages.append({"role": "user", "content": skill_text})

                log.info(
                    "context.skill_retrieval",
                    agent_id=agent.id,
                    skills=len(top_skills),
                    kg_triples=len(kg_triples),
                    retrieval_ms=round(retrieval_ms, 2),
                    top_composite=round(top_skills[0][0], 3) if top_skills else 0,
                )
        except Exception:
            log.debug("skill_retrieval_failed", agent_id=agent.id)

    return ContextResult(
        messages=messages,
        retrieved_skill_ids=retrieved_skill_ids,
        knowledge_items_used=knowledge_access_items,  # Wave 28
    )
