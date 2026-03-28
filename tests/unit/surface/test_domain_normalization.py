"""Tests for Wave 67 domain normalization in extraction prompt."""

from __future__ import annotations

from typing import Any

from formicos.surface.memory_extractor import build_extraction_prompt


def _entries_with_domains(*domain_lists: list[str]) -> list[dict[str, Any]]:
    """Build minimal existing entries with specified domain tag lists."""
    return [
        {
            "id": f"mem-{i}",
            "title": f"entry {i}",
            "confidence": 0.6,
            "access_count": 1,
            "content": "some content",
            "domains": domains,
        }
        for i, domains in enumerate(domain_lists)
    ]


class TestDomainNormalization:
    def test_extraction_prompt_includes_existing_domains(self) -> None:
        entries = _entries_with_domains(
            ["python", "testing"],
            ["auth"],
            ["python", "networking"],
        )
        prompt = build_extraction_prompt(
            task="test task",
            final_output="test output",
            artifacts=[],
            colony_status="completed",
            failure_reason=None,
            contract_result=None,
            existing_entries=entries,
        )
        assert "Use one of these existing domain tags" in prompt
        assert "auth" in prompt
        assert "python" in prompt
        assert "testing" in prompt
        assert "networking" in prompt

    def test_extraction_prompt_caps_domains_at_20(self) -> None:
        # Create entries with 30 unique domains
        domains_per_entry = [
            [f"domain_{i}", f"domain_{i + 10}", f"domain_{i + 20}"]
            for i in range(10)
        ]
        entries = _entries_with_domains(*domains_per_entry)
        prompt = build_extraction_prompt(
            task="test task",
            final_output="test output",
            artifacts=[],
            colony_status="completed",
            failure_reason=None,
            contract_result=None,
            existing_entries=entries,
        )
        assert "Use one of these existing domain tags" in prompt
        # Count how many domain_N tags appear in the hint line
        hint_line = [
            line for line in prompt.split("\n")
            if "Use one of these existing domain tags" in line
        ][0]
        domain_count = hint_line.count("domain_")
        assert domain_count <= 20

    def test_extraction_prompt_no_domains_without_existing(self) -> None:
        prompt = build_extraction_prompt(
            task="test task",
            final_output="test output",
            artifacts=[],
            colony_status="completed",
            failure_reason=None,
            contract_result=None,
            existing_entries=None,
        )
        assert "Use one of these existing domain tags" not in prompt

    def test_extraction_prompt_no_domains_with_empty_entries(self) -> None:
        prompt = build_extraction_prompt(
            task="test task",
            final_output="test output",
            artifacts=[],
            colony_status="completed",
            failure_reason=None,
            contract_result=None,
            existing_entries=[],
        )
        assert "Use one of these existing domain tags" not in prompt

    def test_extraction_prompt_no_hint_when_entries_lack_domains(self) -> None:
        entries = _entries_with_domains([], [])
        prompt = build_extraction_prompt(
            task="test task",
            final_output="test output",
            artifacts=[],
            colony_status="completed",
            failure_reason=None,
            contract_result=None,
            existing_entries=entries,
        )
        assert "Use one of these existing domain tags" not in prompt
