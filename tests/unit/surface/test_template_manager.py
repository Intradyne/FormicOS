"""Unit tests for template_manager.py (ADR-016)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest
import yaml

from formicos.surface.template_manager import (
    ColonyTemplate,
    get_template,
    list_templates,
    load_templates,
    new_template_id,
    save_template,
)


@pytest.fixture()
def tmp_templates(tmp_path: Path) -> Path:
    return tmp_path / "templates"


def _write_template(d: Path, tmpl_id: str, name: str, version: int = 1) -> None:
    d.mkdir(parents=True, exist_ok=True)
    data = {
        "template_id": tmpl_id,
        "name": name,
        "description": f"{name} description.",
        "version": version,
        "castes": [{"caste": "coder"}, {"caste": "reviewer"}],
        "strategy": "stigmergic",
        "budget_limit": 1.0,
        "max_rounds": 15,
        "tags": ["test"],
        "source_colony_id": None,
        "created_at": "2026-03-14T00:00:00Z",
        "use_count": 0,
    }
    path = d / f"{tmpl_id}-v{version}.yaml"
    with path.open("w", encoding="utf-8") as fh:
        yaml.dump(data, fh)


class TestLoadTemplates:
    @pytest.mark.anyio()
    async def test_empty_dir(self, tmp_templates: Path) -> None:
        templates = await load_templates(tmp_templates)
        assert templates == []

    @pytest.mark.anyio()
    async def test_nonexistent_dir(self, tmp_path: Path) -> None:
        templates = await load_templates(tmp_path / "nope")
        assert templates == []

    @pytest.mark.anyio()
    async def test_loads_single_template(self, tmp_templates: Path) -> None:
        _write_template(tmp_templates, "tmpl-001", "Code Review")
        templates = await load_templates(tmp_templates)
        assert len(templates) == 1
        assert templates[0].template_id == "tmpl-001"
        assert templates[0].name == "Code Review"

    @pytest.mark.anyio()
    async def test_returns_latest_version(self, tmp_templates: Path) -> None:
        _write_template(tmp_templates, "tmpl-001", "Code Review v1", version=1)
        _write_template(tmp_templates, "tmpl-001", "Code Review v2", version=2)
        templates = await load_templates(tmp_templates)
        assert len(templates) == 1
        assert templates[0].version == 2
        assert templates[0].name == "Code Review v2"

    @pytest.mark.anyio()
    async def test_multiple_templates(self, tmp_templates: Path) -> None:
        _write_template(tmp_templates, "tmpl-001", "Code Review")
        _write_template(tmp_templates, "tmpl-002", "Research Sprint")
        templates = await load_templates(tmp_templates)
        assert len(templates) == 2

    @pytest.mark.anyio()
    async def test_skips_invalid_yaml(self, tmp_templates: Path) -> None:
        tmp_templates.mkdir(parents=True, exist_ok=True)
        bad = tmp_templates / "bad.yaml"
        bad.write_text("{{invalid", encoding="utf-8")
        _write_template(tmp_templates, "tmpl-001", "Good")
        templates = await load_templates(tmp_templates)
        assert len(templates) == 1


class TestGetTemplate:
    @pytest.mark.anyio()
    async def test_found(self, tmp_templates: Path) -> None:
        _write_template(tmp_templates, "tmpl-001", "Code Review")
        tmpl = await get_template("tmpl-001", tmp_templates)
        assert tmpl is not None
        assert tmpl.template_id == "tmpl-001"

    @pytest.mark.anyio()
    async def test_not_found(self, tmp_templates: Path) -> None:
        _write_template(tmp_templates, "tmpl-001", "Code Review")
        tmpl = await get_template("tmpl-missing", tmp_templates)
        assert tmpl is None


class TestSaveTemplate:
    @pytest.mark.anyio()
    async def test_saves_yaml_and_emits_event(self, tmp_templates: Path) -> None:
        runtime = AsyncMock()
        runtime.emit_and_broadcast = AsyncMock(return_value=1)

        tmpl = ColonyTemplate(
            template_id="tmpl-new",
            name="New Template",
            description="Test.",
            castes=[{"caste": "coder"}],
        )
        saved = await save_template(tmpl, runtime, tmp_templates)

        # File exists
        yaml_path = tmp_templates / "tmpl-new-v1.yaml"
        assert yaml_path.exists()

        # Event emitted
        runtime.emit_and_broadcast.assert_awaited_once()
        event = runtime.emit_and_broadcast.call_args[0][0]
        assert event.type == "ColonyTemplateCreated"
        assert event.template_id == "tmpl-new"

        # created_at auto-filled
        assert saved.created_at != ""

    @pytest.mark.anyio()
    async def test_versioned_save(self, tmp_templates: Path) -> None:
        runtime = AsyncMock()
        runtime.emit_and_broadcast = AsyncMock(return_value=1)

        v1 = ColonyTemplate(
            template_id="tmpl-v",
            name="Template v1",
            description="First.",
            castes=[{"caste": "coder"}],
            version=1,
        )
        v2 = ColonyTemplate(
            template_id="tmpl-v",
            name="Template v2",
            description="Second.",
            castes=[{"caste": "coder"}, {"caste": "reviewer"}],
            version=2,
        )
        await save_template(v1, runtime, tmp_templates)
        await save_template(v2, runtime, tmp_templates)

        # Both files exist
        assert (tmp_templates / "tmpl-v-v1.yaml").exists()
        assert (tmp_templates / "tmpl-v-v2.yaml").exists()

        # load_templates returns latest
        templates = await load_templates(tmp_templates)
        match = [t for t in templates if t.template_id == "tmpl-v"]
        assert len(match) == 1
        assert match[0].version == 2


class TestListTemplates:
    @pytest.mark.anyio()
    async def test_returns_dicts(self, tmp_templates: Path) -> None:
        _write_template(tmp_templates, "tmpl-001", "Code Review")
        result = await list_templates(tmp_templates)
        assert len(result) == 1
        assert isinstance(result[0], dict)
        assert result[0]["template_id"] == "tmpl-001"


class TestNewTemplateId:
    def test_format(self) -> None:
        tid = new_template_id()
        assert tid.startswith("tmpl-")
        assert len(tid) == 13  # "tmpl-" + 8 hex chars
