"""Wave 89 Track C: check_hosted_capabilities tool tests."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from unittest.mock import MagicMock

import pytest


@dataclass
class _FakeManifest:
    name: str = "system-health"
    version: str = "1.0.0"
    description: str = "test"
    hidden: bool = False
    tools: list[Any] = field(default_factory=list)
    handlers: list[Any] = field(default_factory=list)
    triggers: list[Any] = field(default_factory=list)
    config: list[Any] = field(default_factory=list)
    panels: list[Any] = field(default_factory=list)


@dataclass
class _FakeTrigger:
    type: str = "cron"
    schedule: str = "*/5 * * * *"
    handler: str = "status.py::refresh"


@dataclass
class _FakeRegistration:
    manifest: _FakeManifest = field(default_factory=_FakeManifest)
    registered_panels: list[dict[str, Any]] = field(default_factory=list)
    registered_tools: list[Any] = field(default_factory=list)
    health_status: str = "ok"
    last_error: str = ""
    disabled: bool = False
    trigger_fire_times: dict[str, Any] = field(default_factory=dict)
    tool_call_counts: dict[str, int] = field(default_factory=dict)
    last_handler_fire: str = ""
    handler_error_count: int = 0


def _make_dispatcher(registrations: list[_FakeRegistration]) -> Any:
    """Build a minimal mock QueenToolDispatcher with addon registrations."""
    from formicos.surface.queen_tools import QueenToolDispatcher

    runtime = MagicMock()
    runtime.addon_registrations = registrations
    runtime.projections = MagicMock()
    runtime.projections.workspaces = {}

    dispatcher = QueenToolDispatcher.__new__(QueenToolDispatcher)
    dispatcher._runtime = runtime
    return dispatcher


class TestCheckHostedCapabilities:
    @pytest.mark.anyio()
    async def test_no_registrations(self) -> None:
        dispatcher = _make_dispatcher([])
        text, meta = await dispatcher._check_hosted_capabilities({}, "ws-1", "t-1")
        assert "No hosted capabilities" in text
        assert meta is None

    @pytest.mark.anyio()
    async def test_single_addon_with_panels(self) -> None:
        reg = _FakeRegistration(
            registered_panels=[
                {"target": "workspace", "path": "/dashboard", "display_type": "kpi_card", "refresh_interval_s": 30},
            ],
        )
        dispatcher = _make_dispatcher([reg])
        text, meta = await dispatcher._check_hosted_capabilities({}, "ws-1", "t-1")
        assert "system-health" in text
        assert "1 addon" in text
        assert meta is not None
        caps = meta["capabilities"]
        assert len(caps) == 1
        assert caps[0]["addon"] == "system-health"
        assert caps[0]["panels"][0]["refresh_interval_s"] == 30

    @pytest.mark.anyio()
    async def test_disabled_addon_flagged(self) -> None:
        reg = _FakeRegistration(disabled=True, health_status="error", last_error="import failed")
        dispatcher = _make_dispatcher([reg])
        text, meta = await dispatcher._check_hosted_capabilities({}, "ws-1", "t-1")
        assert "DISABLED" in text
        assert "import failed" in text
        caps = meta["capabilities"]
        assert caps[0]["disabled"] is True
        assert caps[0]["last_error"] == "import failed"

    @pytest.mark.anyio()
    async def test_hidden_addon_excluded(self) -> None:
        hidden = _FakeRegistration(manifest=_FakeManifest(hidden=True))
        visible = _FakeRegistration(manifest=_FakeManifest(name="visible-addon"))
        dispatcher = _make_dispatcher([hidden, visible])
        text, meta = await dispatcher._check_hosted_capabilities({}, "ws-1", "t-1")
        assert "visible-addon" in text
        caps = meta["capabilities"]
        assert len(caps) == 1
        assert caps[0]["addon"] == "visible-addon"

    @pytest.mark.anyio()
    async def test_trigger_metadata_included(self) -> None:
        manifest = _FakeManifest(triggers=[_FakeTrigger()])
        reg = _FakeRegistration(manifest=manifest)
        dispatcher = _make_dispatcher([reg])
        text, meta = await dispatcher._check_hosted_capabilities({}, "ws-1", "t-1")
        assert "cron" in text
        caps = meta["capabilities"]
        assert len(caps[0]["triggers"]) == 1
        assert caps[0]["triggers"][0]["type"] == "cron"

    @pytest.mark.anyio()
    async def test_multiple_addons(self) -> None:
        reg1 = _FakeRegistration(manifest=_FakeManifest(name="health"))
        reg2 = _FakeRegistration(manifest=_FakeManifest(name="repo-activity"))
        dispatcher = _make_dispatcher([reg1, reg2])
        text, meta = await dispatcher._check_hosted_capabilities({}, "ws-1", "t-1")
        assert "2 addon" in text
        caps = meta["capabilities"]
        assert len(caps) == 2
