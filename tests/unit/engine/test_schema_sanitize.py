"""Tests for provider-aware tool schema sanitization (Wave 78.5 Track 1)."""

from __future__ import annotations

from formicos.engine.schema_sanitize import (
    coerce_array_items,
    maybe_sanitize_tool_schemas,
    sanitize_tool_schemas,
)


class TestSanitizeToolSchemas:
    def _nested_spec(self) -> dict:
        return {
            "name": "spawn_colony",
            "description": "Spawn a colony.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task": {"type": "string", "description": "Task text"},
                    "castes": {
                        "type": "array",
                        "description": "Caste list",
                        "items": {
                            "type": "object",
                            "properties": {
                                "caste": {
                                    "type": "string",
                                    "description": "Caste name",
                                },
                                "tier": {
                                    "type": "string",
                                    "description": "Tier level",
                                },
                            },
                            "required": ["caste"],
                        },
                    },
                },
            },
        }

    def test_flattens_nested_array_of_object(self) -> None:
        specs = sanitize_tool_schemas([self._nested_spec()])
        castes = specs[0]["parameters"]["properties"]["castes"]
        assert castes["items"]["type"] == "string"
        assert "JSON object string" in castes["description"]
        assert "caste" in castes["description"]

    def test_preserves_flat_schemas(self) -> None:
        flat_spec = {
            "name": "simple_tool",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                },
            },
        }
        result = sanitize_tool_schemas([flat_spec])
        assert result[0]["parameters"]["properties"]["query"]["type"] == "string"

    def test_does_not_mutate_original(self) -> None:
        original = self._nested_spec()
        original_items_type = original["parameters"]["properties"]["castes"]["items"]["type"]
        sanitize_tool_schemas([original])
        after = original["parameters"]["properties"]["castes"]["items"]["type"]
        assert after == original_items_type


class TestMaybeSanitize:
    def _spec(self) -> dict:
        return {
            "name": "test",
            "parameters": {
                "type": "object",
                "properties": {
                    "items": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {"key": {"type": "string"}},
                        },
                    },
                },
            },
        }

    def test_sanitizes_for_llama_cpp(self) -> None:
        result = maybe_sanitize_tool_schemas("llama-cpp", [self._spec()])
        assert result is not None
        prop = list(result)[0]["parameters"]["properties"]["items"]
        assert prop["items"]["type"] == "string"

    def test_sanitizes_for_llama_cpp_swarm(self) -> None:
        result = maybe_sanitize_tool_schemas("llama-cpp-swarm", [self._spec()])
        assert result is not None
        prop = list(result)[0]["parameters"]["properties"]["items"]
        assert prop["items"]["type"] == "string"

    def test_sanitizes_for_gemini(self) -> None:
        result = maybe_sanitize_tool_schemas("gemini", [self._spec()])
        assert result is not None
        prop = list(result)[0]["parameters"]["properties"]["items"]
        assert prop["items"]["type"] == "string"

    def test_no_sanitize_for_anthropic(self) -> None:
        result = maybe_sanitize_tool_schemas("anthropic", [self._spec()])
        assert result is not None
        prop = list(result)[0]["parameters"]["properties"]["items"]
        assert prop["items"]["type"] == "object"

    def test_no_sanitize_for_openai(self) -> None:
        result = maybe_sanitize_tool_schemas("openai", [self._spec()])
        assert result is not None
        prop = list(result)[0]["parameters"]["properties"]["items"]
        assert prop["items"]["type"] == "object"

    def test_none_specs_passthrough(self) -> None:
        assert maybe_sanitize_tool_schemas("llama-cpp", None) is None

    def test_empty_specs_passthrough(self) -> None:
        assert maybe_sanitize_tool_schemas("llama-cpp", []) == []


class TestCoerceArrayItems:
    def test_dict_passthrough(self) -> None:
        items = [{"caste": "coder"}, {"caste": "reviewer"}]
        assert coerce_array_items(items) == items

    def test_json_string_parsed(self) -> None:
        items = ['{"caste": "coder"}', '{"caste": "reviewer"}']
        result = coerce_array_items(items)
        assert len(result) == 2
        assert result[0] == {"caste": "coder"}
        assert result[1] == {"caste": "reviewer"}

    def test_mixed_formats(self) -> None:
        items = [{"caste": "coder"}, '{"caste": "reviewer"}']
        result = coerce_array_items(items)
        assert len(result) == 2

    def test_invalid_json_skipped(self) -> None:
        items = ["not json", '{"valid": true}']
        result = coerce_array_items(items)
        assert len(result) == 1
        assert result[0] == {"valid": True}

    def test_plain_string_skipped(self) -> None:
        items = ["coder"]
        result = coerce_array_items(items)
        assert len(result) == 0

    def test_empty_list(self) -> None:
        assert coerce_array_items([]) == []

    def test_json_array_string_skipped(self) -> None:
        items = ['[1, 2, 3]']
        result = coerce_array_items(items)
        assert len(result) == 0
