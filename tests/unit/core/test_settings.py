"""Tests for formicos.core.settings — config loading and env interpolation."""

from __future__ import annotations

import os
import shutil
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

from formicos.core.settings import (
    CasteRecipeSet,
    ContextConfig,
    SystemSettings,
    TierBudgets,
    _interpolate_env,
    load_castes,
    load_config,
)

ROOT = Path(__file__).resolve().parents[3]
CONFIG_PATH = ROOT / "config" / "formicos.yaml"
CASTES_PATH = ROOT / "config" / "caste_recipes.yaml"


@contextmanager
def _repo_temp_dir() -> Path:
    """Create a repo-local temp dir to avoid Windows temp ACL issues."""
    base = ROOT / ".tmp_pytest"
    base.mkdir(exist_ok=True)
    path = base / f"core-settings-{uuid4().hex}"
    path.mkdir()
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


# ---------------------------------------------------------------------------
# load_config
# ---------------------------------------------------------------------------


def test_load_config() -> None:
    settings = load_config(CONFIG_PATH)
    assert isinstance(settings, SystemSettings)

    assert settings.system.host == "0.0.0.0"
    assert settings.system.port == 8080

    assert settings.models.defaults.queen == "anthropic/claude-sonnet-4-6"
    assert settings.models.defaults.archivist == "anthropic/claude-haiku-4-5"
    assert len(settings.models.registry) == 46
    assert settings.models.registry[0].address == "llama-cpp/qwen3.5-35b"
    assert settings.models.registry[0].provider == "llama-cpp"

    assert settings.embedding.model == "nomic-ai/nomic-embed-text-v1.5"
    assert settings.embedding.dimensions == 768

    assert settings.governance.max_rounds_per_colony == 25
    assert settings.governance.default_budget_per_colony == 1.0

    assert settings.routing.default_strategy == "stigmergic"
    assert settings.routing.tau_threshold == 0.35
    assert settings.routing.k_in_cap == 5


# ---------------------------------------------------------------------------
# load_castes
# ---------------------------------------------------------------------------


def test_load_castes() -> None:
    recipe_set = load_castes(CASTES_PATH)
    assert isinstance(recipe_set, CasteRecipeSet)
    assert set(recipe_set.castes.keys()) == {
        "queen",
        "coder",
        "reviewer",
        "researcher",
        "archivist",
        "forager",
    }
    assert recipe_set.castes["coder"].temperature == 0.0
    assert recipe_set.castes["queen"].max_tokens == 4096


# ---------------------------------------------------------------------------
# env-var interpolation
# ---------------------------------------------------------------------------


def test_env_interpolation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FORMICOS_TEST_VAR", "override_value")
    result = _interpolate_env("${FORMICOS_TEST_VAR:fallback}")
    assert result == "override_value"


def test_env_interpolation_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FORMICOS_DATA_DIR", raising=False)
    result = _interpolate_env("${FORMICOS_DATA_DIR:./data}")
    assert result == "./data"


# ---------------------------------------------------------------------------
# validation rejects malformed config
# ---------------------------------------------------------------------------


def test_invalid_config_rejected() -> None:
    with _repo_temp_dir() as tmp_path:
        bad_yaml = tmp_path / "bad.yaml"
        bad_yaml.write_text(
            "system:\n  host: 123\n  port: not_an_int\n",
            encoding="utf-8",
        )
        with pytest.raises(ValidationError):
            load_config(bad_yaml)


# ---------------------------------------------------------------------------
# ContextConfig (ADR-008)
# ---------------------------------------------------------------------------


def test_context_config_defaults() -> None:
    cfg = ContextConfig()
    assert cfg.total_budget_tokens == 4000
    assert cfg.compaction_threshold == 500
    assert cfg.tier_budgets.goal == 500
    assert cfg.tier_budgets.routed_outputs == 1500
    assert cfg.tier_budgets.skill_bank == 800


def test_context_config_from_yaml() -> None:
    settings = load_config(CONFIG_PATH)
    ctx = settings.context
    assert ctx.total_budget_tokens == 32000
    assert ctx.tier_budgets.goal == 2400
    assert ctx.tier_budgets.routed_outputs == 12800
    assert ctx.tier_budgets.max_per_source == 3600
    assert ctx.tier_budgets.merge_summaries == 3600
    assert ctx.tier_budgets.prev_round_summary == 3600
    assert ctx.tier_budgets.skill_bank == 6000
    assert ctx.compaction_threshold == 2400


def test_context_config_missing_uses_defaults() -> None:
    """Config without context section should still parse with defaults."""
    with _repo_temp_dir() as tmp_path:
        minimal = tmp_path / "minimal.yaml"
        minimal.write_text(
            "system:\n  host: '0.0.0.0'\n  port: 8080\n  data_dir: ./data\n"
            "models:\n  defaults:\n    queen: 'x/y'\n    coder: 'x/y'\n"
            "    reviewer: 'x/y'\n    researcher: 'x/y'\n    archivist: 'x/y'\n"
            "  registry: []\n"
            "embedding:\n  model: test\n  dimensions: 384\n"
            "governance:\n  max_rounds_per_colony: 10\n  stall_detection_window: 3\n"
            "  convergence_threshold: 0.95\n  default_budget_per_colony: 1.0\n"
            "routing:\n  default_strategy: sequential\n  tau_threshold: 0.35\n"
            "  k_in_cap: 5\n  pheromone_decay_rate: 0.1\n  pheromone_reinforce_rate: 0.3\n",
            encoding="utf-8",
        )
        settings = load_config(minimal)
        assert settings.context.total_budget_tokens == 4000
        assert isinstance(settings.context.tier_budgets, TierBudgets)
