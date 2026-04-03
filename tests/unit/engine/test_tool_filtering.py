"""Wave 79 Track 2A: Colony task-aware tool filtering tests."""

from __future__ import annotations

from formicos.engine.runner import (
    _select_tool_profile,
    _CODING_TOOLS,
    _RESEARCH_TOOLS,
    _REVIEW_TOOLS,
)


def test_coder_gets_compact_profile() -> None:
    declared = [
        "memory_search", "code_execute", "workspace_execute",
        "list_workspace_files", "read_workspace_file",
        "write_workspace_file", "patch_file",
        "git_status", "git_diff", "git_log", "git_commit",
        "knowledge_detail", "transcript_search",
    ]
    result = _select_tool_profile("coder", declared)
    assert set(result) == set(declared) & _CODING_TOOLS
    assert "code_execute" in result
    assert "workspace_execute" in result
    assert "knowledge_detail" not in result


def test_reviewer_gets_compact_profile() -> None:
    declared = [
        "memory_search", "list_workspace_files", "read_workspace_file",
        "git_status", "git_diff", "git_log",
        "knowledge_detail", "transcript_search",
    ]
    result = _select_tool_profile("reviewer", declared)
    assert set(result) == set(declared) & _REVIEW_TOOLS
    assert "git_log" not in result  # not in review profile


def test_researcher_gets_compact_profile() -> None:
    declared = [
        "memory_search", "knowledge_detail", "transcript_search",
        "artifact_inspect", "list_workspace_files", "read_workspace_file",
    ]
    result = _select_tool_profile("researcher", declared)
    assert set(result) == set(declared) & _RESEARCH_TOOLS


def test_archivist_gets_full_list() -> None:
    declared = ["memory_search", "knowledge_detail", "read_workspace_file"]
    result = _select_tool_profile("archivist", declared)
    assert result == declared  # no profile for archivist


def test_unknown_caste_gets_full_list() -> None:
    declared = ["memory_search", "code_execute"]
    result = _select_tool_profile("custom_caste", declared)
    assert result == declared


def test_fallback_when_profile_too_small() -> None:
    """If intersection yields <3 tools, fall back to full declared list."""
    declared = ["memory_search", "git_log"]  # only 1 overlaps with coding
    result = _select_tool_profile("coder", declared)
    assert result == declared  # fallback to full


def test_empty_declared_returns_empty() -> None:
    result = _select_tool_profile("coder", [])
    assert result == []
