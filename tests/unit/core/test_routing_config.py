"""Tests for ModelRoutingEntry and RoutingConfig model_routing (ADR-012)."""

from __future__ import annotations

from pathlib import Path

from formicos.core.settings import (
    ModelRoutingEntry,
    RoutingConfig,
    load_config,
)

ROOT = Path(__file__).resolve().parents[3]
CONFIG_PATH = ROOT / "config" / "formicos.yaml"


# ---------------------------------------------------------------------------
# ModelRoutingEntry
# ---------------------------------------------------------------------------


def test_model_routing_entry_defaults_all_none() -> None:
    entry = ModelRoutingEntry()
    assert entry.queen is None
    assert entry.coder is None
    assert entry.reviewer is None
    assert entry.researcher is None
    assert entry.archivist is None


def test_model_routing_entry_partial_override() -> None:
    entry = ModelRoutingEntry(queen="anthropic/claude-sonnet-4.6", coder="anthropic/claude-sonnet-4.6")
    assert entry.queen == "anthropic/claude-sonnet-4.6"
    assert entry.coder == "anthropic/claude-sonnet-4.6"
    assert entry.reviewer is None


def test_model_routing_entry_all_set() -> None:
    entry = ModelRoutingEntry(
        queen="a/1", coder="a/2", reviewer="a/3",
        researcher="a/4", archivist="a/5",
    )
    assert entry.queen == "a/1"
    assert entry.archivist == "a/5"


# ---------------------------------------------------------------------------
# RoutingConfig with model_routing
# ---------------------------------------------------------------------------


def test_routing_config_empty_model_routing_default() -> None:
    cfg = RoutingConfig(
        default_strategy="sequential",
        tau_threshold=0.35,
        k_in_cap=5,
        pheromone_decay_rate=0.1,
        pheromone_reinforce_rate=0.3,
    )
    assert cfg.model_routing == {}


def test_routing_config_with_model_routing() -> None:
    cfg = RoutingConfig(
        default_strategy="sequential",
        tau_threshold=0.35,
        k_in_cap=5,
        pheromone_decay_rate=0.1,
        pheromone_reinforce_rate=0.3,
        model_routing={
            "execute": ModelRoutingEntry(
                coder="anthropic/claude-sonnet-4.6",
                reviewer="llama-cpp/gpt-4",
            ),
        },
    )
    assert "execute" in cfg.model_routing
    assert cfg.model_routing["execute"].coder == "anthropic/claude-sonnet-4.6"
    assert cfg.model_routing["execute"].reviewer == "llama-cpp/gpt-4"
    assert cfg.model_routing["execute"].queen is None


def test_routing_config_multiple_phases() -> None:
    cfg = RoutingConfig(
        default_strategy="sequential",
        tau_threshold=0.35,
        k_in_cap=5,
        pheromone_decay_rate=0.1,
        pheromone_reinforce_rate=0.3,
        model_routing={
            "execute": ModelRoutingEntry(coder="a/1"),
            "goal": ModelRoutingEntry(queen="a/2"),
        },
    )
    assert len(cfg.model_routing) == 2
    assert cfg.model_routing["goal"].queen == "a/2"
    assert cfg.model_routing["execute"].coder == "a/1"


# ---------------------------------------------------------------------------
# YAML config loading
# ---------------------------------------------------------------------------


def test_load_config_has_model_routing() -> None:
    settings = load_config(CONFIG_PATH)
    assert hasattr(settings.routing, "model_routing")
    assert isinstance(settings.routing.model_routing, dict)


def test_load_config_execute_phase_entries() -> None:
    settings = load_config(CONFIG_PATH)
    execute = settings.routing.model_routing.get("execute")
    assert execute is not None
    assert execute.queen == "llama-cpp/gpt-4"
    assert execute.coder == "llama-cpp/gpt-4"
    assert execute.reviewer == "openai/gpt-4o"


def test_load_config_goal_phase_entries() -> None:
    settings = load_config(CONFIG_PATH)
    goal = settings.routing.model_routing.get("goal")
    assert goal is not None
    assert goal.queen == "llama-cpp/gpt-4"
    assert goal.coder is None  # not set in YAML


def test_load_config_missing_phase_returns_none() -> None:
    settings = load_config(CONFIG_PATH)
    assert settings.routing.model_routing.get("compress") is None
