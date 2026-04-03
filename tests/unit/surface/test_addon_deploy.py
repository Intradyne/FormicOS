"""Wave 89 Track A: addon deployment tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from formicos.surface.addon_loader import (
    AddonManifest,
    AddonRegistration,
    load_new_addon,
    validate_new_addon,
)


def _make_manifest(name: str = "test-addon", **overrides: object) -> AddonManifest:
    base = {
        "name": name,
        "version": "1.0.0",
        "description": "Test addon",
    }
    base.update(overrides)
    return AddonManifest(**base)


def _make_registration(name: str = "existing") -> AddonRegistration:
    m = _make_manifest(name)
    reg = AddonRegistration(m)
    reg.registered_routes.append({
        "addon_name": name, "path": "/status", "handler": lambda: None,
    })
    return reg


class TestValidateNewAddon:
    def test_valid_new_addon(self) -> None:
        errors = validate_new_addon(_make_manifest("new"), [])
        # May have handler resolution errors (no actual module), but no name clash
        name_errors = [e for e in errors if "already exists" in e]
        assert name_errors == []

    def test_duplicate_name_fails(self) -> None:
        existing = [_make_registration("my-addon")]
        errors = validate_new_addon(_make_manifest("my-addon"), existing)
        assert any("already exists" in e for e in errors)

    def test_route_collision_detected(self) -> None:
        existing = [_make_registration("other")]
        # The existing addon has /status route
        new = _make_manifest("new", routes=[{"path": "/status", "handler": "x.py::f"}])
        errors = validate_new_addon(new, existing)
        assert any("conflicts" in e for e in errors)


class TestLoadNewAddon:
    @pytest.mark.asyncio()
    async def test_duplicate_name_rejected(self) -> None:
        app_state = MagicMock()
        app_state.addon_registrations = [_make_registration("dup")]
        runtime = MagicMock()
        runtime.emit_and_broadcast = AsyncMock()

        reg, errors = await load_new_addon(
            _make_manifest("dup"),
            app_state=app_state,
            runtime=runtime,
            base_runtime_context={},
        )
        assert reg is None
        assert any("already exists" in e for e in errors)

    @pytest.mark.asyncio()
    async def test_valid_addon_registers(self) -> None:
        app_state = MagicMock()
        app_state.addon_registrations = []
        runtime = MagicMock()
        runtime.emit_and_broadcast = AsyncMock()

        # Minimal manifest with no handlers to resolve
        manifest = _make_manifest("clean-addon")

        reg, errors = await load_new_addon(
            manifest,
            app_state=app_state,
            runtime=runtime,
            base_runtime_context={},
        )
        assert reg is not None
        assert errors == []
        assert reg.manifest.name == "clean-addon"
        # Should have been appended to app state
        assert len(app_state.addon_registrations) == 1
