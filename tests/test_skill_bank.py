"""
Tests for FormicOS v0.6.0 SkillBank.

Covers:
- Store + retrieve round-trip
- Dedup rejects skill with similarity > threshold
- Dedup allows skill with similarity < threshold
- Evolution prunes zero-hit skills
- Retrieval increments retrieval_count
- Cached embeddings persist across save/load
- get_all() groups by tier correctly
- format_for_injection produces readable markdown
- Delete removes skill
- Update changes content
- Category filtering in retrieve
- Store without embedder (skip dedup, no embedding cached)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pytest

from src.models import Skill, SkillBankConfig, SkillTier
from src.skill_bank import EvolutionReport, SkillBank


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════


class FakeEmbedder:
    """Mock embedder that maps predefined content strings to vectors.

    Any unknown content is embedded as a random-but-deterministic vector
    derived from the hash of the string.
    """

    def __init__(self, mapping: dict[str, list[float]] | None = None, dim: int = 4):
        self.mapping: dict[str, list[float]] = mapping or {}
        self.dim = dim
        self.encode_calls: list[list[str]] = []

    def encode(self, texts: list[str]) -> np.ndarray:
        self.encode_calls.append(texts)
        vecs = []
        for t in texts:
            if t in self.mapping:
                vecs.append(self.mapping[t])
            else:
                rng = np.random.RandomState(hash(t) % 2**31)
                vecs.append(rng.randn(self.dim).tolist())
        return np.array(vecs)


def _default_config(**overrides: Any) -> SkillBankConfig:
    """Build a SkillBankConfig with test-friendly defaults."""
    defaults = {
        "storage_file": ".formicos/skill_bank.json",
        "retrieval_top_k": 3,
        "dedup_threshold": 0.85,
        "evolution_interval": 5,
        "prune_zero_hit_after": 10,
    }
    defaults.update(overrides)
    return SkillBankConfig(**defaults)


def _make_skill(
    content: str = "test skill",
    tier: SkillTier = SkillTier.GENERAL,
    category: str | None = None,
    embedding: list[float] | None = None,
    retrieval_count: int = 0,
    success_correlation: float = 0.0,
    skill_id: str = "",
    source_colony: str | None = None,
) -> Skill:
    """Build a Skill with sensible defaults for testing."""
    return Skill(
        skill_id=skill_id,
        content=content,
        tier=tier,
        category=category,
        embedding=embedding,
        retrieval_count=retrieval_count,
        success_correlation=success_correlation,
        source_colony=source_colony,
    )


# ═══════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════


@pytest.fixture
def storage_file(tmp_path: Path) -> Path:
    """Return a temporary storage path (file does not exist yet)."""
    return tmp_path / "skills.json"


@pytest.fixture
def embedder() -> FakeEmbedder:
    """Return a FakeEmbedder with some predefined mappings."""
    return FakeEmbedder(
        mapping={
            "alpha skill": [1.0, 0.0, 0.0, 0.0],
            "beta skill": [0.0, 1.0, 0.0, 0.0],
            "gamma skill": [0.0, 0.0, 1.0, 0.0],
            "delta skill": [0.0, 0.0, 0.0, 1.0],
            # Near-duplicate of alpha (cosine > 0.85)
            "alpha skill v2": [0.99, 0.05, 0.0, 0.0],
            # Query vectors
            "find alpha": [0.95, 0.1, 0.0, 0.0],
            "find beta": [0.1, 0.95, 0.0, 0.0],
            "find gamma": [0.0, 0.1, 0.95, 0.0],
        },
        dim=4,
    )


@pytest.fixture
def config() -> SkillBankConfig:
    return _default_config()


@pytest.fixture
def bank(storage_file: Path, config: SkillBankConfig, embedder: FakeEmbedder) -> SkillBank:
    """Return a fresh SkillBank wired to tmp storage and a fake embedder."""
    return SkillBank(
        storage_path=storage_file,
        config=config,
        embedder=embedder,
    )


# ═══════════════════════════════════════════════════════════════════════════
# Store + Retrieve Round-Trip
# ═══════════════════════════════════════════════════════════════════════════


class TestStoreRetrieve:
    def test_store_and_retrieve_round_trip(self, bank: SkillBank, embedder: FakeEmbedder):
        """Store a skill, then retrieve it with a similar query."""
        skill = _make_skill(content="alpha skill")
        count = bank.store([skill])
        assert count == 1
        assert len(bank.skills) == 1

        results = bank.retrieve("find alpha", top_k=1)
        assert len(results) == 1
        assert results[0].content == "alpha skill"

    def test_store_multiple(self, bank: SkillBank):
        """Store several skills at once."""
        skills = [
            _make_skill(content="alpha skill"),
            _make_skill(content="beta skill"),
            _make_skill(content="gamma skill"),
        ]
        count = bank.store(skills)
        assert count == 3
        assert len(bank.skills) == 3

    def test_store_returns_zero_for_empty_list(self, bank: SkillBank):
        assert bank.store([]) == 0

    def test_retrieve_empty_bank(self, bank: SkillBank):
        results = bank.retrieve("anything")
        assert results == []


# ═══════════════════════════════════════════════════════════════════════════
# Deduplication
# ═══════════════════════════════════════════════════════════════════════════


class TestDedup:
    def test_dedup_rejects_similar_skill(self, bank: SkillBank):
        """A skill with cosine similarity > threshold is rejected."""
        bank.store([_make_skill(content="alpha skill")])
        count = bank.store([_make_skill(content="alpha skill v2")])
        assert count == 0, "Near-duplicate should be rejected"
        assert len(bank.skills) == 1

    def test_dedup_allows_dissimilar_skill(self, bank: SkillBank):
        """Orthogonal skills pass dedup."""
        bank.store([_make_skill(content="alpha skill")])
        count = bank.store([_make_skill(content="beta skill")])
        assert count == 1
        assert len(bank.skills) == 2

    def test_dedup_threshold_configurable(
        self, storage_file: Path, embedder: FakeEmbedder
    ):
        """A very high threshold (0.999) lets the near-duplicate through."""
        cfg = _default_config(dedup_threshold=0.999)
        bank = SkillBank(storage_path=storage_file, config=cfg, embedder=embedder)
        bank.store([_make_skill(content="alpha skill")])
        count = bank.store([_make_skill(content="alpha skill v2")])
        assert count == 1, "Near-duplicate should pass with threshold=0.999"


# ═══════════════════════════════════════════════════════════════════════════
# Evolution
# ═══════════════════════════════════════════════════════════════════════════


class TestEvolution:
    def test_evolve_prunes_zero_hit_skills(self, bank: SkillBank):
        """After evolution_interval colonies, zero-hit skills are pruned."""
        # Store two skills; only one is ever retrieved
        bank.store([
            _make_skill(content="alpha skill"),
            _make_skill(content="beta skill"),
        ])
        # Retrieve alpha once (increments retrieval_count)
        bank.retrieve("find alpha", top_k=1)

        # Run evolution_interval - 1 times (should NOT evolve yet)
        for _ in range(bank.evolution_interval - 1):
            report = bank.evolve()
            assert not report.evolved

        # This one triggers evolution
        report = bank.evolve()
        assert report.evolved
        assert report.pruned == 1  # beta was never retrieved
        assert len(bank.skills) == 1
        assert bank.skills[0].content == "alpha skill"

    def test_evolve_not_due(self, bank: SkillBank):
        report = bank.evolve()
        assert not report.evolved
        assert report.reason == "Not yet due"

    def test_evolve_flags_low_correlation(
        self, storage_file: Path, embedder: FakeEmbedder
    ):
        """Skills with low success_correlation and retrieval_count >= 3 are flagged."""
        cfg = _default_config(evolution_interval=1)
        bank = SkillBank(storage_path=storage_file, config=cfg, embedder=embedder)

        skill = _make_skill(
            content="alpha skill",
            retrieval_count=5,
            success_correlation=0.1,
            skill_id="flagme",
        )
        # Pre-set embedding so store doesn't recompute
        skill.embedding = [1.0, 0.0, 0.0, 0.0]
        bank._skills.append(skill)

        report = bank.evolve()
        assert report.evolved
        assert "flagme" in report.flagged_for_revision

    def test_evolve_returns_evolution_report(self, bank: SkillBank):
        """evolve() always returns an EvolutionReport."""
        report = bank.evolve()
        assert isinstance(report, EvolutionReport)


# ═══════════════════════════════════════════════════════════════════════════
# Retrieval Count
# ═══════════════════════════════════════════════════════════════════════════


class TestRetrievalCount:
    def test_retrieve_increments_count(self, bank: SkillBank):
        """Every retrieval increments retrieval_count by 1."""
        bank.store([_make_skill(content="alpha skill")])
        assert bank.skills[0].retrieval_count == 0

        bank.retrieve("find alpha", top_k=1)
        assert bank.skills[0].retrieval_count == 1

        bank.retrieve("find alpha", top_k=1)
        assert bank.skills[0].retrieval_count == 2


# ═══════════════════════════════════════════════════════════════════════════
# Persistence — save / load
# ═══════════════════════════════════════════════════════════════════════════


class TestPersistence:
    def test_cached_embeddings_persist(
        self, storage_file: Path, config: SkillBankConfig, embedder: FakeEmbedder
    ):
        """After save+load, embeddings are restored from cache (not recomputed)."""
        bank1 = SkillBank(storage_path=storage_file, config=config, embedder=embedder)
        bank1.store([_make_skill(content="alpha skill")])

        # Record the embedding that was cached
        saved_embedding = bank1.skills[0].embedding
        assert saved_embedding is not None

        # Create a second bank from the same file — should load cached embeddings
        embedder2 = FakeEmbedder(dim=4)
        bank2 = SkillBank(storage_path=storage_file, config=config, embedder=embedder2)

        assert len(bank2.skills) == 1
        assert bank2.skills[0].embedding == saved_embedding
        # embedder2 should NOT have been called for encoding (loaded from cache)
        assert len(embedder2.encode_calls) == 0

    def test_save_creates_parent_dirs(self, tmp_path: Path, config: SkillBankConfig):
        """save() creates intermediate directories if they don't exist."""
        deep_path = tmp_path / "a" / "b" / "c" / "skills.json"
        bank = SkillBank(storage_path=deep_path, config=config)
        bank.store([_make_skill(content="test", skill_id="x")])
        assert deep_path.exists()

    def test_load_nonexistent_file(self, tmp_path: Path, config: SkillBankConfig):
        """Loading from a missing file results in an empty skill list."""
        bank = SkillBank(
            storage_path=tmp_path / "missing.json",
            config=config,
        )
        assert len(bank.skills) == 0

    def test_load_corrupt_file(self, tmp_path: Path, config: SkillBankConfig):
        """A corrupt JSON file results in an empty skill list (not a crash)."""
        bad_file = tmp_path / "bad.json"
        bad_file.write_text("NOT VALID JSON {{{", encoding="utf-8")
        bank = SkillBank(storage_path=bad_file, config=config)
        assert len(bank.skills) == 0

    def test_colony_count_persists(
        self, storage_file: Path, config: SkillBankConfig, embedder: FakeEmbedder
    ):
        """The colony_count counter survives save/load."""
        bank1 = SkillBank(storage_path=storage_file, config=config, embedder=embedder)
        bank1.store([_make_skill(content="alpha skill")])
        bank1.evolve()  # increments _colony_count to 1
        bank1.evolve()  # increments _colony_count to 2
        bank1.save()

        bank2 = SkillBank(storage_path=storage_file, config=config, embedder=embedder)
        assert bank2._colony_count == 2


# ═══════════════════════════════════════════════════════════════════════════
# get_all() grouping
# ═══════════════════════════════════════════════════════════════════════════


class TestGetAll:
    def test_groups_by_tier(self, bank: SkillBank):
        """get_all() returns a dict keyed by tier value."""
        bank.store([
            _make_skill(content="alpha skill", tier=SkillTier.GENERAL),
            _make_skill(content="beta skill", tier=SkillTier.TASK_SPECIFIC, category="code"),
            _make_skill(content="gamma skill", tier=SkillTier.LESSON),
        ])
        grouped = bank.get_all()

        assert "general" in grouped
        assert "task_specific" in grouped
        assert "lesson" in grouped
        assert len(grouped["general"]) == 1
        assert len(grouped["task_specific"]) == 1
        assert len(grouped["lesson"]) == 1
        assert grouped["general"][0].content == "alpha skill"

    def test_empty_tiers_present(self, bank: SkillBank):
        """Even with no skills, all three tier keys are present."""
        grouped = bank.get_all()
        assert set(grouped.keys()) == {"general", "task_specific", "lesson"}
        for v in grouped.values():
            assert v == []


# ═══════════════════════════════════════════════════════════════════════════
# format_for_injection
# ═══════════════════════════════════════════════════════════════════════════


class TestFormatForInjection:
    def test_produces_readable_markdown(self, bank: SkillBank):
        skill = _make_skill(
            content="Always decompose complex tasks",
            tier=SkillTier.GENERAL,
            retrieval_count=7,
            success_correlation=0.8,
            skill_id="gen_abc",
        )
        skill.embedding = [1.0, 0.0, 0.0, 0.0]

        output = bank.format_for_injection([skill])
        assert "[STRATEGIC GUIDANCE]" in output
        assert "[END STRATEGIC GUIDANCE]" in output
        assert "Always decompose complex tasks" in output
        assert "7x" in output
        assert "80% success" in output
        assert "**[General]**" in output

    def test_empty_list_returns_empty_string(self, bank: SkillBank):
        assert bank.format_for_injection([]) == ""

    def test_multiple_skills(self, bank: SkillBank):
        skills = [
            _make_skill(content="skill A", skill_id="a"),
            _make_skill(content="skill B", skill_id="b"),
        ]
        for s in skills:
            s.embedding = [1.0, 0.0, 0.0, 0.0]
        output = bank.format_for_injection(skills)
        assert "skill A" in output
        assert "skill B" in output


# ═══════════════════════════════════════════════════════════════════════════
# Delete
# ═══════════════════════════════════════════════════════════════════════════


class TestDelete:
    def test_delete_removes_skill(self, bank: SkillBank):
        bank.store([_make_skill(content="alpha skill")])
        sid = bank.skills[0].skill_id
        bank.delete(sid)
        assert len(bank.skills) == 0

    def test_delete_nonexistent_raises(self, bank: SkillBank):
        with pytest.raises(KeyError):
            bank.delete("nonexistent_id")


# ═══════════════════════════════════════════════════════════════════════════
# Update
# ═══════════════════════════════════════════════════════════════════════════


class TestUpdate:
    def test_update_changes_content(self, bank: SkillBank):
        bank.store([_make_skill(content="alpha skill")])
        sid = bank.skills[0].skill_id
        bank.update(sid, "updated content")
        assert bank.skills[0].content == "updated content"

    def test_update_reembeds(self, bank: SkillBank, embedder: FakeEmbedder):
        """Updating content triggers a new embedding computation."""
        bank.store([_make_skill(content="alpha skill")])
        sid = bank.skills[0].skill_id
        old_embedding = bank.skills[0].embedding

        bank.update(sid, "beta skill")
        new_embedding = bank.skills[0].embedding

        assert new_embedding is not None
        assert new_embedding != old_embedding

    def test_update_nonexistent_raises(self, bank: SkillBank):
        with pytest.raises(KeyError):
            bank.update("nonexistent_id", "content")


# ═══════════════════════════════════════════════════════════════════════════
# Category filtering in retrieve
# ═══════════════════════════════════════════════════════════════════════════


class TestCategoryFiltering:
    def test_retrieve_filters_by_category(self, bank: SkillBank):
        """Task-specific skills outside the requested categories are excluded."""
        bank.store([
            _make_skill(content="alpha skill", tier=SkillTier.GENERAL),
            _make_skill(
                content="beta skill",
                tier=SkillTier.TASK_SPECIFIC,
                category="coding",
            ),
            _make_skill(
                content="gamma skill",
                tier=SkillTier.TASK_SPECIFIC,
                category="research",
            ),
        ])

        # Only "coding" category + general/lesson
        results = bank.retrieve("find beta", top_k=10, categories=["coding"])
        contents = [r.content for r in results]
        assert "beta skill" in contents
        assert "alpha skill" in contents  # general is always included
        assert "gamma skill" not in contents  # wrong category

    def test_retrieve_no_categories_returns_all(self, bank: SkillBank):
        """Without categories filter, all skills are searched."""
        bank.store([
            _make_skill(content="alpha skill", tier=SkillTier.GENERAL),
            _make_skill(
                content="beta skill",
                tier=SkillTier.TASK_SPECIFIC,
                category="coding",
            ),
        ])
        results = bank.retrieve("find alpha", top_k=10)
        assert len(results) == 2

    def test_lessons_always_included(self, bank: SkillBank):
        """LESSON tier is universal — always included regardless of categories."""
        bank.store([
            _make_skill(content="delta skill", tier=SkillTier.LESSON),
        ])
        results = bank.retrieve("find delta", top_k=10, categories=["coding"])
        assert len(results) == 1
        assert results[0].tier == SkillTier.LESSON


# ═══════════════════════════════════════════════════════════════════════════
# Store without embedder
# ═══════════════════════════════════════════════════════════════════════════


class TestNoEmbedder:
    def test_store_without_embedder(self, storage_file: Path, config: SkillBankConfig):
        """When embedder is None, skills are stored without embedding or dedup."""
        bank = SkillBank(storage_path=storage_file, config=config, embedder=None)
        count = bank.store([_make_skill(content="orphan skill")])
        assert count == 1
        assert bank.skills[0].embedding is None

    def test_retrieve_without_embedder(self, storage_file: Path, config: SkillBankConfig):
        """Without embedder, retrieve returns an empty list."""
        bank = SkillBank(storage_path=storage_file, config=config, embedder=None)
        bank.store([_make_skill(content="orphan skill")])
        results = bank.retrieve("anything")
        assert results == []

    def test_no_dedup_without_embedder(self, storage_file: Path, config: SkillBankConfig):
        """Without embedder, identical content can be stored twice (no dedup)."""
        bank = SkillBank(storage_path=storage_file, config=config, embedder=None)
        bank.store([_make_skill(content="same")])
        count = bank.store([_make_skill(content="same")])
        assert count == 1  # no dedup, so it stores
        assert len(bank.skills) == 2


# ═══════════════════════════════════════════════════════════════════════════
# store_single convenience method
# ═══════════════════════════════════════════════════════════════════════════


class TestStoreSingle:
    def test_store_single_returns_id(self, bank: SkillBank):
        sid = bank.store_single("alpha skill", tier="general")
        assert sid.startswith("gen_")
        assert len(bank.skills) == 1

    def test_store_single_with_category(self, bank: SkillBank):
        sid = bank.store_single(
            "beta skill", tier="task_specific", category="coding"
        )
        assert sid.startswith("ts_")
        assert bank.skills[0].category == "coding"

    def test_store_single_dedup_raises(self, bank: SkillBank):
        """store_single raises ValueError when dedup rejects."""
        bank.store_single("alpha skill", tier="general")
        with pytest.raises(ValueError, match="too similar"):
            bank.store_single("alpha skill v2", tier="general")


# ═══════════════════════════════════════════════════════════════════════════
# Success correlation tracking
# ═══════════════════════════════════════════════════════════════════════════


class TestSuccessCorrelation:
    def test_evolve_updates_correlation_on_success(self, bank: SkillBank):
        """When a colony succeeds, retrieved skills get their correlation boosted."""
        bank.store([_make_skill(content="alpha skill")])
        sid = bank.skills[0].skill_id

        outcomes = [{"skill_ids": [sid], "success": True}]
        bank.evolve(colony_outcomes=outcomes)

        # Correlation should have increased from 0.0 toward 1.0
        assert bank.skills[0].success_correlation > 0.0

    def test_evolve_updates_correlation_on_failure(self, bank: SkillBank):
        """When a colony fails, retrieved skills keep low correlation."""
        bank.store([_make_skill(content="alpha skill")])
        sid = bank.skills[0].skill_id

        outcomes = [{"skill_ids": [sid], "success": False}]
        bank.evolve(colony_outcomes=outcomes)

        # Correlation should stay at 0.0 (started at 0.0, EMA toward 0.0)
        assert bank.skills[0].success_correlation == 0.0

    def test_correlation_clamped(
        self, storage_file: Path, embedder: FakeEmbedder
    ):
        """success_correlation never exceeds [0.0, 1.0]."""
        cfg = _default_config(evolution_interval=100)
        bank = SkillBank(storage_path=storage_file, config=cfg, embedder=embedder)
        bank.store([_make_skill(content="alpha skill")])
        sid = bank.skills[0].skill_id

        # Many successful outcomes
        for _ in range(50):
            bank.evolve(colony_outcomes=[{"skill_ids": [sid], "success": True}])

        assert 0.0 <= bank.skills[0].success_correlation <= 1.0


# ═══════════════════════════════════════════════════════════════════════════
# EvolutionReport model
# ═══════════════════════════════════════════════════════════════════════════


class TestEvolutionReport:
    def test_evolution_report_fields(self):
        report = EvolutionReport(
            evolved=True,
            pruned=3,
            flagged_for_revision=["a", "b"],
            total_skills=10,
        )
        assert report.evolved is True
        assert report.pruned == 3
        assert report.flagged_for_revision == ["a", "b"]
        assert report.total_skills == 10

    def test_evolution_report_defaults(self):
        report = EvolutionReport(evolved=False)
        assert report.pruned == 0
        assert report.flagged_for_revision == []
        assert report.total_skills == 0
        assert report.reason is None
