"""Tests for formicos.surface.config_validator — CONFIG_UPDATE payload validation."""

from __future__ import annotations

import json
from typing import Any

from formicos.surface.config_validator import (
    FORBIDDEN_CONFIG_PREFIXES,
    PARAM_RULES,
    ConfigValidationResult,
    validate_config_update,
)

# ---------------------------------------------------------------------------
# Whitelist loaded from YAML
# ---------------------------------------------------------------------------


class TestParamRulesLoaded:
    """Verify PARAM_RULES loaded from experimentable_params.yaml."""

    def test_rules_not_empty(self) -> None:
        assert len(PARAM_RULES) > 0

    def test_live_caste_paths(self) -> None:
        """All paths use castes.* not recipes.* (prealpha schema)."""
        for path in PARAM_RULES:
            if path.startswith("castes."):
                parts = path.split(".")
                assert parts[1] in {
                    "queen", "coder", "reviewer", "researcher", "archivist",
                }, f"unexpected caste in path: {path}"

    def test_no_prealpha_paths(self) -> None:
        for path in PARAM_RULES:
            assert not path.startswith("recipes."), f"prealpha path found: {path}"
            for old_caste in ("architect", "manager"):
                assert f".{old_caste}." not in path, f"prealpha caste in path: {path}"

    def test_temperature_paths_present(self) -> None:
        for caste in ("queen", "coder", "reviewer", "researcher", "archivist"):
            assert f"castes.{caste}.temperature" in PARAM_RULES

    def test_base_tool_calls_paths_present(self) -> None:
        for caste in ("coder", "reviewer", "researcher", "archivist"):
            assert f"castes.{caste}.base_tool_calls_per_iteration" in PARAM_RULES

    def test_governance_paths_present(self) -> None:
        assert "governance.stall_detection_window" in PARAM_RULES
        assert "governance.convergence_threshold" in PARAM_RULES


# ---------------------------------------------------------------------------
# Valid payloads
# ---------------------------------------------------------------------------


class TestValidPayloads:
    def test_valid_temperature_dict(self) -> None:
        result = validate_config_update({
            "param_path": "castes.coder.temperature",
            "value": 0.5,
        })
        assert result.valid is True
        assert result.param_path == "castes.coder.temperature"
        assert result.value == 0.5

    def test_valid_temperature_json_string(self) -> None:
        payload = json.dumps({"param_path": "castes.coder.temperature", "value": 0.7})
        result = validate_config_update(payload)
        assert result.valid is True
        assert result.value == 0.7

    def test_valid_int_param(self) -> None:
        result = validate_config_update({
            "param_path": "castes.coder.max_iterations",
            "value": 15,
        })
        assert result.valid is True
        assert result.value == 15

    def test_valid_base_tool_calls(self) -> None:
        result = validate_config_update({
            "param_path": "castes.coder.base_tool_calls_per_iteration",
            "value": 25,
        })
        assert result.valid is True

    def test_valid_execution_time(self) -> None:
        result = validate_config_update({
            "param_path": "castes.coder.max_execution_time_s",
            "value": 300,
        })
        assert result.valid is True

    def test_valid_governance_param(self) -> None:
        result = validate_config_update({
            "param_path": "governance.convergence_threshold",
            "value": 0.90,
        })
        assert result.valid is True

    def test_valid_routing_param(self) -> None:
        result = validate_config_update({
            "param_path": "routing.tau_threshold",
            "value": 0.5,
        })
        assert result.valid is True

    def test_extra_keys_stripped(self) -> None:
        result = validate_config_update({
            "param_path": "castes.coder.temperature",
            "value": 0.5,
            "hallucinated_key": "should be ignored",
        })
        assert result.valid is True


# ---------------------------------------------------------------------------
# Unknown param paths
# ---------------------------------------------------------------------------


class TestUnknownPaths:
    def test_unknown_path(self) -> None:
        result = validate_config_update({
            "param_path": "castes.coder.nonexistent",
            "value": 1,
        })
        assert result.valid is False
        assert "unknown param_path" in result.error

    def test_prealpha_path_rejected(self) -> None:
        result = validate_config_update({
            "param_path": "recipes.coder.temperature",
            "value": 0.5,
        })
        assert result.valid is False
        assert "unknown param_path" in result.error

    def test_prealpha_caste_rejected(self) -> None:
        result = validate_config_update({
            "param_path": "castes.architect.temperature",
            "value": 0.5,
        })
        assert result.valid is False


# ---------------------------------------------------------------------------
# Out-of-range values
# ---------------------------------------------------------------------------


class TestOutOfRange:
    def test_temperature_too_high(self) -> None:
        result = validate_config_update({
            "param_path": "castes.coder.temperature",
            "value": 5.0,
        })
        assert result.valid is False
        assert "out of range" in result.error

    def test_temperature_negative(self) -> None:
        result = validate_config_update({
            "param_path": "castes.coder.temperature",
            "value": -0.1,
        })
        assert result.valid is False
        assert "out of range" in result.error

    def test_iterations_too_high(self) -> None:
        result = validate_config_update({
            "param_path": "castes.coder.max_iterations",
            "value": 999,
        })
        assert result.valid is False

    def test_iterations_zero(self) -> None:
        result = validate_config_update({
            "param_path": "castes.coder.max_iterations",
            "value": 0,
        })
        assert result.valid is False

    def test_boundary_min_accepted(self) -> None:
        result = validate_config_update({
            "param_path": "castes.coder.temperature",
            "value": 0.0,
        })
        assert result.valid is True

    def test_boundary_max_accepted(self) -> None:
        result = validate_config_update({
            "param_path": "castes.coder.temperature",
            "value": 1.0,
        })
        assert result.valid is True

    def test_wrong_type_for_int(self) -> None:
        result = validate_config_update({
            "param_path": "castes.coder.max_iterations",
            "value": "not_a_number",
        })
        assert result.valid is False
        assert "int" in result.error

    def test_wrong_type_for_float(self) -> None:
        result = validate_config_update({
            "param_path": "castes.coder.temperature",
            "value": [1, 2, 3],
        })
        assert result.valid is False
        assert "float" in result.error


# ---------------------------------------------------------------------------
# Forbidden strings
# ---------------------------------------------------------------------------


class TestForbiddenStrings:
    def test_null_byte(self) -> None:
        result = validate_config_update({
            "param_path": "castes.coder.temperature",
            "value": "hello\x00world",
        })
        assert result.valid is False
        assert "forbidden content" in result.error

    def test_shell_injection(self) -> None:
        result = validate_config_update({
            "param_path": "castes.coder.temperature",
            "value": "rm -rf /",
        })
        assert result.valid is False
        assert "forbidden content" in result.error

    def test_exec_injection(self) -> None:
        result = validate_config_update({
            "param_path": "castes.coder.temperature",
            "value": "exec('evil')",
        })
        assert result.valid is False

    def test_xss(self) -> None:
        result = validate_config_update({
            "param_path": "castes.coder.temperature",
            "value": "<script>alert(1)</script>",
        })
        assert result.valid is False

    def test_shell_expansion(self) -> None:
        result = validate_config_update({
            "param_path": "castes.coder.temperature",
            "value": "${HOME}",
        })
        assert result.valid is False

    def test_forbidden_in_param_path(self) -> None:
        """Forbidden scan covers the whole payload including param_path."""
        result = validate_config_update({
            "param_path": "eval(bad)",
            "value": 0.5,
        })
        assert result.valid is False


# ---------------------------------------------------------------------------
# NaN / Inf rejection
# ---------------------------------------------------------------------------


class TestNanInf:
    def test_nan_float(self) -> None:
        result = validate_config_update({
            "param_path": "castes.coder.temperature",
            "value": float("nan"),
        })
        assert result.valid is False
        assert "NaN/Inf" in result.error

    def test_inf_float(self) -> None:
        result = validate_config_update({
            "param_path": "castes.coder.temperature",
            "value": float("inf"),
        })
        assert result.valid is False

    def test_neg_inf_float(self) -> None:
        result = validate_config_update({
            "param_path": "castes.coder.temperature",
            "value": float("-inf"),
        })
        assert result.valid is False

    def test_nan_string(self) -> None:
        result = validate_config_update({
            "param_path": "castes.coder.temperature",
            "value": "NaN",
        })
        assert result.valid is False

    def test_infinity_string(self) -> None:
        result = validate_config_update({
            "param_path": "castes.coder.temperature",
            "value": "infinity",
        })
        assert result.valid is False


# ---------------------------------------------------------------------------
# Depth guard
# ---------------------------------------------------------------------------


class TestDepthGuard:
    def test_shallow_payload_ok(self) -> None:
        result = validate_config_update({
            "param_path": "castes.coder.temperature",
            "value": {"nested": "ok"},
        })
        # Will fail type check (value is dict not float) but not depth guard
        assert "depth" not in result.error

    def test_deeply_nested_rejected(self) -> None:
        deep: dict[str, Any] = {"a": {"b": {"c": {"d": {"e": "too deep"}}}}}
        result = validate_config_update({
            "param_path": "castes.coder.temperature",
            "value": deep,
        })
        assert result.valid is False
        assert "depth" in result.error

    def test_exact_max_depth_ok(self) -> None:
        # depth 4 = root → a → b → c → leaf
        at_limit: dict[str, Any] = {"a": {"b": {"c": "leaf"}}}
        result = validate_config_update({
            "param_path": "castes.coder.temperature",
            "value": at_limit,
        })
        assert "depth" not in result.error


# ---------------------------------------------------------------------------
# Oversized payload
# ---------------------------------------------------------------------------


class TestOversizedPayload:
    def test_oversized_string(self) -> None:
        huge = json.dumps({"param_path": "castes.coder.temperature", "value": "x" * 3000})
        result = validate_config_update(huge)
        assert result.valid is False
        assert "too large" in result.error

    def test_within_limit(self) -> None:
        ok = json.dumps({"param_path": "castes.coder.temperature", "value": 0.5})
        result = validate_config_update(ok)
        assert result.valid is True


# ---------------------------------------------------------------------------
# Forbidden config prefixes
# ---------------------------------------------------------------------------


class TestForbiddenPrefixes:
    def test_system_prefix_rejected(self) -> None:
        result = validate_config_update({
            "param_path": "system.port",
            "value": 9090,
        })
        assert result.valid is False
        assert "forbidden prefix" in result.error

    def test_models_registry_prefix_rejected(self) -> None:
        result = validate_config_update({
            "param_path": "models.registry.0.api_key_env",
            "value": "STOLEN_KEY",
        })
        assert result.valid is False
        assert "forbidden prefix" in result.error

    def test_embedding_prefix_rejected(self) -> None:
        result = validate_config_update({
            "param_path": "embedding.model",
            "value": "evil-model",
        })
        assert result.valid is False

    def test_vector_prefix_rejected(self) -> None:
        result = validate_config_update({
            "param_path": "vector.qdrant_url",
            "value": "http://evil.com",
        })
        assert result.valid is False

    def test_knowledge_graph_prefix_rejected(self) -> None:
        result = validate_config_update({
            "param_path": "knowledge_graph.entity_similarity_threshold",
            "value": 0.5,
        })
        assert result.valid is False

    def test_skill_bank_prefix_rejected(self) -> None:
        result = validate_config_update({
            "param_path": "skill_bank.ucb_exploration_weight",
            "value": 0.5,
        })
        assert result.valid is False

    def test_all_forbidden_prefixes_have_tests(self) -> None:
        """Every entry in FORBIDDEN_CONFIG_PREFIXES is tested above."""
        tested = {
            "system.",
            "models.registry.",
            "embedding.",
            "vector.",
            "knowledge_graph.",
            "skill_bank.",
        }
        assert tested == FORBIDDEN_CONFIG_PREFIXES


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_non_dict_payload(self) -> None:
        result = validate_config_update("[1, 2, 3]")
        assert result.valid is False
        assert "JSON object" in result.error

    def test_invalid_json(self) -> None:
        result = validate_config_update("{bad json")
        assert result.valid is False
        assert "unparseable" in result.error

    def test_empty_dict(self) -> None:
        result = validate_config_update({})
        assert result.valid is False

    def test_missing_value_key(self) -> None:
        result = validate_config_update({"param_path": "castes.coder.temperature"})
        # value defaults to None → will fail NaN check or type check
        assert result.valid is False

    def test_result_model_shape(self) -> None:
        result = validate_config_update({
            "param_path": "castes.coder.temperature",
            "value": 0.5,
        })
        assert isinstance(result, ConfigValidationResult)
        assert hasattr(result, "valid")
        assert hasattr(result, "param_path")
        assert hasattr(result, "value")
        assert hasattr(result, "error")
