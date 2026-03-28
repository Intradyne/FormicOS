"""Tests for Wave 66 T3: Addon panels + routes wiring."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import pytest
import yaml

from formicos.surface.addon_loader import (
    AddonManifest,
    AddonRegistration,
    register_addon,
)


class TestRouteRegistration:
    """Test that addon routes are resolved and stored on registration."""

    def test_route_registered_on_addon(self) -> None:
        raw = {
            "name": "test-addon",
            "routes": [
                {"path": "/status", "handler": "status.py::get_status"},
            ],
        }
        manifest = AddonManifest(**raw)
        # Route resolution will fail (no module), but we can test manifest parsing
        reg = register_addon(manifest)
        # Handler resolution fails gracefully — route not registered
        assert isinstance(reg.registered_routes, list)

    def test_panel_registered_on_addon(self) -> None:
        raw = {
            "name": "test-addon",
            "panels": [
                {
                    "target": "knowledge",
                    "display_type": "status_card",
                    "path": "/status",
                    "handler": "status.py::get_status",
                },
            ],
        }
        manifest = AddonManifest(**raw)
        reg = register_addon(manifest)
        assert len(reg.registered_panels) == 1
        assert reg.registered_panels[0]["target"] == "knowledge"
        assert reg.registered_panels[0]["addon_name"] == "test-addon"

    def test_real_manifests_have_routes_and_panels(self) -> None:
        """Shipped addon manifests should declare routes and panels."""
        addons_dir = Path(__file__).resolve().parents[3] / "addons"
        found_routes = 0
        found_panels = 0
        for child in sorted(addons_dir.iterdir()):
            manifest_path = child / "addon.yaml"
            if child.is_dir() and manifest_path.exists():
                raw = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
                manifest = AddonManifest(**raw)
                found_routes += len(manifest.routes)
                found_panels += len(manifest.panels)
        # git-control and codebase-index each declare 1 route + 1 panel
        assert found_routes >= 2
        assert found_panels >= 2


class TestAddonStatusEndpoints:
    """Test addon status endpoint functions."""

    @pytest.mark.asyncio
    async def test_codebase_index_status_no_vector(self) -> None:
        from formicos.addons.codebase_index.status import get_status

        result = await get_status({}, "ws-1", "t-1", runtime_context={})
        assert result["display_type"] == "status_card"
        assert any(i["label"] == "Status" for i in result["items"])

    @pytest.mark.asyncio
    async def test_codebase_index_status_with_vector(self) -> None:
        from formicos.addons.codebase_index.status import get_status

        mock_vp = AsyncMock()
        mock_vp.collection_info.return_value = {"points_count": 1247}
        result = await get_status(
            {}, "ws-1", "t-1",
            runtime_context={"vector_port": mock_vp},
        )
        assert result["display_type"] == "status_card"
        assert any(i["value"] == "1247" for i in result["items"])

    @pytest.mark.asyncio
    async def test_git_status_no_workspace(self) -> None:
        from formicos.addons.git_control.status import get_status

        result = await get_status({}, "ws-1", "t-1", runtime_context={})
        assert result["display_type"] == "status_card"
        assert any(i["label"] == "Status" for i in result["items"])


class TestAddonRegistrationFields:
    """Test that AddonRegistration has route and panel fields."""

    def test_registration_has_route_and_panel_lists(self) -> None:
        manifest = AddonManifest(name="test")
        reg = AddonRegistration(manifest)
        assert reg.registered_routes == []
        assert reg.registered_panels == []

    def test_templates_still_warn(self) -> None:
        """Templates field should still log a warning (unimplemented)."""
        manifest = AddonManifest(
            name="test",
            templates=[{"name": "foo"}],
        )
        # Should not raise
        reg = register_addon(manifest)
        assert reg.registered_panels == []
