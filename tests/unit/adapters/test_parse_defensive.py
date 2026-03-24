"""Tests for the 3-stage defensive tool-call parser."""

from __future__ import annotations

import json

from formicos.adapters.parse_defensive import parse_tool_calls_defensive

# ---------------------------------------------------------------------------
# Stage 1: clean JSON
# ---------------------------------------------------------------------------


class TestStage1CleanJSON:
    def test_single_tool_call(self) -> None:
        text = json.dumps({"name": "search", "arguments": {"query": "hello"}})
        result = parse_tool_calls_defensive(text)
        assert len(result) == 1
        assert result[0].name == "search"
        assert result[0].arguments == {"query": "hello"}

    def test_array_of_tool_calls(self) -> None:
        text = json.dumps([
            {"name": "search", "arguments": {"q": "a"}},
            {"name": "write", "arguments": {"path": "/tmp/x"}},
        ])
        result = parse_tool_calls_defensive(text)
        assert len(result) == 2
        assert result[0].name == "search"
        assert result[1].name == "write"

    def test_tool_calls_wrapper(self) -> None:
        text = json.dumps({"tool_calls": [
            {"name": "search", "arguments": {"q": "a"}},
        ]})
        result = parse_tool_calls_defensive(text)
        assert len(result) == 1
        assert result[0].name == "search"

    def test_function_call_wrapper(self) -> None:
        text = json.dumps({"function_call": {"name": "exec", "arguments": {"cmd": "ls"}}})
        result = parse_tool_calls_defensive(text)
        assert len(result) == 1
        assert result[0].name == "exec"

    def test_openai_function_format(self) -> None:
        """OpenAI format: {function: {name, arguments}}"""
        text = json.dumps({"function": {"name": "read_file", "arguments": "{\"path\": \"/a\"}"}})
        result = parse_tool_calls_defensive(text)
        assert len(result) == 1
        assert result[0].name == "read_file"
        assert result[0].arguments == {"path": "/a"}

    def test_args_as_string(self) -> None:
        """Arguments field is a JSON string (OpenAI format)."""
        text = json.dumps({"name": "search", "arguments": '{"query": "test"}'})
        result = parse_tool_calls_defensive(text)
        assert len(result) == 1
        assert result[0].arguments == {"query": "test"}

    def test_empty_input(self) -> None:
        assert parse_tool_calls_defensive("") == []
        assert parse_tool_calls_defensive("   ") == []


# ---------------------------------------------------------------------------
# Stage 2: json_repair
# ---------------------------------------------------------------------------


class TestStage2JsonRepair:
    def test_trailing_comma(self) -> None:
        text = '{"name": "search", "arguments": {"q": "hello",}}'
        result = parse_tool_calls_defensive(text)
        assert len(result) == 1
        assert result[0].name == "search"

    def test_missing_closing_brace(self) -> None:
        text = '{"name": "search", "arguments": {"q": "hello"}'
        result = parse_tool_calls_defensive(text)
        assert len(result) == 1
        assert result[0].name == "search"

    def test_single_quotes(self) -> None:
        text = "{'name': 'search', 'arguments': {'q': 'hello'}}"
        result = parse_tool_calls_defensive(text)
        assert len(result) == 1
        assert result[0].name == "search"


# ---------------------------------------------------------------------------
# Stage 3: regex extraction
# ---------------------------------------------------------------------------


class TestStage3Regex:
    def test_think_tags_stripped(self) -> None:
        text = (
            '<think>Internal reasoning here</think>'
            '{"name": "search", "arguments": {"q": "hello"}}'
        )
        result = parse_tool_calls_defensive(text)
        assert len(result) == 1
        assert result[0].name == "search"

    def test_markdown_fenced_json(self) -> None:
        text = (
            'Here is the tool call:\n```json\n'
            '{"name": "search", "arguments": {"q": "hello"}}\n```\nDone.'
        )
        result = parse_tool_calls_defensive(text)
        assert len(result) == 1
        assert result[0].name == "search"

    def test_markdown_fence_without_json_tag(self) -> None:
        text = '```\n{"name": "write", "arguments": {"text": "hi"}}\n```'
        result = parse_tool_calls_defensive(text)
        assert len(result) == 1
        assert result[0].name == "write"

    def test_think_tags_with_fenced_json(self) -> None:
        text = """<think>
I should use search to find the answer.
Let me format the tool call.
</think>
```json
{"name": "search", "arguments": {"query": "best practices"}}
```"""
        result = parse_tool_calls_defensive(text)
        assert len(result) == 1
        assert result[0].name == "search"
        assert result[0].arguments == {"query": "best practices"}

    def test_bare_json_in_text(self) -> None:
        text = (
            'I will call the tool now: '
            '{"name": "read", "arguments": {"path": "/x"}} and then continue.'
        )
        result = parse_tool_calls_defensive(text)
        assert len(result) == 1
        assert result[0].name == "read"

    def test_total_failure_returns_empty(self) -> None:
        text = "This is just plain text with no JSON at all."
        assert parse_tool_calls_defensive(text) == []


# ---------------------------------------------------------------------------
# Fuzzy tool matching
# ---------------------------------------------------------------------------


class TestFuzzyMatching:
    def test_fuzzy_match_close_name(self) -> None:
        """Hallucinated tool name close to a known tool should be corrected."""
        text = json.dumps({"name": "serch", "arguments": {"q": "hello"}})
        result = parse_tool_calls_defensive(text, known_tools={"search", "write", "read"})
        assert len(result) == 1
        assert result[0].name == "search"

    def test_exact_match_passes(self) -> None:
        text = json.dumps({"name": "search", "arguments": {"q": "hello"}})
        result = parse_tool_calls_defensive(text, known_tools={"search", "write"})
        assert len(result) == 1
        assert result[0].name == "search"

    def test_unknown_tool_rejected(self) -> None:
        """Completely unknown tool name should be rejected."""
        text = json.dumps({"name": "zzz_unknown_tool", "arguments": {}})
        result = parse_tool_calls_defensive(text, known_tools={"search", "write"})
        assert result == []

    def test_no_known_tools_accepts_all(self) -> None:
        """Without known_tools, accept any tool name."""
        text = json.dumps({"name": "anything", "arguments": {}})
        result = parse_tool_calls_defensive(text, known_tools=None)
        assert len(result) == 1
        assert result[0].name == "anything"


# ---------------------------------------------------------------------------
# Shape normalization
# ---------------------------------------------------------------------------


class TestShapeNormalization:
    def test_input_field_as_args(self) -> None:
        """Anthropic uses 'input' for arguments."""
        text = json.dumps({"name": "tool", "input": {"key": "val"}})
        result = parse_tool_calls_defensive(text)
        assert len(result) == 1
        assert result[0].arguments == {"key": "val"}

    def test_parameters_field_as_args(self) -> None:
        text = json.dumps({"name": "tool", "parameters": {"k": "v"}})
        result = parse_tool_calls_defensive(text)
        assert len(result) == 1
        assert result[0].arguments == {"k": "v"}

    def test_args_field_as_args(self) -> None:
        """Gemini uses 'args' for arguments."""
        text = json.dumps({"name": "tool", "args": {"k": "v"}})
        result = parse_tool_calls_defensive(text)
        assert len(result) == 1
        assert result[0].arguments == {"k": "v"}

    def test_no_args_defaults_empty(self) -> None:
        text = json.dumps({"name": "tool"})
        result = parse_tool_calls_defensive(text)
        assert len(result) == 1
        assert result[0].arguments == {}

    def test_malformed_args_string_wrapped(self) -> None:
        """Completely unparseable string args get wrapped in _raw."""
        text = json.dumps({"name": "tool", "arguments": "not json at all"})
        result = parse_tool_calls_defensive(text)
        assert len(result) == 1
        assert result[0].arguments == {"_raw": "not json at all"}
