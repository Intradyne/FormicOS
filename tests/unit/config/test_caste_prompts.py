"""Tests for worker caste prompt rewrites (Wave 33.5 Team 1)."""

from __future__ import annotations

from pathlib import Path

import yaml


def _load_recipes() -> dict:
    raw = yaml.safe_load(Path("config/caste_recipes.yaml").read_text())
    return raw["castes"]


class TestWorkerCastePrompts:
    """Verify rewritten prompts meet specifications."""

    def test_prompt_line_counts(self) -> None:
        recipes = _load_recipes()
        for caste_name in ["coder", "reviewer", "researcher", "archivist"]:
            prompt = recipes[caste_name]["system_prompt"]
            lines = [line for line in prompt.strip().split("\n") if line.strip()]
            assert 15 <= len(lines) <= 50, (
                f"{caste_name}: {len(lines)} lines (expected 15-50)"
            )

    def test_all_tools_mentioned(self) -> None:
        recipes = _load_recipes()
        for caste_name in ["coder", "reviewer", "researcher", "archivist"]:
            prompt = recipes[caste_name]["system_prompt"]
            tools = recipes[caste_name]["tools"]
            for tool in tools:
                assert tool in prompt, f"{caste_name}: missing tool {tool}"

    def test_no_extra_tools_mentioned(self) -> None:
        """Prompts should not mention tools the caste does not have."""
        recipes = _load_recipes()
        all_worker_tools = {
            "memory_search", "memory_write", "code_execute",
            "knowledge_detail", "transcript_search", "artifact_inspect",
        }
        for caste_name in ["coder", "reviewer", "researcher", "archivist"]:
            prompt = recipes[caste_name]["system_prompt"]
            tools = set(recipes[caste_name]["tools"])
            for tool in all_worker_tools - tools:
                # Tool name should not appear as a standalone reference
                assert f"- {tool}:" not in prompt, (
                    f"{caste_name}: mentions tool {tool} it does not have"
                )

    def test_confidence_awareness(self) -> None:
        recipes = _load_recipes()
        for caste_name in ["coder", "reviewer", "researcher", "archivist"]:
            prompt = recipes[caste_name]["system_prompt"].lower()
            assert "confidence" in prompt, f"{caste_name}: missing confidence awareness"

    def test_knowledge_awareness(self) -> None:
        recipes = _load_recipes()
        for caste_name in ["coder", "reviewer", "researcher", "archivist"]:
            prompt = recipes[caste_name]["system_prompt"].lower()
            assert "knowledge" in prompt, f"{caste_name}: missing knowledge awareness"

    def test_credential_scanning_awareness(self) -> None:
        recipes = _load_recipes()
        for caste_name in ["coder", "reviewer", "researcher", "archivist"]:
            prompt = recipes[caste_name]["system_prompt"].lower()
            assert "credential" in prompt or "secret" in prompt, (
                f"{caste_name}: missing credential/secret awareness"
            )

    def test_queen_prompt_unchanged(self) -> None:
        recipes = _load_recipes()
        queen_prompt = recipes["queen"]["system_prompt"]
        assert "You are the Queen" in queen_prompt

    def test_archivist_decay_class_awareness(self) -> None:
        prompt = _load_recipes()["archivist"]["system_prompt"]
        assert "ephemeral" in prompt
        assert "stable" in prompt
        assert "permanent" in prompt

    def test_archivist_beta_prior_awareness(self) -> None:
        prompt = _load_recipes()["archivist"]["system_prompt"]
        assert "Beta(5,5)" in prompt
