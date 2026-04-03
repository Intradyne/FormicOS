"""Tests for dynamic Queen toolset classifier (Wave 79 Track 1)."""

from __future__ import annotations

from formicos.surface.queen_runtime import classify_relevant_toolsets


class TestClassifyRelevantToolsets:
    """Tests for keyword-based toolset classification."""

    def test_always_includes_operations(self) -> None:
        result = classify_relevant_toolsets("anything at all")
        assert "operations" in result

    def test_status_query_minimal(self) -> None:
        result = classify_relevant_toolsets("what's the status?")
        assert "operations" in result

    def test_spawn_includes_colony(self) -> None:
        result = classify_relevant_toolsets("spawn a colony to fix auth")
        assert "colony" in result
        assert "planning" in result

    def test_file_edit_includes_workspace(self) -> None:
        result = classify_relevant_toolsets("edit the config file")
        assert "workspace" in result

    def test_search_includes_knowledge(self) -> None:
        result = classify_relevant_toolsets("search knowledge for embedding")
        assert "knowledge" in result

    def test_plan_includes_planning(self) -> None:
        result = classify_relevant_toolsets("create a plan for the milestone")
        assert "planning" in result

    def test_document_includes_documents(self) -> None:
        result = classify_relevant_toolsets("draft a summary of the work")
        assert "documents" in result

    def test_rollback_includes_safety(self) -> None:
        result = classify_relevant_toolsets("rollback the last edit")
        assert "safety" in result

    def test_note_includes_working_memory(self) -> None:
        result = classify_relevant_toolsets("write a working note")
        assert "working_memory" in result

    def test_analyze_includes_analysis(self) -> None:
        result = classify_relevant_toolsets("analyze colony performance")
        assert "analysis" in result

    def test_active_colonies_adds_colony_toolset(self) -> None:
        result = classify_relevant_toolsets("hello", active_colonies=3)
        assert "colony" in result

    def test_fallback_on_no_keywords(self) -> None:
        """When no keywords match, fallback includes colony+workspace+knowledge."""
        result = classify_relevant_toolsets("hello there")
        assert "colony" in result
        assert "workspace" in result
        assert "knowledge" in result

    def test_complex_message_multiple_toolsets(self) -> None:
        result = classify_relevant_toolsets(
            "spawn a colony to search knowledge and edit the file",
        )
        assert "colony" in result
        assert "knowledge" in result
        assert "workspace" in result
        assert "planning" in result

    def test_explicit_multi_file_build_gets_colony_and_planning(self) -> None:
        result = classify_relevant_toolsets(
            "build addon scanner.py coverage.py handlers.py and tests",
        )
        assert "colony" in result
        assert "planning" in result

    def test_empty_message_gets_fallback(self) -> None:
        result = classify_relevant_toolsets("")
        assert "operations" in result
        assert "colony" in result  # fallback

    def test_returns_set(self) -> None:
        result = classify_relevant_toolsets("status")
        assert isinstance(result, set)
