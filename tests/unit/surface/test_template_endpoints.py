"""Unit tests for template REST endpoints in app.py."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
import yaml
from starlette.testclient import TestClient

from formicos.surface.template_manager import ColonyTemplate


def _write_template(d: Path, tmpl_id: str, name: str, version: int = 1) -> None:
    d.mkdir(parents=True, exist_ok=True)
    data = {
        "template_id": tmpl_id,
        "name": name,
        "description": f"{name} desc.",
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


@pytest.fixture()
def _tmp_templates(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Patch TEMPLATE_DIR to a tmp directory."""
    d = tmp_path / "templates"
    d.mkdir()
    monkeypatch.setattr(
        "formicos.surface.template_manager.TEMPLATE_DIR", d,
    )
    return d


class TestGetTemplates:
    @pytest.mark.anyio()
    async def test_list_empty(self, _tmp_templates: Path) -> None:
        from formicos.surface.template_manager import list_templates

        result = await list_templates(_tmp_templates)
        assert result == []

    @pytest.mark.anyio()
    async def test_list_with_templates(self, _tmp_templates: Path) -> None:
        from formicos.surface.template_manager import list_templates

        _write_template(_tmp_templates, "tmpl-a", "Alpha")
        _write_template(_tmp_templates, "tmpl-b", "Beta")
        result = await list_templates(_tmp_templates)
        assert len(result) == 2


class TestGetTemplateDetail:
    @pytest.mark.anyio()
    async def test_found(self, _tmp_templates: Path) -> None:
        from formicos.surface.template_manager import get_template

        _write_template(_tmp_templates, "tmpl-a", "Alpha")
        result = await get_template("tmpl-a", _tmp_templates)
        assert result is not None
        assert result.name == "Alpha"

    @pytest.mark.anyio()
    async def test_not_found(self, _tmp_templates: Path) -> None:
        from formicos.surface.template_manager import get_template

        result = await get_template("nope", _tmp_templates)
        assert result is None


class TestCreateTemplate:
    @pytest.mark.anyio()
    async def test_save_creates_file_and_emits(self, _tmp_templates: Path) -> None:
        from formicos.surface.template_manager import save_template

        runtime = AsyncMock()
        runtime.emit_and_broadcast = AsyncMock(return_value=1)

        tmpl = ColonyTemplate(
            template_id="tmpl-new",
            name="New",
            description="desc",
            castes=[{"caste": "coder"}],
        )
        saved = await save_template(tmpl, runtime, _tmp_templates)
        assert (_tmp_templates / "tmpl-new-v1.yaml").exists()
        runtime.emit_and_broadcast.assert_awaited_once()
        assert saved.template_id == "tmpl-new"
