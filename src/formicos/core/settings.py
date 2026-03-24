"""Configuration loading for FormicOS.

Reads YAML config files, interpolates environment variables,
and validates against Pydantic v2 models. ADR-002 compliant.
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel

from formicos.core.events import CoordinationStrategyName
from formicos.core.types import CasteRecipe, ModelRecord

_ENV_PATTERN = re.compile(r"\$\{([^}:]+)(?::([^}]*))?\}")


def _interpolate_env(value: str) -> str:
    """Replace ``${VAR:default}`` patterns with environment variable values."""

    def _replace(match: re.Match[str]) -> str:
        var_name = match.group(1)
        default = match.group(2)
        env_val = os.environ.get(var_name)
        if env_val is not None:
            return env_val
        return default if default is not None else match.group(0)

    return _ENV_PATTERN.sub(_replace, value)


def _interpolate_recursive(data: Any) -> Any:  # noqa: ANN401
    """Walk a nested dict/list and interpolate all string values."""
    if isinstance(data, str):
        return _interpolate_env(data)
    if isinstance(data, dict):
        return {str(k): _interpolate_recursive(v) for k, v in data.items()}  # pyright: ignore[reportUnknownVariableType,reportUnknownArgumentType]
    if isinstance(data, list):
        return [_interpolate_recursive(item) for item in data]  # pyright: ignore[reportUnknownVariableType]
    return data


# --- Config section models ---

class SystemConfig(BaseModel):
    """System-level host/port/data configuration."""
    host: str
    port: int
    data_dir: str


class ModelDefaults(BaseModel):
    """Default model assignments per caste."""
    queen: str
    coder: str
    reviewer: str
    researcher: str
    archivist: str


class ModelsConfig(BaseModel):
    """Model defaults and registry."""
    defaults: ModelDefaults
    registry: list[ModelRecord]


class EmbeddingConfig(BaseModel):
    """Embedding model configuration."""
    model: str
    dimensions: int


class GovernanceConfig(BaseModel):
    """Colony governance constraints."""
    max_rounds_per_colony: int
    stall_detection_window: int
    convergence_threshold: float
    default_budget_per_colony: float
    max_redirects_per_colony: int = 1


class ModelRoutingEntry(BaseModel):
    """Per-caste model override for a specific phase. Null = inherit cascade."""
    queen: str | None = None
    coder: str | None = None
    reviewer: str | None = None
    researcher: str | None = None
    archivist: str | None = None


class RoutingConfig(BaseModel):
    """Pheromone routing + compute routing parameters."""
    default_strategy: CoordinationStrategyName
    tau_threshold: float
    k_in_cap: int
    pheromone_decay_rate: float
    pheromone_reinforce_rate: float
    model_routing: dict[str, ModelRoutingEntry] = {}


class TierBudgets(BaseModel):
    """Per-tier token budgets for context assembly (ADR-008)."""
    goal: int = 500
    routed_outputs: int = 1500
    max_per_source: int = 500
    merge_summaries: int = 500
    prev_round_summary: int = 500
    skill_bank: int = 800


class ContextConfig(BaseModel):
    """Tiered context assembly configuration (ADR-008)."""
    total_budget_tokens: int = 4000
    tier_budgets: TierBudgets = TierBudgets()
    compaction_threshold: int = 500


class SystemSettings(BaseModel):
    """Top-level validated system configuration."""
    system: SystemConfig
    models: ModelsConfig
    embedding: EmbeddingConfig
    governance: GovernanceConfig
    routing: RoutingConfig
    context: ContextConfig = ContextConfig()


class CasteRecipeSet(BaseModel):
    """Validated set of caste recipes keyed by caste identifier."""
    castes: dict[str, CasteRecipe]


# --- Pre-processing ---

def _enrich_registry(raw: dict[str, Any]) -> dict[str, Any]:
    """Derive missing ``provider`` field on registry entries from ``address``."""
    for entry in raw.get("models", {}).get("registry", []):
        if "provider" not in entry and "address" in entry:
            addr: str = entry["address"]
            entry["provider"] = addr.split("/", 1)[0] if "/" in addr else addr
    return raw


# --- Public loaders ---

def load_config(path: Path | str) -> SystemSettings:
    """Read a YAML config file, interpolate env vars, and validate."""
    with Path(path).open("r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    raw = _interpolate_recursive(raw)
    raw = _enrich_registry(raw)
    return SystemSettings.model_validate(raw)


def load_castes(path: Path | str) -> CasteRecipeSet:
    """Read a YAML caste recipes file and validate."""
    with Path(path).open("r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    return CasteRecipeSet.model_validate(raw)


def save_model_registry(
    config_path: Path | str, settings: SystemSettings,
) -> None:
    """Write updated model registry back to the config YAML.

    Re-reads the raw YAML, replaces the ``models.registry`` list with the
    current in-memory records, and writes the file back.  Other sections
    (system, embedding, governance, routing, etc.) are preserved.
    """
    p = Path(config_path)
    with p.open("r", encoding="utf-8") as fh:
        raw: dict[str, Any] = yaml.safe_load(fh) or {}

    registry_dicts: list[dict[str, Any]] = []
    for m in settings.models.registry:
        entry = m.model_dump(exclude_defaults=False)
        # Drop provider — it is derived from address at load time
        entry.pop("provider", None)
        # Drop status — runtime-only field
        if entry.get("status") == "available":
            entry.pop("status", None)
        registry_dicts.append(entry)

    raw.setdefault("models", {})["registry"] = registry_dicts

    with p.open("w", encoding="utf-8") as fh:
        yaml.dump(
            raw, fh,
            default_flow_style=False,
            sort_keys=False,
            allow_unicode=True,
        )


def save_castes(path: Path | str, recipe_set: CasteRecipeSet) -> None:
    """Write a CasteRecipeSet back to YAML, preserving multiline strings."""
    data: dict[str, Any] = {"castes": {}}
    for caste_id, recipe in recipe_set.castes.items():
        entry = recipe.model_dump(exclude_defaults=False)
        # Omit deprecated/empty fields to keep backward-compatible YAML
        if entry.get("model_override") is None:
            entry.pop("model_override", None)
        if not entry.get("tier_models"):
            entry.pop("tier_models", None)
        data["castes"][caste_id] = entry

    def _str_representer(
        dumper: yaml.Dumper, val: str,
    ) -> yaml.ScalarNode:
        if "\n" in val:
            return dumper.represent_scalar(  # type: ignore[return-value]
                "tag:yaml.org,2002:str", val, style="|",
            )
        return dumper.represent_scalar("tag:yaml.org,2002:str", val)  # type: ignore[return-value]

    custom_dumper = type("_CasteDumper", (yaml.Dumper,), {})
    custom_dumper.add_representer(str, _str_representer)  # type: ignore[arg-type]

    header = (
        "# FormicOS Caste Recipes\n"
        "# Each caste defines a role that an agent can play in a colony.\n"
        "# Model assignment comes from the cascade "
        "(formicos.yaml > workspace override).\n\n"
    )
    with Path(path).open("w", encoding="utf-8") as fh:
        fh.write(header)
        yaml.dump(
            data, fh,
            Dumper=custom_dumper,
            default_flow_style=False,
            sort_keys=False,
            allow_unicode=True,
        )
