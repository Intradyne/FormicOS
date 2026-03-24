"""Entry sub-type tests (Wave 34 B3).

Validates:
- EntrySubType enum members and values
- Sub-type classification in extraction prompts
- Harvest type → EntrySubType mapping
- Sub-type flow through build_memory_entries
- Default sub_type is None (existing entries unaffected)
"""

from __future__ import annotations

from formicos.core.types import EntrySubType, MemoryEntry, MemoryEntryType


class TestEntrySubTypeEnum:
    """Validate the EntrySubType StrEnum."""

    def test_skill_sub_types(self) -> None:
        assert EntrySubType.technique == "technique"
        assert EntrySubType.pattern == "pattern"
        assert EntrySubType.anti_pattern == "anti_pattern"

    def test_experience_sub_types(self) -> None:
        assert EntrySubType.decision == "decision"
        assert EntrySubType.convention == "convention"
        assert EntrySubType.learning == "learning"
        assert EntrySubType.bug == "bug"

    def test_all_eight_members(self) -> None:
        assert len(EntrySubType) == 8


class TestMemoryEntrySubType:
    """Validate sub_type field on MemoryEntry."""

    def test_default_sub_type_is_none(self) -> None:
        entry = MemoryEntry(
            id="mem-test-s-0",
            entry_type=MemoryEntryType.skill,
            title="Test",
            content="Test content",
            source_colony_id="col-1",
            source_artifact_ids=[],
        )
        assert entry.sub_type is None

    def test_sub_type_set_on_skill(self) -> None:
        entry = MemoryEntry(
            id="mem-test-s-0",
            entry_type=MemoryEntryType.skill,
            title="Test",
            content="Test content",
            source_colony_id="col-1",
            source_artifact_ids=[],
            sub_type=EntrySubType.pattern,
        )
        assert entry.sub_type == EntrySubType.pattern

    def test_sub_type_set_on_experience(self) -> None:
        entry = MemoryEntry(
            id="mem-test-e-0",
            entry_type=MemoryEntryType.experience,
            title="Test",
            content="Test content",
            source_colony_id="col-1",
            source_artifact_ids=[],
            sub_type=EntrySubType.bug,
        )
        assert entry.sub_type == EntrySubType.bug

    def test_sub_type_serializes_to_dict(self) -> None:
        entry = MemoryEntry(
            id="mem-test-s-0",
            entry_type=MemoryEntryType.skill,
            title="Test",
            content="Test content",
            source_colony_id="col-1",
            source_artifact_ids=[],
            sub_type=EntrySubType.technique,
        )
        d = entry.model_dump()
        assert d["sub_type"] == "technique"

    def test_none_sub_type_serializes_to_none(self) -> None:
        entry = MemoryEntry(
            id="mem-test-s-0",
            entry_type=MemoryEntryType.skill,
            title="Test",
            content="Test content",
            source_colony_id="col-1",
            source_artifact_ids=[],
        )
        d = entry.model_dump()
        assert d["sub_type"] is None


class TestExtractionPromptSubType:
    """Verify extraction prompt includes sub_type classification."""

    def test_extraction_prompt_includes_sub_type_for_skills(self) -> None:
        from formicos.surface.memory_extractor import build_extraction_prompt

        prompt = build_extraction_prompt(
            task="test task",
            final_output="test output",
            artifacts=[],
            colony_status="completed",
            failure_reason=None,
            contract_result=None,
        )
        assert '"sub_type"' in prompt
        assert '"technique"' in prompt
        assert '"pattern"' in prompt
        assert '"anti_pattern"' in prompt

    def test_extraction_prompt_includes_sub_type_for_experiences(self) -> None:
        from formicos.surface.memory_extractor import build_extraction_prompt

        prompt = build_extraction_prompt(
            task="test task",
            final_output="test output",
            artifacts=[],
            colony_status="completed",
            failure_reason=None,
            contract_result=None,
        )
        assert '"decision"' in prompt
        assert '"convention"' in prompt
        assert '"learning"' in prompt
        assert '"bug"' in prompt

    def test_failed_extraction_prompt_includes_sub_type(self) -> None:
        from formicos.surface.memory_extractor import build_extraction_prompt

        prompt = build_extraction_prompt(
            task="test task",
            final_output="test output",
            artifacts=[],
            colony_status="failed",
            failure_reason="out of budget",
            contract_result=None,
        )
        assert '"sub_type"' in prompt


class TestHarvestSubTypeMapping:
    """Verify harvest types map to EntrySubType values."""

    def test_harvest_sub_type_map_exists(self) -> None:
        from formicos.surface.memory_extractor import HARVEST_SUB_TYPE_MAP

        assert isinstance(HARVEST_SUB_TYPE_MAP, dict)

    def test_bug_maps_to_bug(self) -> None:
        from formicos.surface.memory_extractor import HARVEST_SUB_TYPE_MAP

        assert HARVEST_SUB_TYPE_MAP["bug"] == "bug"

    def test_decision_maps_to_decision(self) -> None:
        from formicos.surface.memory_extractor import HARVEST_SUB_TYPE_MAP

        assert HARVEST_SUB_TYPE_MAP["decision"] == "decision"

    def test_convention_maps_to_convention(self) -> None:
        from formicos.surface.memory_extractor import HARVEST_SUB_TYPE_MAP

        assert HARVEST_SUB_TYPE_MAP["convention"] == "convention"

    def test_learning_maps_to_learning(self) -> None:
        from formicos.surface.memory_extractor import HARVEST_SUB_TYPE_MAP

        assert HARVEST_SUB_TYPE_MAP["learning"] == "learning"

    def test_all_harvest_types_have_valid_sub_types(self) -> None:
        from formicos.surface.memory_extractor import HARVEST_SUB_TYPE_MAP

        valid = {e.value for e in EntrySubType}
        for harvest_type, sub_type in HARVEST_SUB_TYPE_MAP.items():
            assert sub_type in valid, f"Harvest type '{harvest_type}' maps to invalid sub_type '{sub_type}'"


class TestBuildMemoryEntriesSubType:
    """Verify sub_type flows through build_memory_entries."""

    def test_skill_with_sub_type(self) -> None:
        from formicos.surface.memory_extractor import build_memory_entries

        raw = {
            "skills": [{
                "title": "Test Skill",
                "content": "A" * 40,
                "when_to_use": "testing",
                "domains": ["python"],
                "tool_refs": [],
                "sub_type": "technique",
            }],
            "experiences": [],
        }
        entries = build_memory_entries(raw, "col-1", "ws-1", [], "completed")
        assert len(entries) == 1
        assert entries[0]["sub_type"] == "technique"

    def test_experience_with_sub_type(self) -> None:
        from formicos.surface.memory_extractor import build_memory_entries

        raw = {
            "skills": [],
            "experiences": [{
                "title": "Test Bug",
                "content": "B" * 40,
                "trigger": "testing",
                "domains": ["python"],
                "tool_refs": [],
                "polarity": "negative",
                "sub_type": "bug",
            }],
        }
        entries = build_memory_entries(raw, "col-1", "ws-1", [], "completed")
        assert len(entries) == 1
        assert entries[0]["sub_type"] == "bug"

    def test_missing_sub_type_defaults_to_none(self) -> None:
        from formicos.surface.memory_extractor import build_memory_entries

        raw = {
            "skills": [{
                "title": "Test Skill",
                "content": "C" * 40,
                "when_to_use": "testing",
                "domains": [],
                "tool_refs": [],
            }],
            "experiences": [],
        }
        entries = build_memory_entries(raw, "col-1", "ws-1", [], "completed")
        assert len(entries) == 1
        assert entries[0]["sub_type"] is None

    def test_invalid_sub_type_defaults_to_none(self) -> None:
        from formicos.surface.memory_extractor import build_memory_entries

        raw = {
            "skills": [{
                "title": "Test Skill",
                "content": "D" * 40,
                "when_to_use": "testing",
                "domains": [],
                "tool_refs": [],
                "sub_type": "not_a_real_type",
            }],
            "experiences": [],
        }
        entries = build_memory_entries(raw, "col-1", "ws-1", [], "completed")
        assert len(entries) == 1
        assert entries[0]["sub_type"] is None

    def test_filters_environment_noise_entries(self) -> None:
        from formicos.surface.memory_extractor import build_memory_entries

        raw = {
            "skills": [],
            "experiences": [{
                "title": "Workspace Issue",
                "content": (
                    "The workspace directory remains unconfigured despite repeated "
                    "attempts to create files in the current environment."
                ),
                "trigger": "tooling",
                "domains": ["python"],
                "tool_refs": [],
                "polarity": "negative",
                "sub_type": "bug",
            }],
        }
        entries = build_memory_entries(raw, "col-1", "ws-1", [], "completed")
        assert entries == []
