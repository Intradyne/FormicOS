"""Tests for memory_extractor.py curation features (Wave 59)."""

from __future__ import annotations

from typing import Any

from formicos.surface.memory_extractor import (
    build_extraction_prompt,
    parse_extraction_response,
)


def _existing_entries() -> list[dict[str, Any]]:
    return [
        {
            "id": "mem-col-42-s-0",
            "title": "Token bucket implementation",
            "confidence": 0.72,
            "access_count": 8,
            "primary_domain": "code_implementation",
            "content": "Implement rate limiting using a token bucket algorithm "
            "with configurable refill rate and burst capacity.",
        },
        {
            "id": "mem-col-30-e-1",
            "title": "Input validation convention",
            "confidence": 0.55,
            "access_count": 3,
            "primary_domain": "code_implementation",
            "content": "Always validate input types before processing to "
            "prevent runtime errors in downstream functions.",
        },
    ]


class TestCuratingPrompt:
    def test_curating_prompt_includes_existing_entries(self) -> None:
        prompt = build_extraction_prompt(
            task="implement auth endpoint",
            final_output="completed auth implementation",
            artifacts=[],
            colony_status="completed",
            failure_reason=None,
            contract_result=None,
            existing_entries=_existing_entries(),
        )
        assert "EXISTING ENTRIES" in prompt
        assert "mem-col-42-s-0" in prompt
        assert "Token bucket implementation" in prompt
        assert "conf: 0.72" in prompt
        assert "accessed: 8x" in prompt
        assert "actions" in prompt

    def test_curating_prompt_fallback_without_existing(self) -> None:
        prompt = build_extraction_prompt(
            task="implement something",
            final_output="done",
            artifacts=[],
            colony_status="completed",
            failure_reason=None,
            contract_result=None,
            existing_entries=None,
        )
        assert "EXISTING ENTRIES" not in prompt
        assert '"skills"' in prompt
        assert '"experiences"' in prompt

    def test_curating_prompt_empty_list_is_fallback(self) -> None:
        prompt = build_extraction_prompt(
            task="implement something",
            final_output="done",
            artifacts=[],
            colony_status="completed",
            failure_reason=None,
            contract_result=None,
            existing_entries=[],
        )
        assert "EXISTING ENTRIES" not in prompt


class TestActionParsing:
    def test_parse_actions_format(self) -> None:
        text = '{"actions": [{"type": "CREATE", "entry": {"title": "new"}}, {"type": "NOOP", "entry_id": "old-1"}]}'
        result = parse_extraction_response(text)
        assert "actions" in result
        assert len(result["actions"]) == 2
        assert result["actions"][0]["type"] == "CREATE"
        assert result["actions"][1]["type"] == "NOOP"

    def test_parse_legacy_format_fallback(self) -> None:
        text = '{"skills": [{"title": "s1", "content": "skill content"}], "experiences": []}'
        result = parse_extraction_response(text)
        assert "skills" in result
        assert len(result["skills"]) == 1

    def test_parse_refine_action(self) -> None:
        text = '{"actions": [{"type": "REFINE", "entry_id": "mem-1", "new_content": "improved content"}]}'
        result = parse_extraction_response(text)
        assert result["actions"][0]["type"] == "REFINE"
        assert result["actions"][0]["entry_id"] == "mem-1"

    def test_parse_merge_action(self) -> None:
        text = '{"actions": [{"type": "MERGE", "target_id": "t1", "source_id": "s1", "merged_content": "combined"}]}'
        result = parse_extraction_response(text)
        assert result["actions"][0]["type"] == "MERGE"

    def test_parse_mixed_format_prefers_actions(self) -> None:
        text = '{"actions": [{"type": "NOOP"}], "skills": [{"title": "ignored"}]}'
        result = parse_extraction_response(text)
        assert "actions" in result
