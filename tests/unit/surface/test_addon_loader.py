"""Tests for Wave 64 Track 6a — addon loader."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from formicos.surface.addon_loader import (
    AddonManifest,
    build_addon_tool_specs,
    discover_addons,
    load_addon_manifest,
    register_addon,
)


# ---------------------------------------------------------------------------
# Fixture: create a temporary addon directory
# ---------------------------------------------------------------------------

@pytest.fixture()
def addon_dir(tmp_path: Path) -> Path:
    """Create a minimal addon directory with a hello-world addon."""
    hw_dir = tmp_path / "hello-world"
    hw_dir.mkdir()
    manifest = hw_dir / "addon.yaml"
    manifest.write_text(
        "name: hello-world\n"
        "version: '1.0.0'\n"
        "description: Test addon\n"
        "author: test\n"
        "tools:\n"
        "  - name: hello\n"
        "    description: Say hello\n"
        "    handler: handler.py::handle_hello\n"
        "    parameters:\n"
        "      type: object\n"
        "      properties:\n"
        "        greeting:\n"
        "          type: string\n",
        encoding="utf-8",
    )
    return tmp_path


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestManifestParsing:
    """Test addon manifest loading."""

    def test_load_valid_manifest(self, addon_dir: Path) -> None:
        manifest = load_addon_manifest(addon_dir / "hello-world" / "addon.yaml")
        assert manifest.name == "hello-world"
        assert manifest.version == "1.0.0"
        assert len(manifest.tools) == 1
        assert manifest.tools[0].name == "hello"
        assert manifest.tools[0].handler == "handler.py::handle_hello"

    def test_discover_addons(self, addon_dir: Path) -> None:
        manifests = discover_addons(addon_dir)
        assert len(manifests) == 1
        assert manifests[0].name == "hello-world"

    def test_discover_empty_dir(self, tmp_path: Path) -> None:
        manifests = discover_addons(tmp_path)
        assert manifests == []

    def test_discover_nonexistent_dir(self, tmp_path: Path) -> None:
        manifests = discover_addons(tmp_path / "nope")
        assert manifests == []

    def test_invalid_manifest_skipped(self, tmp_path: Path) -> None:
        bad_dir = tmp_path / "bad-addon"
        bad_dir.mkdir()
        (bad_dir / "addon.yaml").write_text("not a mapping", encoding="utf-8")
        manifests = discover_addons(tmp_path)
        assert manifests == []


class TestRegistration:
    """Test addon component registration."""

    def test_registers_tool_in_handler_dict(self) -> None:
        """Tool handler from hello-world addon is registered in the dict."""
        manifest = AddonManifest(
            name="hello-world",
            version="1.0.0",
            tools=[{  # type: ignore[list-item]
                "name": "hello",
                "description": "Say hello",
                "handler": "handler.py::handle_hello",
                "parameters": {"type": "object", "properties": {}},
            }],
        )
        registry: dict[str, Any] = {}
        result = register_addon(manifest, tool_registry=registry)
        assert "hello" in registry
        assert result.registered_tools == ["hello"]

    def test_registered_tool_is_callable(self) -> None:
        """The registered wrapper calls the actual handler."""
        manifest = AddonManifest(
            name="hello-world",
            version="1.0.0",
            tools=[{  # type: ignore[list-item]
                "name": "hello",
                "description": "Say hello",
                "handler": "handler.py::handle_hello",
                "parameters": {"type": "object", "properties": {}},
            }],
        )
        registry: dict[str, Any] = {}
        register_addon(manifest, tool_registry=registry)
        result = asyncio.run(
            registry["hello"]({"greeting": "Hi"}, "ws1", "th1")
        )
        assert result == "Hi from addon system!"

    def test_registers_event_handler(self) -> None:
        manifest = AddonManifest(
            name="hello-world",
            version="1.0.0",
            handlers=[{  # type: ignore[list-item]
                "event": "ColonyCompleted",
                "handler": "handler.py::handle_hello",
            }],
        )
        mock_router = MagicMock()
        result = register_addon(manifest, service_router=mock_router)
        mock_router.register_handler.assert_called_once()
        call_args = mock_router.register_handler.call_args
        assert call_args[0][0] == "addon:hello-world:ColonyCompleted"
        assert "addon:hello-world:ColonyCompleted" in result.registered_handlers

    def test_bad_handler_ref_skipped(self) -> None:
        """Invalid handler reference doesn't crash, just skips."""
        manifest = AddonManifest(
            name="hello-world",
            version="1.0.0",
            tools=[{  # type: ignore[list-item]
                "name": "broken",
                "description": "Broken tool",
                "handler": "nonexistent.py::nope",
                "parameters": {"type": "object", "properties": {}},
            }],
        )
        registry: dict[str, Any] = {}
        result = register_addon(manifest, tool_registry=registry)
        assert "broken" not in registry
        assert result.registered_tools == []


    def test_runtime_context_stored_on_registration(self) -> None:
        """Runtime context is stored on the AddonRegistration result."""
        manifest = AddonManifest(name="test", version="1.0")
        ctx = {"vector_port": "mock_port"}
        result = register_addon(manifest, runtime_context=ctx)
        assert result.runtime_context == ctx

    def test_handler_without_runtime_context_still_works(self) -> None:
        """Handlers that don't accept runtime_context are called normally."""
        manifest = AddonManifest(
            name="hello-world",
            version="1.0.0",
            tools=[{  # type: ignore[list-item]
                "name": "hello",
                "description": "Say hello",
                "handler": "handler.py::handle_hello",
                "parameters": {"type": "object", "properties": {}},
            }],
        )
        registry: dict[str, Any] = {}
        register_addon(manifest, tool_registry=registry, runtime_context={"key": "val"})
        # handler.py::handle_hello does not accept runtime_context
        result = asyncio.run(registry["hello"]({"greeting": "Hi"}, "ws1", "th1"))
        assert result == "Hi from addon system!"


class TestToolSpecs:
    """Test addon tool spec generation for Queen."""

    def test_build_addon_tool_specs(self) -> None:
        manifests = [
            AddonManifest(
                name="test-addon",
                tools=[{  # type: ignore[list-item]
                    "name": "my_tool",
                    "description": "Does stuff",
                    "handler": "handler.py::func",
                    "parameters": {"type": "object", "properties": {"x": {"type": "string"}}},
                }],
            ),
        ]
        specs = build_addon_tool_specs(manifests)
        assert len(specs) == 1
        assert specs[0]["name"] == "my_tool"
        assert specs[0]["description"] == "Does stuff"
        assert "x" in specs[0]["parameters"]["properties"]
