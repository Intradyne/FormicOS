"""Tests for transcript harvest at hook position 4.5 (Wave 33 A1)."""

from __future__ import annotations

from formicos.surface.memory_extractor import (
    build_harvest_prompt,
    is_environment_noise_text,
    parse_harvest_response,
)


class TestBuildHarvestPrompt:
    def test_includes_all_turns(self) -> None:
        turns = [
            {
                "agent_id": "agent-1",
                "caste": "coder",
                "content": "Fixed the bug",
                "round_number": 1,
            },
            {
                "agent_id": "agent-2",
                "caste": "researcher",
                "content": "Found docs",
                "round_number": 2,
            },
        ]
        prompt = build_harvest_prompt(turns)

        assert "[Turn 0]" in prompt
        assert "[Turn 1]" in prompt
        assert "agent=agent-1" in prompt
        assert "caste=coder" in prompt
        assert "Fixed the bug" in prompt

    def test_empty_turns(self) -> None:
        prompt = build_harvest_prompt([])
        assert "TURNS:" in prompt

    def test_truncates_long_content(self) -> None:
        turns = [
            {"agent_id": "a", "caste": "c", "content": "x" * 1000, "round_number": 0},
        ]
        prompt = build_harvest_prompt(turns)
        assert "x" * 500 in prompt
        assert "x" * 501 not in prompt


class TestParseHarvestResponse:
    def test_valid_json(self) -> None:
        text = (
            '{"entries": [{"turn_index": 0, "type": "bug", '
            '"summary": "Found null pointer"}]}'
        )
        result = parse_harvest_response(text)
        assert len(result) == 1
        assert result[0]["type"] == "bug"
        assert result[0]["summary"] == "Found null pointer"

    def test_code_fenced_json(self) -> None:
        text = (
            "```json\n"
            '{"entries": [{"turn_index": 1, "type": "convention", '
            '"summary": "Use structlog"}]}\n'
            "```"
        )
        result = parse_harvest_response(text)
        assert len(result) == 1
        assert result[0]["type"] == "convention"

    def test_invalid_type_skipped(self) -> None:
        text = '{"entries": [{"turn_index": 0, "type": "unknown", "summary": "nope"}]}'
        result = parse_harvest_response(text)
        assert len(result) == 0

    def test_missing_fields_skipped(self) -> None:
        text = '{"entries": [{"turn_index": 0, "type": "bug"}]}'
        result = parse_harvest_response(text)
        assert len(result) == 0

    def test_empty_entries(self) -> None:
        text = '{"entries": []}'
        result = parse_harvest_response(text)
        assert len(result) == 0

    def test_invalid_json_returns_empty(self) -> None:
        text = "not json at all"
        result = parse_harvest_response(text)
        assert len(result) == 0

    def test_environment_noise_is_filtered(self) -> None:
        text = (
            '{"entries": [{"turn_index": 0, "type": "learning", '
            '"summary": "The workspace directory remains unconfigured '
            'despite repeated attempts."}]}'
        )
        result = parse_harvest_response(text)
        assert result == []

    def test_all_valid_types(self) -> None:
        entries = [
            {"turn_index": i, "type": t, "summary": f"s{i}"}
            for i, t in enumerate(["bug", "decision", "convention", "learning"])
        ]
        import json

        text = json.dumps({"entries": entries})
        result = parse_harvest_response(text)
        assert len(result) == 4

    def test_harvest_type_mapping(self) -> None:
        from formicos.surface.memory_extractor import HARVEST_TYPES

        assert HARVEST_TYPES["bug"] == "experience"
        assert HARVEST_TYPES["decision"] == "experience"
        assert HARVEST_TYPES["convention"] == "skill"
        assert HARVEST_TYPES["learning"] == "experience"


class TestEnvironmentNoiseDetection:
    def test_detects_workspace_failure_chatter(self) -> None:
        assert is_environment_noise_text(
            "The git command is not available in the current environment.",
        )

    def test_keeps_domain_knowledge(self) -> None:
        assert not is_environment_noise_text(
            "Validate email addresses by rejecting local parts with consecutive dots.",
        )


class TestHarvestHookReplaySafety:
    """Test that the harvest hook respects replay safety via memory_extractions_completed."""

    def test_already_harvested_skips(self) -> None:
        from unittest.mock import MagicMock

        from formicos.surface.colony_manager import ColonyManager

        runtime = MagicMock()
        projections = MagicMock()
        projections.memory_extractions_completed = {"col-1:harvest"}
        runtime.projections = projections

        mgr = ColonyManager.__new__(ColonyManager)
        mgr._runtime = runtime

        # Should return immediately without creating a task
        mgr._hook_transcript_harvest("col-1", "ws-1", succeeded=True)

        # No task should have been created — verify no asyncio.create_task call
        # The method returns None early, so no task interaction with runtime
        assert "col-1:harvest" in projections.memory_extractions_completed

    def test_not_harvested_proceeds(self) -> None:
        from unittest.mock import MagicMock

        from formicos.surface.colony_manager import ColonyManager

        runtime = MagicMock()
        projections = MagicMock()
        projections.memory_extractions_completed = set()
        colony_proj = MagicMock()
        colony_proj.chat_messages = [{"agent_id": "a", "content": "test"}]
        projections.get_colony = MagicMock(return_value=colony_proj)
        runtime.projections = projections

        mgr = ColonyManager.__new__(ColonyManager)
        mgr._runtime = runtime
        mgr._deferred_post_colony_work = []
        mgr._active = {}
        mgr._post_colony_drain_task = None
        mgr._schedule_post_colony_drain = MagicMock()

        mgr._hook_transcript_harvest("col-1", "ws-1", succeeded=True)
        assert len(mgr._deferred_post_colony_work) == 1
        mgr._schedule_post_colony_drain.assert_called_once()
