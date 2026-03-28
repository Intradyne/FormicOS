"""Tests for Wave 66 T2: Addon config surface."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from formicos.surface.addon_loader import AddonConfigParam, AddonManifest


class TestAddonConfigManifest:
    """Test that addon manifests parse config declarations."""

    def test_manifest_parses_config_params(self) -> None:
        raw = {
            "name": "test-addon",
            "version": "1.0.0",
            "config": [
                {
                    "key": "enabled",
                    "type": "boolean",
                    "default": True,
                    "label": "Enable feature",
                },
                {
                    "key": "mode",
                    "type": "select",
                    "default": "fast",
                    "label": "Processing mode",
                    "options": ["fast", "thorough"],
                },
            ],
        }
        manifest = AddonManifest(**raw)
        assert len(manifest.config) == 2
        assert manifest.config[0].key == "enabled"
        assert manifest.config[0].type == "boolean"
        assert manifest.config[0].default is True
        assert manifest.config[1].options == ["fast", "thorough"]

    def test_manifest_config_defaults_empty(self) -> None:
        manifest = AddonManifest(name="bare-addon")
        assert manifest.config == []

    def test_config_param_defaults(self) -> None:
        param = AddonConfigParam(key="foo")
        assert param.type == "string"
        assert param.default is None
        assert param.label == ""
        assert param.options == []

    def test_real_manifests_parse_config(self) -> None:
        """All shipped addon manifests should parse with config field."""
        addons_dir = Path(__file__).resolve().parents[3] / "addons"
        for child in sorted(addons_dir.iterdir()):
            manifest_path = child / "addon.yaml"
            if child.is_dir() and manifest_path.exists():
                raw = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
                manifest = AddonManifest(**raw)
                # All three shipped addons have config blocks
                assert isinstance(manifest.config, list), f"{child.name} config not a list"

    def test_git_control_has_auto_stage_config(self) -> None:
        manifest_path = (
            Path(__file__).resolve().parents[3]
            / "addons" / "git-control" / "addon.yaml"
        )
        raw = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
        manifest = AddonManifest(**raw)
        keys = [c.key for c in manifest.config]
        assert "git_auto_stage" in keys

    def test_codebase_index_has_chunk_config(self) -> None:
        manifest_path = (
            Path(__file__).resolve().parents[3]
            / "addons" / "codebase-index" / "addon.yaml"
        )
        raw = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
        manifest = AddonManifest(**raw)
        keys = [c.key for c in manifest.config]
        assert "chunk_size" in keys
        assert "skip_dirs" in keys
