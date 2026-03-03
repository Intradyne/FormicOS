"""
FormicOS v0.6.0 -- SkillBank

Cross-colony skill library that accumulates, retrieves, and evolves knowledge
distilled from completed colonies.  The only component that bridges information
between colonies.

Skills are stored as short, actionable text entries organized into three tiers:
  - General:       Cross-colony strategic patterns
  - Task-Specific: Per-category heuristics
  - Lessons:       Failure patterns to avoid

Retrieval uses MiniLM-L6-v2 (same model as DyTopo routing) for lightweight
cosine-similarity search.  Deduplication prevents bloat.  Cached embeddings
are persisted alongside skills so they are never recomputed on load.

The optional ``embedder`` parameter accepts a SentenceTransformer instance (or
any object whose ``.encode(texts)`` returns an ndarray of shape ``(N, D)``).
When *None*, dedup and retrieval are silently skipped, which allows the rest of
the system (and the test suite) to operate without loading the model.

Inspired by SkillRL (arXiv:2602.08234).
"""

from __future__ import annotations

import json
import logging
import uuid
from pathlib import Path
from typing import Any

import numpy as np
from pydantic import BaseModel, Field

from .models import Skill, SkillBankConfig, SkillTier

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────

SKILL_INJECTION_TEMPLATE = """\
[STRATEGIC GUIDANCE]
The following patterns have been distilled from previous successful colony runs. \
Apply them if relevant to your current task:

{skills_formatted}

These are guidelines, not rules. If your current situation differs significantly \
from the pattern context, use your judgment.
[END STRATEGIC GUIDANCE]"""

_VERSION = "0.6.0"


# ── EvolutionReport ───────────────────────────────────────────────────────

class EvolutionReport(BaseModel):
    """Result of a SkillBank evolution cycle."""

    evolved: bool
    pruned: int = 0
    flagged_for_revision: list[str] = Field(default_factory=list)
    total_skills: int = 0
    reason: str | None = None


# ── SkillBank ─────────────────────────────────────────────────────────────

class SkillBank:
    """
    Stores, retrieves, deduplicates, and evolves distilled skills.

    Parameters
    ----------
    storage_path : str | Path
        Path to the JSON file used for persistence.
    config : SkillBankConfig
        Typed configuration (thresholds, top-k, evolution interval, etc.).
    embedder : Any | None
        A SentenceTransformer-compatible object (must have ``.encode(list[str])``
        returning an ndarray of shape ``(N, D)``).  If *None*, embedding-dependent
        operations (dedup, retrieval) are silently skipped.
    """

    def __init__(
        self,
        storage_path: str | Path,
        config: SkillBankConfig,
        embedder: Any | None = None,
    ) -> None:
        self.storage_path = Path(storage_path)
        self.config = config
        self.embedder = embedder

        self.top_k: int = config.retrieval_top_k
        self.dedup_threshold: float = config.dedup_threshold
        self.evolution_interval: int = config.evolution_interval
        self.prune_zero_hit_after: int = config.prune_zero_hit_after

        self._skills: list[Skill] = []
        self._colony_count: int = 0

        # Load any pre-existing skills from disk
        self.load()

    # ── Properties ────────────────────────────────────────────────────────

    @property
    def skills(self) -> list[Skill]:
        """Read-only access to the internal skill list."""
        return self._skills

    # ── Public API ────────────────────────────────────────────────────────

    def store(self, skills: list[Skill]) -> int:
        """Store a batch of skills, deduplicating against existing entries.

        Returns the number of skills actually stored (after dedup filtering).
        """
        if not skills:
            return 0

        stored = 0
        for skill in skills:
            # Compute embedding if embedder is available and embedding is missing
            if skill.embedding is None and self.embedder is not None:
                vecs = self.embedder.encode([skill.content])
                skill.embedding = vecs[0].tolist()

            # Dedup check (only possible with embeddings)
            if self.embedder is not None and self._is_duplicate(skill):
                logger.debug(
                    "Skill dedup: '%s' too similar to existing",
                    skill.content[:50],
                )
                continue

            # Auto-generate skill_id if empty
            if not skill.skill_id:
                skill.skill_id = self._generate_id(skill.tier)

            self._skills.append(skill)
            stored += 1

        if stored > 0:
            self.save()
            logger.info(
                "Stored %d new skills (total: %d)", stored, len(self._skills)
            )

        return stored

    def store_single(
        self,
        content: str,
        tier: str | SkillTier = SkillTier.GENERAL,
        category: str | None = None,
    ) -> str:
        """Convenience method: create and store a single skill.

        Returns the skill_id on success.
        Raises ``ValueError`` if the skill is rejected by dedup.
        """
        tier_enum = SkillTier(tier) if isinstance(tier, str) else tier
        skill = Skill(
            skill_id="",
            content=content,
            tier=tier_enum,
            category=category,
        )
        count = self.store([skill])
        if count > 0:
            return skill.skill_id
        raise ValueError("Skill too similar to existing skill (dedup threshold)")

    def retrieve(
        self,
        query: str,
        top_k: int | None = None,
        categories: list[str] | None = None,
    ) -> list[Skill]:
        """Return the top-K most relevant skills for *query*.

        Increments ``retrieval_count`` on every returned skill.

        When *categories* is provided, only GENERAL and LESSON tier skills
        (which are universal) plus TASK_SPECIFIC skills whose ``.category``
        matches one of the provided categories are considered.  When *None*,
        all skills are searched.

        If no embedder is available, returns an empty list.
        """
        if self.embedder is None:
            return []

        k = top_k if top_k is not None else self.top_k
        if not self._skills:
            return []

        # Category-scoped filter
        searchable = self._skills
        if categories is not None:
            searchable = [
                s
                for s in self._skills
                if s.tier in (SkillTier.GENERAL, SkillTier.LESSON)
                or (
                    s.tier == SkillTier.TASK_SPECIFIC
                    and s.category in categories
                )
            ]
        if not searchable:
            return []

        query_emb = self.embedder.encode([query])[0]

        scored: list[tuple[float, Skill]] = []
        for skill in searchable:
            if skill.embedding is None:
                continue
            sim = self._cosine_similarity(query_emb, np.array(skill.embedding))
            scored.append((sim, skill))

        scored.sort(key=lambda x: x[0], reverse=True)
        results = [s for _, s in scored[:k]]

        # Increment retrieval counts
        for skill in results:
            skill.retrieval_count += 1

        if results:
            self.save()

        return results

    def update(self, skill_id: str, content: str) -> None:
        """Update a skill's content (and re-embed if embedder is available).

        Raises ``KeyError`` if *skill_id* is not found.
        """
        skill = self._find_skill(skill_id)
        skill.content = content

        if self.embedder is not None:
            vecs = self.embedder.encode([content])
            skill.embedding = vecs[0].tolist()

        self.save()

    def delete(self, skill_id: str) -> None:
        """Remove a skill by ID.

        Raises ``KeyError`` if *skill_id* is not found.
        """
        idx = self._find_skill_index(skill_id)
        self._skills.pop(idx)
        self.save()

    def get_all(self) -> dict[str, list[Skill]]:
        """Return all skills grouped by tier.

        Keys are SkillTier values: ``"general"``, ``"task_specific"``, ``"lesson"``.
        """
        grouped: dict[str, list[Skill]] = {
            SkillTier.GENERAL.value: [],
            SkillTier.TASK_SPECIFIC.value: [],
            SkillTier.LESSON.value: [],
        }
        for skill in self._skills:
            grouped[skill.tier.value].append(skill)
        return grouped

    def evolve(self, colony_outcomes: list[dict[str, Any]] | None = None) -> EvolutionReport:
        """Run one evolution cycle.

        Increments the internal colony counter.  When the counter reaches
        ``evolution_interval``, zero-hit skills are pruned and low
        success-correlation skills are flagged.

        If *colony_outcomes* is provided (list of dicts with ``skill_ids``
        and ``success`` keys), success correlations are updated first.
        """
        # Update success correlations from colony outcomes
        if colony_outcomes:
            self._update_correlations(colony_outcomes)

        self._colony_count += 1

        if self._colony_count < self.evolution_interval:
            return EvolutionReport(
                evolved=False,
                total_skills=len(self._skills),
                reason="Not yet due",
            )

        # Reset counter
        self._colony_count = 0

        pruned = 0
        flagged: list[str] = []
        surviving: list[Skill] = []

        for skill in self._skills:
            if skill.retrieval_count == 0:
                pruned += 1
                logger.info("Pruning zero-hit skill: %s", skill.skill_id)
            else:
                surviving.append(skill)
                if skill.success_correlation < 0.3 and skill.retrieval_count >= 3:
                    flagged.append(skill.skill_id)

        self._skills = surviving
        self.save()

        report = EvolutionReport(
            evolved=True,
            pruned=pruned,
            flagged_for_revision=flagged,
            total_skills=len(self._skills),
        )
        logger.info("SkillBank evolved: %s", report.model_dump())
        return report

    def format_for_injection(self, skills: list[Skill]) -> str:
        """Format a list of skills into a markdown block for agent context injection."""
        if not skills:
            return ""

        lines: list[str] = []
        for skill in skills:
            tier_label = skill.tier.value.replace("_", " ").title()
            success_pct = int(skill.success_correlation * 100)
            lines.append(
                f"- **[{tier_label}]** {skill.content} "
                f"(retrieved {skill.retrieval_count}x, "
                f"{success_pct}% success)"
            )

        return SKILL_INJECTION_TEMPLATE.format(
            skills_formatted="\n".join(lines)
        )

    # ── Persistence ───────────────────────────────────────────────────────

    def save(self) -> None:
        """Persist all skills (with cached embeddings) to JSON."""
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "version": _VERSION,
            "colony_count": self._colony_count,
            "skills": [
                skill.model_dump(mode="json") for skill in self._skills
            ],
        }
        try:
            self.storage_path.write_text(
                json.dumps(data, indent=2, default=str),
                encoding="utf-8",
            )
        except OSError as exc:
            logger.error("Failed to save SkillBank to %s: %s", self.storage_path, exc)

    def load(self) -> None:
        """Load skills from the JSON file.  Embeddings are restored from the
        persisted cache — no recomputation required.
        """
        if not self.storage_path.exists():
            self._skills = []
            return

        try:
            raw = json.loads(self.storage_path.read_text(encoding="utf-8"))
            self._colony_count = raw.get("colony_count", 0)
            self._skills = [
                Skill.model_validate(entry)
                for entry in raw.get("skills", [])
            ]
            logger.info(
                "Loaded %d skills from %s", len(self._skills), self.storage_path
            )
        except Exception as exc:
            logger.warning(
                "Failed to load SkillBank from %s: %s", self.storage_path, exc
            )
            self._skills = []

    # ── Internal helpers ──────────────────────────────────────────────────

    @staticmethod
    def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
        """Cosine similarity between two vectors."""
        denom = np.linalg.norm(a) * np.linalg.norm(b)
        if denom < 1e-12:
            return 0.0
        return float(np.dot(a, b) / denom)

    def _is_duplicate(self, skill: Skill) -> bool:
        """Return True if *skill* is too similar to any existing skill."""
        if not self._skills or skill.embedding is None:
            return False

        new_emb = np.array(skill.embedding)
        for existing in self._skills:
            if existing.embedding is None:
                continue
            sim = self._cosine_similarity(new_emb, np.array(existing.embedding))
            if sim > self.dedup_threshold:
                return True
        return False

    def _find_skill(self, skill_id: str) -> Skill:
        """Lookup a skill by ID, raising KeyError if not found."""
        for skill in self._skills:
            if skill.skill_id == skill_id:
                return skill
        raise KeyError(f"Skill not found: {skill_id}")

    def _find_skill_index(self, skill_id: str) -> int:
        """Lookup a skill's index by ID, raising KeyError if not found."""
        for i, skill in enumerate(self._skills):
            if skill.skill_id == skill_id:
                return i
        raise KeyError(f"Skill not found: {skill_id}")

    @staticmethod
    def _generate_id(tier: SkillTier) -> str:
        """Generate a unique skill ID with a tier prefix."""
        prefix = {
            SkillTier.GENERAL: "gen",
            SkillTier.TASK_SPECIFIC: "ts",
            SkillTier.LESSON: "les",
        }.get(tier, "sk")
        return f"{prefix}_{uuid.uuid4().hex[:8]}"

    def _update_correlations(
        self, colony_outcomes: list[dict[str, Any]]
    ) -> None:
        """Update success_correlation for skills based on colony results.

        Each outcome dict should have:
          - ``skill_ids``: list[str] — skills retrieved during the colony
          - ``success``: bool — whether the colony succeeded
        """
        for outcome in colony_outcomes:
            skill_ids = set(outcome.get("skill_ids", []))
            success = outcome.get("success", False)
            for skill in self._skills:
                if skill.skill_id in skill_ids:
                    # Exponential moving average toward 1.0 (success) or 0.0
                    alpha = 0.3
                    target = 1.0 if success else 0.0
                    new_val = skill.success_correlation * (1 - alpha) + target * alpha
                    # Clamp to [0.0, 1.0] per model constraint
                    skill.success_correlation = max(0.0, min(1.0, new_val))
